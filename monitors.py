"""Monitors with full area and work area (without taskbar), in physical pixels."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import re

try:   # physical pixels instead of scaled values, also at 125 % or 150 %
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def monitors() -> list[dict]:
    """Per monitor: x, y, width, height and the margins of the work area per side."""
    result = []
    PROC = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)

    def each(hmon, hdc, rect, data):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        m, w = mi.rcMonitor, mi.rcWork
        result.append({"x": m.left, "y": m.top, "width": m.right - m.left, "height": m.bottom - m.top,
                       "margins": {"top": w.top - m.top, "bottom": m.bottom - w.bottom,
                                   "left": w.left - m.left, "right": m.right - w.right}})
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(None, None, PROC(each), 0)
    return result


def match_obs_name(name: str) -> dict | None:
    """Monitor for an OBS entry like 'DELL U2421E: 1920x1200 @ 0,0 (...)'."""
    t = re.search(r"(\d+)x(\d+) @ (-?\d+),(-?\d+)", name)
    if not t:
        return None
    w, h, x, y = map(int, t.groups())
    return next((m for m in monitors() if (m["x"], m["y"], m["width"], m["height"]) == (x, y, w, h)), None)


if __name__ == "__main__":
    for m in monitors():
        print(m)
