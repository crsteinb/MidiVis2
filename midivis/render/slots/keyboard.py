'''On-screen 88-key piano slot. Ported from the old ui/slots/keyboard.py,
using the shared note-geometry helpers in render.widgets.mini_keyboard
instead of a locally-duplicated copy (Plan Part 3.4).
'''
from __future__ import annotations

import pygame

from midivis.render.slots.slot_base import SlotBase, draw_handle, HANDLE_W
from midivis.render.widgets.mini_keyboard import (
    FIRST_NOTE, LAST_NOTE, NUM_WHITE_KEYS, is_black, white_index,
)

KEYBOARD_H = 110


class KeyboardSlot(SlotBase):
    fixed_height = KEYBOARD_H

    def __init__(self) -> None:
        super().__init__('keyboard')
        self._dragging = False
        self._mouse_note = None

    # ── Note geometry ────────────────────────────────────────────────────

    def _key_dims(self, rect):
        kx = rect.x + HANDLE_W
        kw = rect.width - HANDLE_W
        fwi = white_index(FIRST_NOTE)
        wkw = kw / NUM_WHITE_KEYS
        wkh = rect.height - 4
        bkw = wkw * 0.6
        bkh = wkh * 0.6
        return kx, fwi, wkw, wkh, bkw, bkh

    def hit_test(self, pos, rect):
        px, py = pos
        rx, ry, rw, rh = rect.x, rect.y, rect.width, rect.height
        kx, fwi, wkw, wkh, bkw, bkh = self._key_dims(rect)
        if px < kx or px >= rx + rw or py < ry or py >= ry + rh:
            return None
        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if is_black(note):
                wi = white_index(note) - fwi
                x = kx + wi * wkw + wkw - bkw / 2
                if pygame.Rect(x, ry, bkw, bkh).collidepoint(px, py):
                    return note
        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if not is_black(note):
                wi = white_index(note) - fwi
                if pygame.Rect(kx + wi * wkw, ry, wkw - 1, wkh).collidepoint(px, py):
                    return note
        return None

    # ── Events ───────────────────────────────────────────────────────────

    def handle_event(self, event, rect, app) -> bool:
        pedal = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)

        if event.type == pygame.KEYUP and event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
            # Releasing the sustain-pedal modifier releases every note it's
            # currently holding — a held note was otherwise only ever released
            # by clicking it again, which reads as "stuck" for any note latched
            # via a drag/glissando rather than a single deliberate click.
            for note in list(app.kb_notes):
                app.kb_note_off(note)
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if rect.collidepoint(event.pos):
                note = self.hit_test(event.pos, rect)
                if note is not None:
                    if pedal:
                        if note in app.kb_notes:
                            app.kb_note_off(note)
                        else:
                            app.kb_note_on(note)
                    else:
                        app.kb_note_on(note)
                    self._dragging = True
                    self._mouse_note = note
                    return True

        elif event.type == pygame.MOUSEMOTION and self._dragging:
            note = self.hit_test(event.pos, rect)
            if note != self._mouse_note:
                if pedal:
                    if note is not None:
                        if note in app.kb_notes:
                            app.kb_note_off(note)
                        else:
                            app.kb_note_on(note)
                else:
                    if self._mouse_note is not None:
                        app.kb_note_off(self._mouse_note)
                    if note is not None:
                        app.kb_note_on(note)
                self._mouse_note = note
            return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging:
                self._dragging = False
                if not pedal and self._mouse_note is not None:
                    app.kb_note_off(self._mouse_note)
                self._mouse_note = None
                return True

        return False

    # ── Rendering ────────────────────────────────────────────────────────

    def draw(self, screen, rect, app, fonts, settings) -> None:
        pal = self.get_pal(settings)
        active_notes = app.active_notes | app.kb_notes
        kx, fwi, wkw, wkh, bkw, bkh = self._key_dims(rect)

        draw_handle(screen, rect.x, rect.y, rect.height, pal)
        pygame.draw.rect(screen, pal['key_bg'], (kx, rect.y, rect.width - HANDLE_W, rect.height))

        def key_rect(note):
            wi = white_index(note) - fwi
            if is_black(note):
                x = kx + wi * wkw + wkw - bkw / 2
                return pygame.Rect(x, rect.y, bkw, bkh)
            return pygame.Rect(kx + wi * wkw, rect.y, wkw - 1, wkh)

        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if not is_black(note):
                r = key_rect(note)
                c = pal['key_active'] if note in active_notes else pal['key_white']
                pygame.draw.rect(screen, c, r)
                pygame.draw.rect(screen, pal['key_black'], r, 1)

        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if is_black(note):
                r = key_rect(note)
                c = pal['key_active'] if note in active_notes else pal['key_black']
                pygame.draw.rect(screen, c, r)

        font = fonts.get('small') if fonts else None
        if font:
            for note in range(FIRST_NOTE, LAST_NOTE + 1):
                if note % 12 == 0:
                    octave = note // 12 - 1
                    r = key_rect(note)
                    active = note in active_notes
                    color = pal['key_marker_active'] if active else pal['key_marker']
                    surf = font.render(f'C{octave}', True, color)
                    screen.blit(surf, (r.centerx - surf.get_width() // 2,
                                        r.bottom - surf.get_height() - 2))
