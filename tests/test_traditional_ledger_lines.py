'''Regression test for a real bug: `_draw_ledger_lines` was being called with
the note's *absolute* diatonic step (from midi/spelling.py) instead of a
step relative to the staff's own bottom line. Since absolute treble/bass
steps are always well above the function's `>= 10` "needs a ledger line"
threshold, this drew bogus ledger lines around essentially every note,
regardless of its actual staff position (reported by the user as "bars"
rendered above the staff for notes that don't need them, worst on dense
16th-note passages).
'''
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import unittest

import pygame

from midivis.render.slots.traditional import _draw_ledger_lines

pygame.init()
pygame.display.set_mode((10, 10))


def _count_lit_pixels(surface, color):
    w, h = surface.get_size()
    return sum(1 for x in range(w) for y in range(h) if surface.get_at((x, y))[:3] == color)


class DrawLedgerLinesTest(unittest.TestCase):
    WHITE = (255, 255, 255)

    def _blank_surface(self):
        surf = pygame.Surface((200, 200))
        surf.fill((0, 0, 0))
        return surf

    def test_note_within_the_staff_gets_no_ledger_lines(self):
        surf = self._blank_surface()
        # Relative step 4 = the staff's middle line -- well within range.
        _draw_ledger_lines(surf, 100, 4, 150, self.WHITE, notehead_w=24)
        self.assertEqual(_count_lit_pixels(surf, self.WHITE), 0)

    def test_note_just_above_the_staff_gets_no_ledger_lines(self):
        surf = self._blank_surface()
        # Relative step 9 = just above the top line (step 8) but not yet at
        # the first ledger-line position (step 10) -- no ledger line needed.
        _draw_ledger_lines(surf, 100, 9, 150, self.WHITE, notehead_w=24)
        self.assertEqual(_count_lit_pixels(surf, self.WHITE), 0)

    def test_note_above_the_staff_gets_a_ledger_line(self):
        surf = self._blank_surface()
        _draw_ledger_lines(surf, 100, 10, 150, self.WHITE, notehead_w=24)
        self.assertGreater(_count_lit_pixels(surf, self.WHITE), 0)

    def test_note_below_the_staff_gets_a_ledger_line(self):
        surf = self._blank_surface()
        _draw_ledger_lines(surf, 100, -2, 150, self.WHITE, notehead_w=24)
        self.assertGreater(_count_lit_pixels(surf, self.WHITE), 0)

    def test_passing_an_absolute_step_would_wrongly_draw_ledger_lines(self):
        # Demonstrates the actual bug shape: a typical absolute treble step
        # (e.g. 30, E4 -- comfortably the staff's own bottom line) is >= 10,
        # so calling this with an absolute step instead of a relative one
        # draws ledger lines for a note that needs none. This test exists to
        # make the distinction between "relative" and "absolute" explicit,
        # not to assert the (wrong) behavior is desirable.
        surf = self._blank_surface()
        _draw_ledger_lines(surf, 100, 30, 150, self.WHITE, notehead_w=24)
        self.assertGreater(_count_lit_pixels(surf, self.WHITE), 0)


if __name__ == '__main__':
    unittest.main()
