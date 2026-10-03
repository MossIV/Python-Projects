"""Routines — one handler per screen.

A routine is deliberately dumb and short: it reads what the screen shows, acts
with the actuator, and reports what it spent.  All the "wait and check it
worked" logic lives in the brain, so a routine never needs its own timing
hacks and every action gets verified the same way.
"""

from .village import VillageRoutine

__all__ = ["VillageRoutine"]
