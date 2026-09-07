'''Shared piano-key geometry (Plan Part 3.4's "MiniKeyboard").

The old repo computed "is this note a black key" / "which white-key slot does
it occupy" independently in ui/slots/keyboard.py (the interactive bottom
keyboard) and ui/slots/bars_sheet.py (the piano-roll's vertical key strip).
This module is the one shared source for that geometry.

Deliberately *not* a single widget that also owns drawing: the two callers
render fundamentally different things from this geometry (a horizontal,
click/drag-to-play interactive keyboard vs. a vertical, display-only lane
background sized to the piano-roll's note rows) — forcing one draw() to cover
both would be an awkward abstraction for no real reuse. What's actually
duplicated, and now isn't, is the note-range/black-key/white-key-index math.
'''
from __future__ import annotations

FIRST_NOTE = 21   # A0
LAST_NOTE = 108   # C8

_BLACK_PITCH_CLASSES = (1, 3, 6, 8, 10)
_WHITE_KEY_OFFSETS = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]

NUM_WHITE_KEYS = sum(1 for n in range(FIRST_NOTE, LAST_NOTE + 1)
                      if (n % 12) not in _BLACK_PITCH_CLASSES)


def is_black(note: int) -> bool:
    return (note % 12) in _BLACK_PITCH_CLASSES


def white_index(note: int) -> int:
    '''Index of this note's white key among all white keys from C0, used to
    position both white and black keys along the keyboard's white-key grid.
    '''
    return (note // 12) * 7 + _WHITE_KEY_OFFSETS[note % 12]
