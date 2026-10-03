"""Action journal — an audit trail for everything the bot does.

Two reasons this exists rather than a pile of ``print`` calls:

1. A game bot fails *silently*.  A click that lands 8 px off does nothing, the
   loop spins, and you have no idea why.  Logging before/after frames and the
   measured screen change turns "it stopped working" into "click missed by 8 px".
2. Anything that spends in-game currency should be reconstructable afterwards.

Frames are written only when ``keep_frames`` is set, and the directory is capped,
so a long run can't silently fill the disk.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2

from .capture import Frame


@dataclass
class Entry:
    ts: float
    event: str
    screen: str = ""
    confidence: float = 0.0
    action: str = ""
    detail: str = ""
    ok: bool = True
    changed: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


class Journal:
    """Append-only JSONL log, plus optional frame snapshots."""

    def __init__(
        self,
        path: str | Path = "runs/journal.jsonl",
        keep_frames: bool = False,
        frame_dir: str | Path | None = None,
        max_frames: int = 400,
        echo: bool = True,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.frame_dir = Path(frame_dir) if frame_dir else self.path.parent / "frames"
        self.keep_frames = keep_frames
        self.max_frames = max_frames
        self.echo = echo
        self._frames_written = 0
        self._fh = self.path.open("a", encoding="utf-8")

    # -- writing ---------------------------------------------------------- #

    def log(self, entry: Entry) -> Entry:
        self._fh.write(entry.to_json() + "\n")
        self._fh.flush()  # flush per line: a crash must not eat the last action
        if self.echo:
            bits = [f"{entry.event:<10}"]
            if entry.screen:
                bits.append(f"[{entry.screen} {entry.confidence:.2f}]")
            if entry.action:
                bits.append(f"{entry.action}")
            if entry.detail:
                bits.append(f"{entry.detail}")
            if entry.changed is not None:
                bits.append(f"(changed {entry.changed:.1%})")
            if not entry.ok:
                bits.append("!! FAILED")
            print(" ".join(bits))
        return entry

    def event(self, event: str, **kw) -> Entry:
        return self.log(Entry(ts=time.time(), event=event, **kw))

    def save_frame(self, frame: Frame, tag: str) -> Path | None:
        """Persist a frame if frame-keeping is on and the cap allows it."""
        if not self.keep_frames or self._frames_written >= self.max_frames:
            return None
        self.frame_dir.mkdir(parents=True, exist_ok=True)
        path = self.frame_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{self._frames_written:05d}-{tag}.png"
        cv2.imwrite(str(path), frame.image)
        self._frames_written += 1
        return path

    def prune_frames(self) -> int:
        """Keep only the newest ``max_frames`` files.  Returns how many went."""
        if not self.frame_dir.exists():
            return 0
        files = sorted(self.frame_dir.glob("*.png"))
        excess = len(files) - self.max_frames
        for f in files[: max(0, excess)]:
            f.unlink()
        return max(0, excess)

    def clear_frames(self) -> None:
        if self.frame_dir.exists():
            shutil.rmtree(self.frame_dir)

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class NullJournal(Journal):
    """Same interface, writes nothing.  For tests and dry sweeps."""

    def __init__(self):
        self.path = Path("<null>")
        self.frame_dir = Path("<null>")
        self.keep_frames = False
        self.max_frames = 0
        self.echo = False
        self._frames_written = 0
        self._fh = None

    def log(self, entry: Entry) -> Entry:
        return entry

    def event(self, event: str, **kw) -> Entry:
        return Entry(ts=time.time(), event=event, **kw)

    def save_frame(self, frame, tag):
        return None

    def close(self):
        pass
