"""Input actuation — the only module allowed to touch the mouse or keyboard.

Three backends, one interface:

* :class:`DryRunActuator` — **the default**.  Records what it *would* do and
  returns the same results as a real backend.  Every routine is developed and
  tested against this, so nothing moves until a human explicitly arms it.
* :class:`PostMessageActuator` — posts ``WM_*`` messages straight to a window
  handle.  Fully background, but Unity generally reads raw input and ignores
  synthetic messages, so this is the "try it first, don't rely on it" option.
* :class:`SendInputActuator` — injects real hardware events.  Reliable, but the
  target window must be foreground, so the desktop is occupied while it runs.

``SentinelActuator`` wraps any backend with a kill switch and a coordinate
sanity check, because a bot that clicks outside the game window is worse than
no bot at all.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #


@dataclass
class ActionResult:
    ok: bool
    action: str
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok


# --------------------------------------------------------------------------- #
# interface
# --------------------------------------------------------------------------- #


@runtime_checkable
class Actuator(Protocol):
    """Everything the brain is allowed to ask of the machine."""

    name: str
    dry_run: bool

    def click(self, x: int, y: int, button: str = "left") -> ActionResult: ...

    def move(self, x: int, y: int) -> ActionResult: ...

    def drag(
        self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3, button: str = "left"
    ) -> ActionResult: ...

    def scroll(self, x: int, y: int, clicks: int) -> ActionResult: ...

    def key(self, key: str, presses: int = 1) -> ActionResult: ...

    def close(self) -> None: ...


# --------------------------------------------------------------------------- #
# dry run
# --------------------------------------------------------------------------- #


@dataclass
class DryRunActuator:
    """Arms-length stand-in: logs intent, touches nothing.

    Deliberately behaves like a successful backend so routines can be driven
    end-to-end in tests and in front of a human before anything is armed.
    """

    name: str = "dryrun"
    dry_run: bool = True
    actions: list[tuple[str, tuple]] = field(default_factory=list)

    def _record(self, action: str, *args) -> ActionResult:
        self.actions.append((action, args))
        return ActionResult(True, action, f"dry-run {action}{args}")

    def click(self, x: int, y: int, button: str = "left") -> ActionResult:
        return self._record("click", x, y, button)

    def move(self, x: int, y: int) -> ActionResult:
        return self._record("move", x, y)

    def drag(self, x1, y1, x2, y2, duration=0.3, button="left") -> ActionResult:
        return self._record("drag", x1, y1, x2, y2)

    def scroll(self, x: int, y: int, clicks: int) -> ActionResult:
        return self._record("scroll", x, y, clicks)

    def key(self, key: str, presses: int = 1) -> ActionResult:
        return self._record("key", key, presses)

    def close(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# coordinate helpers
# --------------------------------------------------------------------------- #


def virtual_screen_metrics() -> tuple[int, int, int, int]:
    """(left, top, width, height) of the whole virtual desktop."""
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Screen point -> client point.  ``WM_*`` messages use client coordinates."""
    pt = wintypes.POINT(int(x), int(y))
    ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return (pt.x, pt.y)


# --------------------------------------------------------------------------- #
# SendInput
# --------------------------------------------------------------------------- #

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_VK = {
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
}


