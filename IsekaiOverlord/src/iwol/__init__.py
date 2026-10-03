"""iwoL — a computer-vision bot that plays Isekai: Waifu Overlord.

Layers, bottom to top:

``capture``   grab the game window (works while it's unfocused)
``ocr``       read text out of a frame
``vision``    template matching, fingerprints, change detection
``screens``   decide which screen we're on, from data-driven specs
``economy``   decide which upgrade is worth buying (pure logic)
``routines``  one handler per screen: act, then verify
``actuator``  the only thing allowed to touch the mouse
``journal``   audit trail of everything that happened
``brain``     the loop that ties it together, with the safety gates

Start with ``Brain``; everything else is a component it owns.
"""

from .actuator import (
    Aborted,
    Actuator,
    ActionResult,
    DryRunActuator,
    PostMessageActuator,
    SendInputActuator,
    SentinelActuator,
)
from .brain import Brain, BrainConfig, Budget, Context, RoutineOutcome, RunReport
from .capture import (
    CaptureBackend,
    Frame,
    ImageBackend,
    MssBackend,
    PrintWindowBackend,
    find_windows,
    open_backend,
)
from .economy import Building, Purchase, income_per_second, plan_upgrades, project_income
from .journal import Entry, Journal, NullJournal
from .ocr import Ocr, TextLine, parse_number
from .screens import Classification, Region, ScreenClassifier, ScreenSpec
from .vision import (
    Match,
    color_distance,
    color_profile,
    diff_ratio,
    dominant_colors,
    match_all,
    match_template,
    mean_brightness,
    phash,
    phash_distance,
)

__version__ = "0.1.0"

__all__ = [
    "Aborted",
    "Actuator",
    "ActionResult",
    "Brain",
    "BrainConfig",
    "Budget",
    "Building",
    "CaptureBackend",
    "Classification",
    "Context",
    "DryRunActuator",
    "Entry",
    "Frame",
    "ImageBackend",
    "Journal",
    "Match",
    "MssBackend",
    "NullJournal",
    "Ocr",
    "PostMessageActuator",
    "PrintWindowBackend",
    "Purchase",
    "Region",
    "RoutineOutcome",
    "RunReport",
    "ScreenClassifier",
    "ScreenSpec",
    "SendInputActuator",
    "SentinelActuator",
    "TextLine",
    "color_distance",
    "color_profile",
    "diff_ratio",
    "dominant_colors",
    "find_windows",
    "income_per_second",
    "match_all",
    "match_template",
    "mean_brightness",
    "open_backend",
    "parse_number",
    "phash",
    "phash_distance",
    "plan_upgrades",
    "project_income",
]
