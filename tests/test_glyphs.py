'''Covers GlyphAtlas's tinted-surface cache — added after a real perf bug:
blit() re-tinted (Surface.copy() + a blend fill) on every single call, so a
busy traditional-view frame allocated dozens of throwaway surfaces 60 times
a second, showing up as periodic stutter during playback (reported as the
view "freezing for a moment and then jumping ahead").
'''
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import unittest

import pygame

from midivis.notation.glyphs import GlyphAtlas

pygame.init()
pygame.display.set_mode((10, 10))


class TintCacheTest(unittest.TestCase):
    def setUp(self):
        self.atlas = GlyphAtlas()
        self.screen = pygame.Surface((200, 200))

    def test_same_name_tier_color_reuses_the_cached_surface(self):
        self.atlas.blit(self.screen, 'noteheadBlack', 'md', 50, 50, color=(80, 140, 220))
        self.assertEqual(len(self.atlas._tint_cache), 1)
        self.atlas.blit(self.screen, 'noteheadBlack', 'md', 60, 60, color=(80, 140, 220))
        self.assertEqual(len(self.atlas._tint_cache), 1)   # no new entry

    def test_different_colors_get_distinct_cache_entries(self):
        self.atlas.blit(self.screen, 'noteheadBlack', 'md', 50, 50, color=(80, 140, 220))
        self.atlas.blit(self.screen, 'noteheadBlack', 'md', 50, 50, color=(220, 60, 60))
        self.assertEqual(len(self.atlas._tint_cache), 2)

    def test_different_glyphs_get_distinct_cache_entries(self):
        self.atlas.blit(self.screen, 'noteheadBlack', 'md', 50, 50, color=(80, 140, 220))
        self.atlas.blit(self.screen, 'noteheadHalf', 'md', 50, 50, color=(80, 140, 220))
        self.assertEqual(len(self.atlas._tint_cache), 2)

    def test_uncolored_blit_does_not_populate_the_tint_cache(self):
        self.atlas.blit(self.screen, 'noteheadBlack', 'md', 50, 50)
        self.assertEqual(len(self.atlas._tint_cache), 0)


if __name__ == '__main__':
    unittest.main()
