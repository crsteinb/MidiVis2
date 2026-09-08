'''Two behaviors added after a user-reported screenshot of overlapping
noteheads reading as one indistinct blob (a two-note chord a step apart):

1. Each notehead gets a thin outline traced from its own alpha silhouette
   (GlyphAtlas.draw_outline), so overlapping same-color noteheads keep a
   visible boundary between them instead of blending together.
2. Draw order for a chord's noteheads goes highest-pitch-first / lowest-
   pitch-last, so the lower note -- always the more visually "important"
   one to keep legible -- ends up drawn on top instead of partly covered by
   whatever was drawn after it.
'''
import os

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import unittest

import pygame

from midivis.notation.glyphs import GlyphAtlas
from midivis.render.slots.traditional import TraditionalSlot

pygame.init()
pygame.display.set_mode((10, 10))


class NoteheadStackingOrderTest(unittest.TestCase):
    def setUp(self):
        self.atlas = GlyphAtlas()
        self.slot = TraditionalSlot(atlas=self.atlas)
        self.screen = pygame.Surface((400, 400))
        self.pal = {'trad_note_outline': (0, 0, 0)}

    def _draw_order(self, positions):
        '''Each position has a distinct `y` here, so recording draw_outline's
        y argument (called once per note, right after its notehead blit)
        doubles as an identifier for which note was drawn in which order.
        '''
        seen = []
        real_outline = self.atlas.draw_outline

        def recording_outline(screen, name, tier, x, y, color, width=1):
            seen.append(y)
            real_outline(screen, name, tier, x, y, color, width=width)

        self.atlas.draw_outline = recording_outline
        try:
            self.slot._draw_chord_heads(self.screen, 200, positions, 'quarter', (255, 255, 255), self.pal)
        finally:
            self.atlas.draw_outline = real_outline
        return seen

    def test_lower_note_is_drawn_last(self):
        # A "second" interval: two notes a step apart, distinct midi note
        # numbers. (step, y, midi_note, accidental)
        high = (4, 100, 64, 0)
        low = (3, 106, 62, 0)
        self.assertEqual(self._draw_order([high, low]), [100, 106])

    def test_order_is_independent_of_input_order(self):
        high = (4, 100, 64, 0)
        low = (3, 106, 62, 0)
        self.assertEqual(self._draw_order([low, high]), [100, 106])   # still high-first, low-last


class NoteheadOutlineTest(unittest.TestCase):
    def setUp(self):
        self.atlas = GlyphAtlas()
        self.slot = TraditionalSlot(atlas=self.atlas)
        self.screen = pygame.Surface((400, 400))

    def test_each_notehead_gets_an_outline_in_the_theme_color(self):
        pal = {'trad_note_outline': (11, 22, 33)}
        calls = []
        real_outline = self.atlas.draw_outline

        def recording_outline(screen, name, tier, x, y, color, width=1):
            calls.append((name, color))
            real_outline(screen, name, tier, x, y, color, width=width)

        self.atlas.draw_outline = recording_outline
        try:
            positions = [(0, 100, 60, 0), (3, 106, 64, 0)]
            self.slot._draw_chord_heads(self.screen, 200, positions, 'quarter', (255, 255, 255), pal)
        finally:
            self.atlas.draw_outline = real_outline

        self.assertEqual(len(calls), 2)
        for name, color in calls:
            self.assertEqual(name, 'noteheadBlack')
            self.assertEqual(color, (11, 22, 33))


class DrawOutlineTest(unittest.TestCase):
    '''GlyphAtlas.draw_outline itself: traces and caches a glyph's actual
    silhouette rather than an approximate bounding box.
    '''

    def setUp(self):
        self.atlas = GlyphAtlas()
        self.screen = pygame.Surface((200, 200))

    def test_outline_points_are_cached_after_first_use(self):
        self.assertEqual(len(self.atlas._outline_cache), 0)
        self.atlas.draw_outline(self.screen, 'noteheadBlack', 'md', 50, 50, (255, 0, 0))
        self.assertEqual(len(self.atlas._outline_cache), 1)
        self.atlas.draw_outline(self.screen, 'noteheadBlack', 'md', 60, 60, (255, 0, 0))
        self.assertEqual(len(self.atlas._outline_cache), 1)   # no new entry

    def test_outline_traces_the_glyphs_actual_shape_not_a_fixed_box(self):
        sharp_points = self.atlas._outline_points('accidentalSharp', 'md')
        flat_points = self.atlas._outline_points('accidentalFlat', 'md')
        self.assertGreaterEqual(len(sharp_points), 4)
        self.assertNotEqual(sharp_points, flat_points)   # distinct glyphs, distinct silhouettes


if __name__ == '__main__':
    unittest.main()
