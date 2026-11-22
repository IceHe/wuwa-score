"""Live scoring window and background OCR loop."""

from dataclasses import dataclass
import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk

from .capture import capture_game, enable_dpi_awareness
from .recognition import Echo
from .scoring import calculate_echo_score, substat_tier_label, template_names


@dataclass(frozen=True)
class Update:
    status: str
    echo: Echo | None = None
    clear: bool = False


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
            image = capture()
        except OSError:
            publish(Update("暂时无法截取画面，正在重试"))
            stop.wait(0.5)
            continue

        if image is None:
            publish(Update("等待鸣潮切到前台"))
            stop.wait(0.5)
            continue
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
            publish(Update("已识别当前声骸", echo))
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
        self.template = template
        self.template_choices = template_names()

        root.title("wuwa-score · 声骸评分")
        root.configure(background=BG)
        # Start between the two game panels so the window does not cover
        # the stats it needs to capture on a typical single-display setup.
        offset = max(0, (root.winfo_screenwidth() - 390) // 2)
        root.geometry(f"390x410+{offset}+48")
        root.minsize(375, 410)
        root.attributes("-topmost", True)
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
        root.option_add("*TCombobox*Listbox.font", (FONT, 9))

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
        self.template_query = tk.StringVar(value=template)
        self.selector = ttk.Combobox(controls, values=self.template_choices, font=(FONT, 9),
                                     textvariable=self.template_query)
        self.selector.grid(row=0, column=1, sticky="ew")
        self.template_query.trace_add("write", self.filter_templates)
        self.selector.bind("<<ComboboxSelected>>", self.select_template)
        self.selector.bind("<Return>", self.select_template)
        self.selector.bind("<Escape>", self.restore_template)
        self.topmost = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            controls, style="Score.TCheckbutton", text="置顶", variable=self.topmost,
            command=lambda: root.attributes("-topmost", self.topmost.get()),
        ).grid(row=0, column=2, padx=(8, 0))

        self.status = tk.StringVar(value="等待鸣潮切到前台")
        tk.Label(content, textvariable=self.status, bg=BG, fg=MUTED, font=(FONT, 9),
                 anchor="w").grid(row=1, column=0, sticky="ew", pady=(0, 8))

        scores = tk.Frame(content, background=BG)
        scores.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        scores.columnconfigure((0, 1), weight=1, uniform="scores")
        self.current = self.score_card(scores, 0, "当前评分", ACCENT)
        self.potential = self.score_card(scores, 1, "理论最高", TEXT)

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
        self.cost = tk.StringVar()
        tk.Label(content, textvariable=self.cost, bg=BG, fg=MUTED, font=(FONT, 9),
                 anchor="w").grid(row=4, column=0, sticky="ew", pady=(5, 0))
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

    def filter_templates(self, *_):
        query = self.template_query.get().strip().casefold()
        self.selector.configure(values=[
            name for name in self.template_choices if query in name.casefold()
        ])

    def select_template(self, _event):
        entered = self.selector.get().strip()
        matches = self.selector.cget("values")
        if entered in self.template_choices:
            self.template = entered
        elif len(matches) == 1:
            self.template = matches[0]
        self.restore_template()
        self.render()

    def restore_template(self, _event=None):
        self.selector.set(self.template)
        self.selector.configure(values=self.template_choices)

    def poll(self):
        for _ in range(10):
            try:
                update = self.updates.get_nowait()
            except queue.Empty:
                break
            self.status.set(update.status)
            if update.echo is not None or update.clear:
                self.echo = update.echo
                self.render()
        self.root.after(100, self.poll)

    def render(self):
        self.rows.delete(*self.rows.get_children())
        if self.echo is None:
            self.current.set("—")
            self.potential.set("—")
            self.cost.set("")
            return

        echo = self.echo
        score = calculate_echo_score(self.template, echo.cost, echo.main_rows, echo.sub_rows)
        self.current.set(f"{score.current_score:.2f}")
        self.potential.set(f"{score.potential_score:.2f}")
        self.cost.set(f"{echo.cost} COST   ·   主词条按 +25 计分")
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
    ScoreWindow(root, template, updates)
    worker = threading.Thread(target=scan_live, args=(updates, stop), name="Echo OCR")
    worker.start()
    try:
        root.mainloop()
    finally:
        stop.set()
        worker.join()
