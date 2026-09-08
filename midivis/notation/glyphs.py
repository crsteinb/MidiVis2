'''GlyphAtlas: runtime loader for the sprite atlas tools/build_atlas.py
generates (Plan Part 3.3).

Loads the packed PNG once and returns `pygame.Surface.subsurface()` regions
by (glyph name, tier) — no font lookups, no OS-font dependency, no
silent-omission failure mode (a missing glyph/tier raises KeyError
immediately at first use, rather than the old traditional_sheet.py's clef
rendering, which just... didn't draw anything if `segoeuisymbol` lacked the
codepoint).
'''
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import pygame

_DEFAULT_ATLAS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'assets', 'atlas')


@dataclass(frozen=True)
class Glyph:
    surface: pygame.Surface   # subsurface of the atlas sheet
    anchor_x: int              # pixel offset from surface's left edge to the
    anchor_y: int               # glyph's SMuFL reference point (its logical origin)


class GlyphAtlas:
    def __init__(self, atlas_dir: str = _DEFAULT_ATLAS_DIR) -> None:
        with open(os.path.join(atlas_dir, 'glyphs.json')) as f:
            manifest = json.load(f)
        self.staff_space_px: dict[str, int] = manifest['staff_space_px']
        self._sheet = pygame.image.load(os.path.join(atlas_dir, 'glyphs.png')).convert_alpha()
        self._glyphs = manifest['glyphs']
        self._cache: dict[tuple[str, str], Glyph] = {}
        self._tint_cache: dict[tuple[str, str, tuple[int, int, int]], pygame.Surface] = {}

    def tiers(self) -> list[str]:
        '''Tier names sorted by ascending staff-space size.'''
        return sorted(self.staff_space_px, key=lambda t: self.staff_space_px[t])

    def nearest_tier(self, staff_space_px: float) -> str:
        return min(self.staff_space_px, key=lambda t: abs(self.staff_space_px[t] - staff_space_px))

    def get(self, name: str, tier: str) -> Glyph:
        key = (name, tier)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        entry = self._glyphs[name][tier]
        rect = pygame.Rect(entry['x'], entry['y'], entry['w'], entry['h'])
        glyph = Glyph(surface=self._sheet.subsurface(rect),
                       anchor_x=entry['anchor_x'], anchor_y=entry['anchor_y'])
        self._cache[key] = glyph
        return glyph

    def _tinted(self, name: str, tier: str, glyph: Glyph,
                 color: tuple[int, int, int]) -> pygame.Surface:
        '''Cached per (name, tier, color) — a naive `blit()` re-tinted a
        fresh `Surface.copy()` on *every single call*, so a busy traditional-
        view frame (every notehead/accidental/rest/flag/dot re-tinted from
        one of only a handful of theme colors) allocated and blended dozens
        of throwaway surfaces 60 times a second. That churn is exactly the
        kind of thing that shows up as periodic GC-driven stutter — reported
        as the view "freezing for a moment and then jumping ahead" during
        playback, since the audio clock (wall-clock, per Milestone 2) keeps
        advancing through a render hitch instead of pausing for it. The
        color set actually used is small and theme-driven (a handful of RGB
        tuples per palette), so this cache stays small and bounded.
        '''
        key = (name, tier, color)
        cached = self._tint_cache.get(key)
        if cached is not None:
            return cached
        tinted = glyph.surface.copy()
        # Glyphs are rasterized white-on-transparent; RGBA_MULT scales RGB
        # down to `color` while leaving each pixel's own alpha (anti-
        # aliasing) untouched.
        tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self._tint_cache[key] = tinted
        return tinted

    def blit(self, screen: pygame.Surface, name: str, tier: str, x: int, y: int,
              color: tuple[int, int, int] | None = None) -> None:
        '''Blit a glyph so that its SMuFL reference point lands at (x, y).'''
        glyph = self.get(name, tier)
        pos = (x - glyph.anchor_x, y - glyph.anchor_y)
        if color is None:
            screen.blit(glyph.surface, pos)
        else:
            screen.blit(self._tinted(name, tier, glyph, color), pos)
