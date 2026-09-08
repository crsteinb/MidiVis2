'''Offline glyph-atlas builder (Plan Part 3.3).

Source: `assets/fonts/Bravura.otf` — the open-license (SIL OFL) SMuFL font
this rewrite adopted instead of hand-drawing vector glyphs (see
FullRewriteStatus.md's Milestone 4 deviations for why: pygame's font loader
takes a font *file* directly, sidestepping the old repo's exact failure mode
of asking the OS for a named font and silently getting nothing if it's
missing — the SIL OFL explicitly permits bundling and redistributing the
font file itself, so there's no "hope the machine has this installed"
step at all).

Output: `assets/atlas/glyphs.png` (one packed RGBA sheet) + `glyphs.json`
(a manifest of {tier: {glyph_name: {x, y, w, h, anchor_x, anchor_y}}}).
Both are checked into the repo like any other asset — nothing needs GUI
font rendering at app startup, and running this script is only needed again
if the glyph list or tier sizes change.

Run with: python tools/build_atlas.py

Tiers: SMuFL fonts use the convention "1 staff space = font size / 4" (a
standard 5-line staff spans 4 spaces = 1 em) — confirmed empirically against
Bravura (a quarter notehead renders exactly `size/4` px tall). Three fixed
staff-space sizes are rasterized ahead of time, covering the app's zoom
range (Plan Part 3.3: "covers the zoom range without needing the current
runtime supersample-then-smoothscale trick") — the renderer picks whichever
tier is closest to the live pixel scale instead of rescaling a glyph bitmap
every frame.
'''
from __future__ import annotations

import json
import os

import pygame

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(REPO_ROOT, 'assets', 'fonts', 'Bravura.otf')
OUT_PNG = os.path.join(REPO_ROOT, 'assets', 'atlas', 'glyphs.png')
OUT_JSON = os.path.join(REPO_ROOT, 'assets', 'atlas', 'glyphs.json')

# staff-space pixel size per tier -- see module docstring.
TIERS: dict[str, int] = {'sm': 14, 'md': 24, 'lg': 44}

# name -> SMuFL codepoint. Deliberately a small, curated set: exactly what
# notation/engraver.py + render/slots/traditional.py need this milestone, not
# the full SMuFL repertoire.
GLYPHS: dict[str, int] = {
    'gClef': 0xE050,
    'fClef': 0xE062,
    'noteheadWhole': 0xE0A2,
    'noteheadHalf': 0xE0A3,
    'noteheadBlack': 0xE0A4,
    'accidentalFlat': 0xE260,
    'accidentalNatural': 0xE261,
    'accidentalSharp': 0xE262,
    'restWhole': 0xE4E3,
    'restHalf': 0xE4E4,
    'restQuarter': 0xE4E5,
    'rest8th': 0xE4E6,
    'rest16th': 0xE4E7,
    'rest32nd': 0xE4E8,
    'flag8thUp': 0xE240,
    'flag8thDown': 0xE241,
    'flag16thUp': 0xE242,
    'flag16thDown': 0xE243,
    'augmentationDot': 0xE1E7,
    **{f'timeSig{d}': 0xE080 + d for d in range(10)},
}

ATLAS_MAX_W = 2048
PADDING = 2


def _render_glyph(font: pygame.font.Font, codepoint: int) -> tuple[pygame.Surface, int, int]:
    '''Render one glyph, cropped tight vertically (x is already tight -- see
    module docstring's derivation), plus its (anchor_x, anchor_y): the pixel
    offset from the cropped surface's top-left to the glyph's SMuFL
    reference point (its logical (0, 0) — e.g. a notehead's center, a clef's
    staff-line anchor). The renderer positions glyphs by this point, not by
    the bitmap's corner.
    '''
    ch = chr(codepoint)
    raw = font.render(ch, True, (255, 255, 255))
    minx, maxx, miny, maxy, _advance = font.metrics(ch)[0]
    ascent = font.get_ascent()
    top = ascent - maxy
    height = max(1, maxy - miny)
    cropped = pygame.Surface((raw.get_width(), height), pygame.SRCALPHA)
    cropped.blit(raw, (0, -top))
    return cropped, -minx, maxy


def _pack(surfaces: list[tuple[str, pygame.Surface]]) -> tuple[pygame.Surface, dict[str, pygame.Rect]]:
    '''Simple shelf packer: sort tallest-first, fill rows up to ATLAS_MAX_W.'''
    ordered = sorted(surfaces, key=lambda kv: kv[1].get_height(), reverse=True)
    placements: dict[str, pygame.Rect] = {}
    x = y = row_h = 0
    for key, surf in ordered:
        w, h = surf.get_size()
        if x + w > ATLAS_MAX_W and x > 0:
            x = 0
            y += row_h + PADDING
            row_h = 0
        placements[key] = pygame.Rect(x, y, w, h)
        x += w + PADDING
        row_h = max(row_h, h)
    atlas_h = y + row_h
    atlas = pygame.Surface((ATLAS_MAX_W, atlas_h), pygame.SRCALPHA)
    for key, surf in ordered:
        atlas.blit(surf, placements[key].topleft)
    return atlas, placements


def build() -> None:
    pygame.init()
    pygame.font.init()

    manifest: dict = {'staff_space_px': TIERS, 'glyphs': {}}
    all_surfaces: list[tuple[str, pygame.Surface]] = []
    anchors: dict[str, tuple[int, int]] = {}

    for tier, staff_space in TIERS.items():
        font_px = max(1, round(staff_space * 4))
        font = pygame.font.Font(FONT_PATH, font_px)
        for name, codepoint in GLYPHS.items():
            surf, ax, ay = _render_glyph(font, codepoint)
            key = f'{name}:{tier}'
            all_surfaces.append((key, surf))
            anchors[key] = (ax, ay)

    atlas, placements = _pack(all_surfaces)

    for key, rect in placements.items():
        name, tier = key.rsplit(':', 1)
        ax, ay = anchors[key]
        manifest['glyphs'].setdefault(name, {})[tier] = {
            'x': rect.x, 'y': rect.y, 'w': rect.width, 'h': rect.height,
            'anchor_x': ax, 'anchor_y': ay,
        }

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    pygame.image.save(atlas, OUT_PNG)
    with open(OUT_JSON, 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    print(f'Wrote {OUT_PNG} ({atlas.get_width()}x{atlas.get_height()}) '
          f'and {OUT_JSON} ({len(GLYPHS)} glyphs x {len(TIERS)} tiers).')


if __name__ == '__main__':
    build()
