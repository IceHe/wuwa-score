"""Capture the foreground game client's visible desktop pixels on Windows."""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PIL import ImageGrab


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClientRect.restype = wintypes.BOOL
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.ClientToScreen.restype = wintypes.BOOL


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    bounds: tuple[int, int, int, int]


def enable_dpi_awareness():
    # Per-monitor v2 keeps the coordinates in physical pixels on every display.
    _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def foreground_game():
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None

    class_name = ctypes.create_unicode_buffer(128)
    _user32.GetClassNameW(hwnd, class_name, len(class_name))
    if class_name.value != "UnrealWindow":
        return None
    title = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, title, len(title))
    if title.value.strip().casefold() not in {"鸣潮", "鳴潮", "wuthering waves"}:
        return None

    rect = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    if not _user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    if rect.right < 640 or rect.bottom < 360:
        return None
    return GameWindow(hwnd, (origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom))


def capture_game():
    game = foreground_game()
    if game is None:
        return None
    image = ImageGrab.grab(bbox=game.bounds, all_screens=True)
    if foreground_game() != game:
        return None
    return image, game