class SendInputActuator:
    """Real hardware-level input injection.

    The target window must be foreground for a game to receive these — call
    :meth:`focus` first.  If ``hwnd`` is given, coordinates are validated
    against the window so a stale coordinate can't click the desktop.
    """

    name = "sendinput"
    dry_run = False

    def __init__(self, hwnd: int | None = None):
        self.hwnd = hwnd
        self._user32 = ctypes.windll.user32
        self._user32.SetProcessDPIAware()
        self._send = self._user32.SendInput
        self._send.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
        self._send.restype = wintypes.UINT

    # -- internals -------------------------------------------------------- #

    def _emit(self, *inputs: _INPUT) -> bool:
        arr = (_INPUT * len(inputs))(*inputs)
        return self._send(len(inputs), arr, ctypes.sizeof(_INPUT)) == len(inputs)

    def _to_absolute(self, x: int, y: int) -> tuple[int, int]:
        vx, vy, vw, vh = virtual_screen_metrics()
        nx = int(round((x - vx) * 65535 / max(vw - 1, 1)))
        ny = int(round((y - vy) * 65535 / max(vh - 1, 1)))
        return (max(0, min(65535, nx)), max(0, min(65535, ny)))

    def _mouse_event(self, flags: int, x: int = 0, y: int = 0, data: int = 0) -> _INPUT:
        ev = _INPUT(type=INPUT_MOUSE)
        ev.mi = _MOUSEINPUT(dx=x, dy=y, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=0)
        return ev

    def _check(self, x: int, y: int) -> str | None:
        """Return an error string if the point is outside the target window."""
        if self.hwnd is None:
            return None
        left, top, right, bottom = window_rect(self.hwnd)
        if not (left <= x < right and top <= y < bottom):
            return f"({x},{y}) outside window {self.hwnd} [{left},{top}-{right},{bottom}]"
        return None

    # -- api -------------------------------------------------------------- #

    def focus(self) -> bool:
        if self.hwnd is None:
            return True
        u = self._user32
        if u.IsIconic(self.hwnd):
            u.ShowWindow(self.hwnd, 9)  # SW_RESTORE
        ok = bool(u.SetForegroundWindow(self.hwnd))
        time.sleep(0.25)  # let the game notice focus before input lands
        return ok

    def move(self, x: int, y: int) -> ActionResult:
        err = self._check(x, y)
        if err:
            return ActionResult(False, "move", err)
        nx, ny = self._to_absolute(x, y)
        ok = self._emit(self._mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny))
        return ActionResult(ok, "move", f"({x},{y})")

    def click(self, x: int, y: int, button: str = "left") -> ActionResult:
        err = self._check(x, y)
        if err:
            return ActionResult(False, "click", err)
        down, up = {
            "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
            "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
            "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
        }[button]
        nx, ny = self._to_absolute(x, y)
        ok = self._emit(
            self._mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny),
        )
        ok = ok and self._emit(self._mouse_event(down), self._mouse_event(up))
        return ActionResult(ok, "click", f"{button} ({x},{y})")

    def drag(self, x1, y1, x2, y2, duration: float = 0.3, button: str = "left") -> ActionResult:
        down, up = {
            "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
            "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        }[button]
        if not self.move(x1, y1).ok:
            return ActionResult(False, "drag", f"start ({x1},{y1}) rejected")
        self._emit(self._mouse_event(down))
        steps = max(2, int(duration * 60))
        for i in range(1, steps + 1):
            t = i / steps
            self.move(int(x1 + (x2 - x1) * t), int(y1 + (y2 - y1) * t))
            time.sleep(duration / steps)
        self._emit(self._mouse_event(up))
        return ActionResult(True, "drag", f"({x1},{y1})->({x2},{y2})")

    def scroll(self, x: int, y: int, clicks: int) -> ActionResult:
        self.move(x, y)
        ok = self._emit(self._mouse_event(MOUSEEVENTF_WHEEL, data=(clicks * 120) & 0xFFFFFFFF))
        return ActionResult(ok, "scroll", f"{clicks} at ({x},{y})")

    def key(self, key: str, presses: int = 1) -> ActionResult:
        vk = _VK.get(key.lower())
        if vk is None:
            return ActionResult(False, "key", f"unknown key {key!r}")
        ok = True
        for _ in range(presses):
            down = _INPUT(type=INPUT_KEYBOARD)
            down.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
            up = _INPUT(type=INPUT_KEYBOARD)
            up.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            ok = ok and self._emit(down, up)
        return ActionResult(ok, "key", f"{key} x{presses}")

    def close(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# PostMessage
# --------------------------------------------------------------------------- #

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101


def _make_lparam(x: int, y: int) -> int:
    return (int(y) << 16) | (int(x) & 0xFFFF)


class PostMessageActuator:
    """Background clicking by posting window messages.

    Cheapest possible option — nothing steals focus.  But Unity games typically
    read raw input state and ignore posted messages, so **test before relying on
    it**: :meth:`probe` reports whether the target window reacted at all.
    """

    name = "postmessage"
    dry_run = False

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._user32 = ctypes.windll.user32
        self._user32.SetProcessDPIAware()

    def _post(self, msg: int, wparam: int, lparam: int) -> bool:
        return bool(self._user32.PostMessageW(self.hwnd, msg, wparam, lparam))

    def click(self, x: int, y: int, button: str = "left") -> ActionResult:
        cx, cy = screen_to_client(self.hwnd, x, y)
        down, up = (WM_LBUTTONDOWN, WM_LBUTTONUP) if button == "left" else (WM_RBUTTONDOWN, WM_RBUTTONUP)
        lp = _make_lparam(cx, cy)
        ok = self._post(WM_MOUSEMOVE, 0, lp)
        ok = self._post(down, 1, lp) and ok
        time.sleep(0.05)
        ok = self._post(up, 0, lp) and ok
        return ActionResult(ok, "click", f"{button} client({cx},{cy})")

    def move(self, x: int, y: int) -> ActionResult:
        cx, cy = screen_to_client(self.hwnd, x, y)
        return ActionResult(self._post(WM_MOUSEMOVE, 0, _make_lparam(cx, cy)), "move", f"client({cx},{cy})")

    def drag(self, x1, y1, x2, y2, duration: float = 0.3, button: str = "left") -> ActionResult:
        down = WM_LBUTTONDOWN if button == "left" else WM_RBUTTONDOWN
        up = WM_LBUTTONUP if button == "left" else WM_RBUTTONUP
        cx1, cy1 = screen_to_client(self.hwnd, x1, y1)
        cx2, cy2 = screen_to_client(self.hwnd, x2, y2)
        self._post(WM_MOUSEMOVE, 0, _make_lparam(cx1, cy1))
        self._post(down, 1, _make_lparam(cx1, cy1))
        steps = max(2, int(duration * 60))
        for i in range(1, steps + 1):
            t = i / steps
            self._post(WM_MOUSEMOVE, 1, _make_lparam(int(cx1 + (cx2 - cx1) * t), int(cy1 + (cy2 - cy1) * t)))
            time.sleep(duration / steps)
        self._post(up, 0, _make_lparam(cx2, cy2))
        return ActionResult(True, "drag", f"client({cx1},{cy1})->({cx2},{cy2})")

    def scroll(self, x: int, y: int, clicks: int) -> ActionResult:
        cx, cy = screen_to_client(self.hwnd, x, y)
        ok = self._post(WM_MOUSEWHEEL, ((clicks * 120) & 0xFFFF) << 16, _make_lparam(cx, cy))
        return ActionResult(ok, "scroll", f"{clicks}")

    def key(self, key: str, presses: int = 1) -> ActionResult:
        vk = _VK.get(key.lower())
        if vk is None:
            return ActionResult(False, "key", f"unknown key {key!r}")
        ok = True
        for _ in range(presses):
            ok = self._post(WM_KEYDOWN, vk, 0) and ok
            ok = self._post(WM_KEYUP, vk, 0) and ok
        return ActionResult(ok, "key", f"{key} x{presses}")

    def close(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# kill switch
# --------------------------------------------------------------------------- #


class Aborted(RuntimeError):
    """Raised when the kill switch has been pulled."""


@dataclass
class SentinelActuator:
    """Wraps a backend with a kill switch.

    The kill switch is a callable returning True when the bot must stop at once.
    The brain also checks it between steps; having the actuator check it too
    means a long drag can't run to completion after a stop is requested.
    """

    inner: Actuator
    should_stop: callable = lambda: False

    name: str = "sentinel"

    @property
    def dry_run(self) -> bool:
        return self.inner.dry_run

    def _guard(self) -> None:
        if self.should_stop():
            raise Aborted("kill switch pulled")

    def click(self, x: int, y: int, button: str = "left") -> ActionResult:
        self._guard()
        return self.inner.click(x, y, button)

    def move(self, x: int, y: int) -> ActionResult:
        self._guard()
        return self.inner.move(x, y)

    def drag(self, x1, y1, x2, y2, duration: float = 0.3, button: str = "left") -> ActionResult:
        self._guard()
        return self.inner.drag(x1, y1, x2, y2, duration, button)

    def scroll(self, x: int, y: int, clicks: int) -> ActionResult:
        self._guard()
        return self.inner.scroll(x, y, clicks)

    def key(self, key: str, presses: int = 1) -> ActionResult:
        self._guard()
        return self.inner.key(key, presses)

    def close(self) -> None:
        self.inner.close()
