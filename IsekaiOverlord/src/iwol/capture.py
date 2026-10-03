"""Frame capture backends.

Every backend returns a :class:`Frame` — a BGR numpy array plus the screen
rectangle it came from.  Keeping the origin in the frame means every coordinate
downstream (OCR boxes, template hits, click targets) is in *screen* space and
can be handed straight to an actuator.

The important property: on Windows the PrintWindow backend captures a window
**without it being focused or even visible**.  Verified working on the Unity
D3D12 build of Isekai Waifu Overlord (2560x1440, full colour, no flash).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
from dataclasses import dataclass
from typing import Protocol

import numpy as np

# --------------------------------------------------------------------------- #
# Frame
# --------------------------------------------------------------------------- #


@dataclass
class Frame:
    """A captured image plus its position in screen coordinates."""

    image: np.ndarray  # BGR, HxWx3, uint8
    origin: tuple[int, int] = (0, 0)  # (left, top) of the image in screen space

    @property
    def width(self) -> int:
        return self.image.shape[1]

    @property
    def height(self) -> int:
        return self.image.shape[0]

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def to_screen(self, x: int, y: int) -> tuple[int, int]:
        """Map an image-local point to screen coordinates."""
        return (self.origin[0] + int(x), self.origin[1] + int(y))

    def to_local(self, x: int, y: int) -> tuple[int, int]:
        """Map a screen point to image-local coordinates."""
        return (int(x) - self.origin[0], int(y) - self.origin[1])

    def crop(self, box: tuple[int, int, int, int]) -> "Frame":
        """Crop with an (x, y, w, h) box in image-local coordinates.

        The returned frame's origin is updated, so descendant coordinates stay
        correct in screen space.
        """
        x, y, w, h = box
        sub = self.image[y : y + h, x : x + w].copy()
        return Frame(sub, (self.origin[0] + x, self.origin[1] + y))

    def is_blank(self, threshold: float = 6.0) -> bool:
        """True when the frame is a single flat colour (failed capture)."""
        return bool(self.image.std() < threshold)


# --------------------------------------------------------------------------- #
# Backend protocol
# --------------------------------------------------------------------------- #


class CaptureBackend(Protocol):
    name: str

    def grab(self) -> Frame: ...

    def size(self) -> tuple[int, int]: ...

    def close(self) -> None: ...


# --------------------------------------------------------------------------- #
# Windows: PrintWindow
# --------------------------------------------------------------------------- #

PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def find_windows(substr: str) -> list[tuple[int, str]]:
    """All visible top-level windows whose title contains ``substr``."""
    user32 = ctypes.windll.user32
    found: list[tuple[int, str]] = []
    enum_cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if substr.lower() in buf.value.lower() and user32.IsWindowVisible(hwnd):
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(enum_cb(callback), 0)
    return found


class PrintWindowBackend:
    """Capture a Windows top-level window via ``PrintWindow``.

    Works while the window is unfocused and/or occluded — so the bot can watch
    the game without stealing the desktop.  (Only *clicking* may need focus.)
    """

    name = "printwindow"

    def __init__(self, title_substr: str = "IsekaiWaifuOverlord", hwnd: int | None = None):
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        try:
            self._user32.SetProcessDPIAware()
        except Exception:
            pass
        if hwnd is None:
            matches = find_windows(title_substr)
            if not matches:
                raise LookupError(f"no visible window matching {title_substr!r}")
            hwnd, title = matches[0]
            self.title = title
        else:
            self.title = ""
        self.hwnd = hwnd
        # Cached DC/bitmap sized to the window; recreated if the size changes.
        self._cache: tuple[int, int, int, int] | None = None  # w, h, memdc, bmp

    def _window_rect(self) -> tuple[int, int, int, int]:
        rect = wintypes.RECT()
        self._user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)

    def _ensure_cache(self, width: int, height: int):
        if self._cache and self._cache[0] == width and self._cache[1] == height:
            return
        self._release_cache()
        hdc = self._user32.GetWindowDC(self.hwnd)
        memdc = self._gdi32.CreateCompatibleDC(hdc)
        bmp = self._gdi32.CreateCompatibleBitmap(hdc, width, height)
        self._gdi32.SelectObject(memdc, bmp)
        self._user32.ReleaseDC(self.hwnd, hdc)
        self._cache = (width, height, memdc, bmp)

    def _release_cache(self):
        if self._cache:
            _, _, memdc, bmp = self._cache
            self._gdi32.DeleteObject(bmp)
            self._gdi32.DeleteDC(memdc)
            self._cache = None

    def size(self) -> tuple[int, int]:
        left, top, right, bottom = self._window_rect()
        return (right - left, bottom - top)

    def grab(self) -> Frame:
        left, top, right, bottom = self._window_rect()
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            raise RuntimeError(f"window {self.hwnd} has degenerate size {width}x{height}")

        self._ensure_cache(width, height)
        _, _, memdc, bmp = self._cache

        # SRCCOPY first so a PrintWindow failure leaves *something* (usually
        # black) rather than stale content from a previous frame.
        self._gdi32.BitBlt(memdc, 0, 0, width, height, memdc, 0, 0, 0x00FF0062)  # BLACKNESS
        ok = self._user32.PrintWindow(self.hwnd, memdc, PW_RENDERFULLCONTENT)
        if not ok:
            # Some windows only respond to the flagless call.
            ok = self._user32.PrintWindow(self.hwnd, memdc, 0)
        if not ok:
            raise RuntimeError(f"PrintWindow failed for hwnd {self.hwnd}")

        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # negative => top-down rows
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        buf = ctypes.create_string_buffer(width * height * 4)
        self._gdi32.GetDIBits(memdc, bmp, 0, height, buf, ctypes.byref(bmi), 0)
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 4)
        bgr = arr[:, :, :3].copy()  # drop alpha, already BGR order
        return Frame(bgr, (left, top))

    def close(self):
        self._release_cache()


# --------------------------------------------------------------------------- #
# Any-screen: mss  (full desktop, or an arbitrary rectangle)
# --------------------------------------------------------------------------- #


class MssBackend:
    """Capture a region of the desktop.  Works on Windows/macOS/Linux/Xvfb."""

    name = "mss"

    def __init__(self, monitor: int | dict | None = None):
        import mss  # imported lazily so headless callers don't need it

        # mss renamed the class; prefer the new name when it exists.
        factory = getattr(mss, "MSS", None) or getattr(mss, "mss")
        self._sct = factory()
        if monitor is None:
            monitor = self._sct.monitors[1]  # primary display
        if isinstance(monitor, int):
            monitor = self._sct.monitors[monitor]
        self._region = monitor

    def size(self) -> tuple[int, int]:
        return (self._region["width"], self._region["height"])

    def grab(self) -> Frame:
        shot = self._sct.grab(self._region)
        arr = np.frombuffer(shot.rgb, dtype=np.uint8).reshape(shot.height, shot.width, 3)
        bgr = arr[:, :, ::-1].copy()  # RGB -> BGR
        return Frame(bgr, (self._region["left"], self._region["top"]))

    def close(self):
        self._sct.close()


# --------------------------------------------------------------------------- #
# A frame loaded from disk (used to develop vision code offline from a tour)
# --------------------------------------------------------------------------- #


class ImageBackend:
    """Replay a still image as a capture backend — handy for tests."""

    name = "image"

    def __init__(self, path: str, origin: tuple[int, int] = (0, 0)):
        import cv2

        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(path)
        self._frame = Frame(img, origin)

    def size(self) -> tuple[int, int]:
        return self._frame.size

    def grab(self) -> Frame:
        return Frame(self._frame.image.copy(), self._frame.origin)

    def close(self):
        pass


def open_backend(target: str = "IsekaiWaifuOverlord"):
    """Best available backend for ``target``: a window title, or 'screen'."""
    if target.lower() in {"screen", "desktop"}:
        return MssBackend()
    return PrintWindowBackend(target)
