'''Regression test for a rendering bug: the sharp/flat accidental glyph
overlapped the notehead in the traditional (sheet music) view. GlyphAtlas
anchors every glyph (including accidentals) at its own left edge
(anchor_x=0), so `blit()`'s x parameter IS the glyph's left edge -- but
`_draw_chord_heads` only subtracted half the accidental's width when
positioning it, as if centering it there, leaving its right half drawn on
top of the notehead. Reported by the user from a screenshot: a sharp
visibly overlapping the note it modified.
'''
import os

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import unittest

import pygame

from midivis.notation.glyphs import GlyphAtlas
from midivis.render.slots.traditional import GLYPH_TIER, TraditionalSlot

pygame.init()
pygame.display.set_mode((10, 10))


class AccidentalDoesNotOverlapNoteheadTest(unittest.TestCase):
    def setUp(self):
        self.atlas = GlyphAtlas()
        self.slot = TraditionalSlot(atlas=self.atlas)
        self.screen = pygame.Surface((400, 400))
        self.pal = {'trad_note_outline': (0, 0, 0)}

    def _blit_lefts(self, accidental):
        calls = {}
        real_blit = self.atlas.blit

        def recording_blit(screen, name, tier, x, y, color=None):
            calls[name] = x
            real_blit(screen, name, tier, x, y, color=color)

        self.atlas.blit = recording_blit
        try:
            positions = [(0, 100, 60, accidental)]
            self.slot._draw_chord_heads(self.screen, 200, positions, 'quarter', (255, 255, 255), self.pal)
        finally:
            self.atlas.blit = real_blit
        return calls

    def test_sharp_sits_entirely_left_of_the_notehead(self):
        lefts = self._blit_lefts(accidental=1)
        sharp_width = self.atlas.get('accidentalSharp', GLYPH_TIER).surface.get_width()
        self.assertLessEqual(lefts['accidentalSharp'] + sharp_width, lefts['noteheadBlack'])

    def test_flat_sits_entirely_left_of_the_notehead(self):
        lefts = self._blit_lefts(accidental=-1)
        flat_width = self.atlas.get('accidentalFlat', GLYPH_TIER).surface.get_width()
        self.assertLessEqual(lefts['accidentalFlat'] + flat_width, lefts['noteheadBlack'])

    def test_no_accidental_draws_only_the_notehead(self):
        lefts = self._blit_lefts(accidental=0)
        self.assertEqual(set(lefts), {'noteheadBlack'})


if __name__ == '__main__':
    unittest.main()
