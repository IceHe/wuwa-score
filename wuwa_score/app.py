"""Live scoring window and background OCR loop."""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .capture import GameWindow, capture_game, enable_dpi_awareness, foreground_game
from .overlay import ScoreOverlay
from .recognition import Echo
from .scoring import (
    calculate_echo_score, default_template, format_probability, format_template_label,
    reload_templates, resolve_template_name, substat_tier_label, template_names,
)
from .template_selector import TemplateSelector

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Update:
    status: str
    echo: Echo | None = None
    clear: bool = False
    game: GameWindow | None = None


def scan_live(updates, stop, capture=capture_game):
    reader = None
    previous = None

    def publish(update):
        nonlocal previous
        if update != previous:
            updates.put(update)
            previous = update

    while not stop.is_set():
        try:
            frame = capture()
        except OSError:
            publish(Update("暂时无法截取画面，正在重试"))
            stop.wait(0.5)
            continue

        if frame is None:
            publish(Update("等待鸣潮切到前台"))
            stop.wait(0.5)
            continue
        image, game = frame
        try:
            if reader is None:
                publish(Update("正在加载 OCR 模型…"))
                from .ocr import EchoReader
                reader = EchoReader()
                # Load takes longer than one scan. Discard the pre-load frame.
                continue
            echo = reader.read(image)
        except Exception:
            logging.exception("Echo OCR failed")
            publish(Update("OCR 运行失败，错误详情见终端", clear=True))
            return

        if echo is None:
            publish(Update("请打开单个声骸的详情或强化页面", clear=True))
        else:
            publish(Update("已识别当前声骸", echo, game=game))
        stop.wait(0.5)


BG = "#101721"
PANEL = "#1A2634"
TEXT = "#F0F5FA"
MUTED = "#9EAFBE"
ACCENT = "#7CE5D4"
FONT = "Microsoft YaHei UI"


