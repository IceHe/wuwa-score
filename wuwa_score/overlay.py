"""Draw Echo scores in a transparent, click-through Windows window."""

import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import font

from .scoring import substat_tier


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL

GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

TRANSPARENT = "#010203"
BACKGROUND = "#121C28"
WHITE = "#F0F5FA"
MAIN_COLOR = "#7CE5D4"
TIER_COLOR = "#A8D7FF"
LOW_TIER_COLOR = "#A8D7B1"
HIGH_TIER_COLOR = "#FFD187"
FONT = "Microsoft YaHei UI"


class ScoreOverlay:
    def __init__(self, root):
        self.window = tk.Toplevel(root, background=TRANSPARENT)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-transparentcolor", TRANSPARENT)
        self.window.geometry("1x1+0+0")
        self.canvas = tk.Canvas(self.window, width=1, height=1, background=TRANSPARENT,
                                highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill="both", expand=True)

        # Tk's widget handle is inside its native top-level wrapper.
        self.window.update_idletasks()
        self.hwnd = _user32.GetAncestor(self.window.winfo_id(), GA_ROOT)
        styles = _user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        styles &= ~WS_EX_APPWINDOW
        styles |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        _user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, styles)
        self.drawn = None
        self.text_font = None

    def show(self, game, echo, score, template):
        state = (game, echo, score, template)
        if self.drawn == state:
            return
        if not echo.anchors:
            self.hide()
            return

        left, top, right, bottom = game.bounds
        width, height = right - left, bottom - top
        self._paint(width, height, echo, score, template)
        if self.drawn is None:
            self.window.deiconify()
        # SetWindowPos accepts absolute positions on displays with negative
        # coordinates and leaves the game as the foreground window.
        if _user32.SetWindowPos(self.hwnd, HWND_TOPMOST, left, top, width, height,
                                SWP_NOACTIVATE | SWP_SHOWWINDOW):
            self.drawn = state
        else:
            self.window.withdraw()
            self.drawn = None

    def hide(self):
        if self.drawn is not None:
            self.window.withdraw()
            self.drawn = None

    def _paint(self, width, height, echo, score, template):
        self.canvas.delete("all")
        size = max(12, min(24, round(height * 0.019)))
        self.text_font = font.Font(root=self.canvas, family=FONT, size=-size, weight="bold")
        padding = max(4, round(size * 0.33))
        line_height = self.text_font.metrics("linespace")
        badge_half = (line_height + 2) // 2
        score_width = self.text_font.measure("00.00")
        tier_width = self.text_font.measure("8档")
        badge_width = score_width + tier_width + padding * 3
        stat_left = round(min(anchor.left for anchor in echo.anchors) * width)
        badge_right = max(badge_width + 2, stat_left - padding)

        rows = echo.main_rows + echo.sub_rows
        for index, (row, anchor, points) in enumerate(zip(rows, echo.anchors, score.row_scores)):
            y = round(anchor.center_y * height)
            main = index < len(echo.main_rows)
            tier = None if main else substat_tier(row.stat_name, row.value)
            row_width = badge_width if tier else score_width + padding * 2
            self.canvas.create_rectangle(badge_right - row_width, y - badge_half,
                                         badge_right, y + badge_half, fill=BACKGROUND, width=0)
            self.canvas.create_text(badge_right - padding, y, text=f"{points:.2f}",
                                    anchor="e", fill=MAIN_COLOR if main else WHITE, font=self.text_font)
            if tier:
                rank, total = tier
                color = HIGH_TIER_COLOR if rank == total else LOW_TIER_COLOR if rank == 1 else TIER_COLOR
                self.canvas.create_text(badge_right - badge_width + padding, y, text=f"{rank}档",
                                        anchor="w", fill=color, font=self.text_font)

        summary = (
            (f"当前 {score.current_score:.2f}   理论最高 {score.potential_score:.2f}", MAIN_COLOR),
            (f"双暴概率 {score.double_crit_probability:.2%}", HIGH_TIER_COLOR),
            (template, WHITE),
        )
        summary_width = max(self.text_font.measure(text) for text, _ in summary) + padding * 4
        center = width // 2
        top = round(height * 0.095)
        self.canvas.create_rectangle(center - summary_width // 2, top,
                                     center + summary_width // 2, top + line_height * len(summary) + padding * 2,
                                     fill=BACKGROUND, width=0)
        for index, (text, color) in enumerate(summary):
            self.canvas.create_text(center, top + padding + line_height * index, text=text,
                                    anchor="n", fill=color, font=self.text_font)
