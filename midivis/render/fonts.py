'''Lazy font cache — ported verbatim from the old ui/fonts.py. Requires
pygame.font to be initialized (pygame.init()) before first use.
'''
from __future__ import annotations

import pygame

_fonts: dict = {}
_symbol_fonts: dict = {}


def get_fonts() -> dict:
    if not _fonts:
        _fonts['normal'] = pygame.font.SysFont('segoeui', 14)
        _fonts['normal_bold'] = pygame.font.SysFont('segoeui', 14, bold=True)
        _fonts['small'] = pygame.font.SysFont('segoeui', 11)
        _fonts['measure_bars'] = pygame.font.SysFont('segoeui', 14)
    return _fonts


def symbol_font(size: int) -> pygame.font.Font:
    '''Font used for menu glyphs (► submenu arrow, ✓ checkmark surrogate).'''
    if size not in _symbol_fonts:
        for name in ('segoeuisymbol', 'segoemdl2assets', 'symbola', None):
            try:
                _symbol_fonts[size] = pygame.font.SysFont(name, size)
                break
            except Exception:
                pass
    return _symbol_fonts[size]