class ScoreWindow:
    def __init__(self, root, template, updates):
        self.root = root
        self.updates = updates
        self.echo = None
        self.game = None
        self.score = None
        self.template = template or default_template()
        self.template_specified = template is not None
        self.applied_template_label = self.template
        self.template_update = None

        root.title("wuwa-score · 声骸评分")
        root.configure(background=BG)
        # Start between the two game panels so the window does not cover
        # the stats it needs to capture on a typical single-display setup.
        offset = max(0, (root.winfo_screenwidth() - 390) // 2)
        root.geometry(f"390x502+{offset}+48")
        root.minsize(375, 502)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL,
                        rowheight=25, font=(FONT, 9), borderwidth=0)
        style.configure("Treeview.Heading", background=BG, foreground=MUTED,
                        font=(FONT, 9, "bold"))
        style.map("Treeview", background=[("selected", "#334B61")])
        style.configure("Score.TCheckbutton", background=BG, foreground=TEXT, font=(FONT, 9))
        style.map("Score.TCheckbutton", background=[("active", BG)],
                  foreground=[("active", TEXT)])
        style.configure("Score.TButton", background=PANEL, foreground=TEXT,
                        font=(FONT, 9), padding=(8, 4))
        style.map("Score.TButton", background=[("active", "#273748")],
                  foreground=[("disabled", MUTED)])

        content = tk.Frame(root, background=BG, padx=14, pady=12)
        content.grid(sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)

        controls = tk.Frame(content, background=BG)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(1, weight=1)
        tk.Label(controls, text="评分模板", bg=BG, fg=TEXT, font=(FONT, 9)).grid(
            row=0, column=0, padx=(0, 6)
        )
        self.selector = TemplateSelector(
            controls, template_names(), self.template, self.select_template, font=(FONT, 9)
        )
        self.selector.grid(row=0, column=1, sticky="ew")
        self.auto_match = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            controls, style="Score.TCheckbutton", text="自动", variable=self.auto_match,
            command=self.render,
        ).grid(row=0, column=2, padx=(8, 0))
        self.topmost = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            controls, style="Score.TCheckbutton", text="置顶", variable=self.topmost,
            command=lambda: root.attributes("-topmost", self.topmost.get()),
        ).grid(row=0, column=3, padx=(8, 0))

        self.status = tk.StringVar(value="等待鸣潮切到前台")
        tk.Label(content, textvariable=self.status, bg=BG, fg=MUTED, font=(FONT, 9),
                 anchor="w").grid(row=1, column=0, sticky="ew", pady=(0, 8))

        scores = tk.Frame(content, background=BG)
        scores.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        scores.columnconfigure((0, 1), weight=1, uniform="scores")
        self.current = self.score_card(scores, 0, "当前评分", ACCENT)
        self.potential = self.score_card(scores, 1, "理论最高", TEXT)
        probability = tk.Frame(scores, background=PANEL, padx=12, pady=3)
        probability.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        probability.columnconfigure(0, weight=1)
        self.double_crit = tk.StringVar(value="—")
        self.potential_probability = tk.StringVar(value="—")
        for row, (label, value) in enumerate((
            ("双暴概率", self.double_crit),
            ("理论最高分概率", self.potential_probability),
        )):
            tk.Label(probability, text=label, bg=PANEL, fg=MUTED, font=(FONT, 9)).grid(
                row=row, column=0, sticky="w"
            )
            tk.Label(probability, textvariable=value, bg=PANEL, fg=TEXT, font=(FONT, 11, "bold")).grid(
                row=row, column=1, sticky="e"
            )

        columns = ("stat", "value", "tier", "score")
        self.rows = ttk.Treeview(content, columns=columns, show="headings", height=7,
                                 selectmode="none")
        for column, label, width in zip(columns, ("词条", "数值", "档位", "得分"),
                                        (156, 62, 45, 62)):
            self.rows.heading(column, text=label, anchor="w" if column == "stat" else "center")
            self.rows.column(column, width=width, minwidth=width, stretch=column == "stat",
                             anchor="w" if column == "stat" else "center")
        self.rows.tag_configure("main", foreground=ACCENT)
        self.rows.grid(row=3, column=0, sticky="nsew")
        footer = tk.Frame(content, background=BG)
        footer.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        footer.columnconfigure(0, weight=1)
        self.cost = tk.StringVar()
        tk.Label(footer, textvariable=self.cost, bg=BG, fg=MUTED, font=(FONT, 9),
                 anchor="w").grid(row=0, column=0, sticky="ew")
        self.overlay_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            footer, style="Score.TCheckbutton", text="画面内评分", variable=self.overlay_enabled,
            command=self.refresh_overlay,
        ).grid(row=0, column=1, padx=(8, 0))

        actions = tk.Frame(content, background=BG)
        actions.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.update_button = ttk.Button(actions, text="更新角色权重", style="Score.TButton",
                                        command=self.start_template_update)
        self.update_button.pack(side="left")
        self.update_status = tk.StringVar()
        tk.Label(actions, textvariable=self.update_status, bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=(8, 0))

        self.overlay = ScoreOverlay(root)
        root.after(100, self.poll)

    @staticmethod
    def score_card(parent, column, label, color):
        card = tk.Frame(parent, background=PANEL, padx=12, pady=5)
        card.grid(row=0, column=column, sticky="ew", padx=(0, 4) if column == 0 else (4, 0))
        tk.Label(card, text=label, bg=PANEL, fg=MUTED, font=(FONT, 9)).pack(anchor="w")
        value = tk.StringVar(value="—")
        tk.Label(card, textvariable=value, bg=PANEL, fg=color, font=(FONT, 23, "bold")).pack(
            anchor="w"
        )
        return value

    def select_template(self, name):
        self.template = name
        self.template_specified = True
        self.render()

    def start_template_update(self):
        if self.template_update is not None:
            return
        if shutil.which("git") is None:
            self.update_status.set("请先安装 Git")
            return

        output = None
        try:
            output = tempfile.TemporaryFile()
            script = ROOT / "scripts" / "update_xwuid_echo_templates.py"
            process = subprocess.Popen(
                [sys.executable, str(script)], cwd=ROOT,
                stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
            )
        except OSError as error:
            if output is not None:
                output.close()
            self.show_update_error(str(error))
            return

        self.template_update = process, output
        self.update_button.state(["disabled"])
        self.update_status.set("正在拉取和校验…")

    def poll_template_update(self):
        if self.template_update is None:
            return
        process, output = self.template_update
        code = process.poll()
        if code is None:
            return

        self.template_update = None
        self.update_button.state(["!disabled"])
        with output:
            if code != 0:
                output.seek(0)
                details = output.read().decode("utf-8", errors="replace").strip()
                self.show_update_error(details[-1000:] or f"更新脚本退出，错误码 {code}")
                return
        try:
            changed = reload_templates()
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            self.show_update_error(f"无法加载权重文件。当前评分继续使用已加载的权重。\n\n{error}")
            return

        choices = template_names()
        resolved = resolve_template_name(self.template)
        self.template_specified = self.template_specified and resolved == self.template
        self.template = resolved
        self.selector.replace_choices(choices, self.template)
        self.render()
        count = len(choices)
        self.update_status.set(f"已生效 · {count} 套" if changed else f"已是最新 · {count} 套")

    def show_update_error(self, details):
        self.update_status.set("更新失败")
        messagebox.showerror("更新角色权重", details, parent=self.root)

    def poll(self):
        for _ in range(10):
            try:
                update = self.updates.get_nowait()
            except queue.Empty:
                break
            self.status.set(update.status)
            self.game = update.game
            if update.echo is not None or update.clear:
                self.echo = update.echo
                self.render()
        self.poll_template_update()
        self.refresh_overlay()
        self.root.after(100, self.poll)

    def refresh_overlay(self):
        if (self.overlay_enabled.get() and self.game is not None and self.score is not None
                and foreground_game() == self.game):
            self.overlay.show(self.game, self.echo, self.score, self.applied_template_label)
        else:
            self.overlay.hide()

    def render(self):
        self.rows.delete(*self.rows.get_children())
        if self.echo is None:
            self.score = None
            self.current.set("—")
            self.potential.set("—")
            self.double_crit.set("—")
            self.potential_probability.set("—")
            self.cost.set("")
            return

        echo = self.echo
        automatic = self.auto_match.get()
        matched = echo.equipped_template if automatic else None
        template = matched or self.template
        self.applied_template_label = format_template_label(
            template, automatic=matched is not None, user_specified=self.template_specified or not automatic,
        )
        score = calculate_echo_score(template, echo.cost, echo.main_rows, echo.sub_rows)
        self.score = score
        self.current.set(f"{score.current_score:.2f}")
        self.potential.set(f"{score.potential_score:.2f}")
        self.double_crit.set(f"{score.double_crit_probability:.2%}")
        self.potential_probability.set(format_probability(score.potential_score_probability))
        self.cost.set(f"{echo.cost} COST   ·   {self.applied_template_label}")
        for index, (row, points) in enumerate(zip(echo.main_rows + echo.sub_rows, score.row_scores)):
            main = index < len(echo.main_rows)
            tier = "主词条" if main else substat_tier_label(row.stat_name, row.value)
            self.rows.insert("", "end", values=(row.stat_name, row.value_text, tier, f"{points:.2f}"),
                             tags=("main",) if main else ())


def run(template):
    enable_dpi_awareness()
    root = tk.Tk()
    updates = queue.SimpleQueue()
    stop = threading.Event()
    window = ScoreWindow(root, template, updates)
    worker = threading.Thread(target=scan_live, args=(updates, stop), name="Echo OCR")
    worker.start()
    try:
        root.mainloop()
    finally:
        stop.set()
        worker.join()
        if window.template_update is not None:
            _, output = window.template_update
            output.close()
