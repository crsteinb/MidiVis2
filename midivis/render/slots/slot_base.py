'''Base class for all slot panels (Plan Part 3.4).

Subclasses set fixed_height (int px) or leave it None to be a flexible
"fill remaining space" slot — SlotManager now supports more than one such
slot at a time (see slot_manager.py's fix for the old single-flex-slot
limitation).
'''
from __future__ import annotations

import pygame

from midivis.render.theme import get_theme

HANDLE_W = 12
C_DRAG_LINE = (100, 120, 180)


class SlotBase:
    fixed_height: int | None = None

    def __init__(self, slot_id: str) -> None:
        self.slot_id = slot_id

    def handle_event(self, event, rect, app) -> bool | str:
        return False

    def draw(self, screen, rect, app, fonts, settings) -> None:
        pass

    def get_pal(self, settings: dict) -> dict:
        return get_theme(settings)


def draw_handle(screen, rx, ry, rh, pal) -> None:
    pygame.draw.rect(screen, pal['handle'], (rx, ry, HANDLE_W, rh))
    dash_h = 12
    dash_x = rx + HANDLE_W // 2
    dash_y = ry + (rh - dash_h) // 2
    pygame.draw.line(screen, pal['handle_dash'],
                      (dash_x, dash_y), (dash_x, dash_y + dash_h - 1), 2)
