"""Quick window capture probe. Usage: python grab.py [out.png]"""
import ctypes
import ctypes.wintypes as w
import sys

from PIL import Image

u = ctypes.windll.user32
g = ctypes.windll.gdi32
u.SetProcessDPIAware()

PW_RENDERFULLCONTENT = 0x00000002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", w.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", w.WORD),
        ("biBitCount", w.WORD),
        ("biCompression", w.DWORD),
        ("biSizeImage", w.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", w.DWORD),
        ("biClrImportant", w.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", w.DWORD * 3)]


def find_window(substr="IsekaiWaifuOverlord"):
    found = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

    def cb(h, l):
        n = u.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, buf, n + 1)
            if substr.lower() in buf.value.lower() and u.IsWindowVisible(h):
                found.append((h, buf.value))
        return True

    u.EnumWindows(CB(cb), 0)
    return found


def capture(hwnd, full_content=True):
    r = w.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    width, height = r.right - r.left, r.bottom - r.top
    hdc = u.GetWindowDC(hwnd)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, width, height)
    g.SelectObject(mdc, bmp)
    ok = u.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT if full_content else 0)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB
    buf = ctypes.create_string_buffer(width * height * 4)
    g.GetDIBits(mdc, bmp, 0, height, buf, ctypes.byref(bmi), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB"), bool(ok)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "frame.png"
    wins = find_window()
    if not wins:
        print("window not found")
        raise SystemExit(1)
    hwnd, title = wins[0]
    img, ok = capture(hwnd)
    img.save(out)
    print(f"hwnd={hwnd} title={title!r} size={img.size} printwindow_ok={ok} -> {out}")
