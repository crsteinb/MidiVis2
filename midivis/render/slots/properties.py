'''Properties slot — file metadata panel with expand/collapse. Ported from
the old ui/slots/properties.py, minus the recording-state indicator and the
MIDI-input-device column (both Milestone 5 — recording and input/ don't
exist yet).
'''
from __future__ import annotations

import os

import pygame

from midivis.midi.instruments import drum_kit_name, gm_name
from midivis.render.slots.slot_base import SlotBase, draw_handle, HANDLE_W

MIN_H = 36
BTN_W = 22
ROW_H = 18
PAD = 8


class PropertiesSlot(SlotBase):
    fixed_height = MIN_H

    def __init__(self) -> None:
        super().__init__('properties')

    # ── Height helpers ───────────────────────────────────────────────────

    def expanded_height(self, app) -> int:
        instruments = getattr(app, 'instruments', {})
        n_rows = 0
        if app.loaded:
            n_rows = 6   # File, Size, Tracks, Key, Time, Tempo — see row() calls below
            if instruments:
                unique_count = len({p for progs in instruments.values() for p in progs})
                n_rows += 1 + unique_count
        n_rows = max(n_rows, 1)
        return MIN_H + PAD + n_rows * ROW_H + PAD

    # ── Events ───────────────────────────────────────────────────────────

    def handle_event(self, event, rect, app):
        '''Returns "properties_toggle" if the +/- button was clicked, else False.'''
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and _btn_rect(rect).collidepoint(event.pos)):
            app.properties_expanded = not app.properties_expanded
            return 'properties_toggle'
        return False

    # ── Rendering ────────────────────────────────────────────────────────

    def draw(self, screen, rect, app, fonts, settings) -> None:
        rx, ry, rw, rh = rect.x, rect.y, rect.width, rect.height
        pal = self.get_pal(settings)
        small = fonts['small']
        font = fonts['normal']

        draw_handle(screen, rx, ry, rh, pal)
        ix = rx + HANDLE_W
        iw = rw - HANDLE_W

        pygame.draw.rect(screen, pal['props_bg'], (ix, ry, iw, rh))

        btn = _btn_rect(rect)
        pygame.draw.rect(screen, pal['props_btn_bg'], btn, border_radius=3)
        cx, cy = btn.centerx, btn.centery
        fg = pal['props_btn_fg']
        arm, thick = 5, 2
        pygame.draw.rect(screen, fg, (cx - arm, cy - thick // 2, arm * 2, thick))
        if not getattr(app, 'properties_expanded', False):
            pygame.draw.rect(screen, fg, (cx - thick // 2, cy - arm, thick, arm * 2))

        if app.loaded:
            fname = os.path.basename(app.midi_path)
            num, den = app.time_sig
            stats = f'{app.key_sig or "—"}  {num}/{den}  {int(app.bpm)} BPM'
            text_y = ry + (MIN_H - font.get_height()) // 2
            name_surf = font.render(fname, True, pal['props_text'])
            screen.blit(name_surf, (ix + PAD, text_y))
            screen.blit(font.render(stats, True, pal['props_dim']),
                        (ix + PAD + name_surf.get_width() + 8, text_y))
        else:
            screen.blit(small.render('No file loaded', True, pal['props_dim']),
                        (ix + PAD, ry + (MIN_H - small.get_height()) // 2))

        if not getattr(app, 'properties_expanded', False):
            return

        pygame.draw.line(screen, pal['props_sep'], (ix, ry + MIN_H), (ix + iw, ry + MIN_H))

        y = ry + MIN_H + PAD

        def row(label, value):
            nonlocal y
            if y + ROW_H > ry + rh:
                return
            screen.blit(small.render(label, True, pal['props_dim']), (ix + PAD, y))
            screen.blit(small.render(value, True, pal['props_text']), (ix + PAD + 76, y))
            y += ROW_H

        if app.loaded:
            fname = os.path.basename(app.midi_path)
            try:
                fsize = _fmt_size(os.path.getsize(app.midi_path))
            except OSError:
                fsize = '?'
            num, den = app.time_sig

            row('File', fname)
            row('Size', fsize)
            row('Tracks', str(len(app.tracks)))
            row('Key', app.key_sig or '—')
            row('Time', f'{num}/{den}')
            row('Tempo', f'{int(app.bpm)} BPM')

            instruments = getattr(app, 'instruments', {})
            track_channels = getattr(app, 'track_channels', {})
            if instruments and y + ROW_H <= ry + rh:
                seen, unique = set(), []
                for tid, progs in instruments.items():
                    is_drum = 9 in track_channels.get(tid, set())
                    for p in progs:
                        name = drum_kit_name(p) if is_drum else gm_name(p)
                        if name not in seen:
                            seen.add(name)
                            unique.append(name)
                screen.blit(small.render('Instruments', True, pal['props_dim']), (ix + PAD, y))
                y += ROW_H
                for name in unique:
                    if y + ROW_H > ry + rh:
                        break
                    screen.blit(small.render(name, True, pal['props_text']), (ix + PAD + 8, y))
                    y += ROW_H


def _btn_rect(rect):
    return pygame.Rect(rect.right - BTN_W - 6, rect.y + (MIN_H - 20) // 2, BTN_W, 20)


def _fmt_size(n_bytes):
    if n_bytes < 1024:
        return f'{n_bytes} B'
    if n_bytes < 1048576:
        return f'{n_bytes / 1024:.1f} KB'
    return f'{n_bytes / 1048576:.1f} MB'
