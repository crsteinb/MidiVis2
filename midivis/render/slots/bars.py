'''Piano-roll ("bars") visualization slot. Ported from the old
ui/slots/bars_sheet.py, minus the live-recording note overlay (recording is
Milestone 5) and using the shared VerticalScrollbar widget and
render.widgets.mini_keyboard note geometry instead of locally-duplicated
copies of both (Plan Part 3.4).
'''
from __future__ import annotations

import pygame

from midivis.render.slots.slot_base import SlotBase, draw_handle, HANDLE_W
from midivis.render.widgets.mini_keyboard import FIRST_NOTE, LAST_NOTE, is_black
from midivis.render.widgets.scrollbar import VerticalScrollbar

MEASURES_VISIBLE = 8
PLAYHEAD_RATIO = 0.28
BLACK_KEY_RATIO = 0.55
PIANO_W = 56
SCROLL_W = 10
MIN_WHITE_H = 8


class BarsSlot(SlotBase):
    fixed_height = None   # flexible

    def __init__(self) -> None:
        super().__init__('sheet')
        self._scrollbar = VerticalScrollbar(SCROLL_W)
        self._label_cache: dict = {}

    # ── Scroll geometry ──────────────────────────────────────────────────

    def _scroll_info(self, rect, app):
        roll_h = rect.height
        virtual_h = max(roll_h, self._min_virtual_h())
        scroll_frac = max(0.0, min(1.0, getattr(app, 'bars_scroll', 0.0)))
        has_scroll = self._scrollbar.is_needed(virtual_h, roll_h)
        scroll_px = int(scroll_frac * (virtual_h - roll_h)) if has_scroll else 0
        return virtual_h, scroll_px, has_scroll

    # ── Events ───────────────────────────────────────────────────────────

    def handle_event(self, event, rect, app) -> bool:
        virtual_h, _, _ = self._scroll_info(rect, app)
        track_r = pygame.Rect(rect.right - SCROLL_W, rect.y, SCROLL_W, rect.height)
        frac = max(0.0, min(1.0, getattr(app, 'bars_scroll', 0.0)))
        was_dragging = self._scrollbar.dragging
        new_frac = self._scrollbar.handle_event(event, track_r, virtual_h, rect.height, frac)
        if new_frac is not None:
            app.bars_scroll = new_frac
            return True
        return was_dragging

    # ── Rendering ────────────────────────────────────────────────────────

    def draw(self, screen, rect, app, fonts, settings) -> None:
        small = fonts['small']
        measure_font = fonts.get('measure_bars', small)
        pal = self.get_pal(settings)
        rx, ry, rw, rh = rect.x, rect.y, rect.width, rect.height

        draw_handle(screen, rx, ry, rh, pal)
        rx += HANDLE_W
        rw -= HANDLE_W

        roll_h = rh
        virtual_h, scroll_px, has_scroll = self._scroll_info(rect, app)

        if has_scroll:
            rw -= SCROLL_W

        ry_virtual = ry - scroll_px
        note_top, note_h, _ = self._build_note_layout(virtual_h, ry_virtual)
        active_notes = getattr(app, 'active_notes', set())

        prev_clip = screen.get_clip()
        screen.set_clip(pygame.Rect(rx, ry, rw, roll_h))

        self._draw_piano_strip(screen, rx, ry, roll_h, note_top, note_h, active_notes, pal)

        roll_x = rx + PIANO_W
        roll_w = rw - PIANO_W
        zoom = getattr(app, 'sheet_zoom', 1.0)
        measure_dur = (60.0 / app.bpm) * app.time_sig[0]
        measures_visible = MEASURES_VISIBLE / zoom
        pps = roll_w / (measure_dur * measures_visible)
        playhead = roll_x + int(roll_w * PLAYHEAD_RATIO)

        pygame.draw.rect(screen, pal['bg_roll'], (roll_x, ry, roll_w, roll_h))

        for note in range(FIRST_NOTE, LAST_NOTE + 1, 12):
            ny = int(note_top[note])
            if ry <= ny < ry + roll_h:
                pygame.draw.line(screen, pal['octave'], (roll_x, ny), (roll_x + roll_w, ny))

        for n, t in app.measure_times:
            x = playhead + int((t - app.elapsed) * pps)
            if roll_x <= x <= roll_x + roll_w:
                pygame.draw.line(screen, pal['measure'], (x, ry), (x, ry + roll_h))
                screen.blit(measure_font.render(str(n + 1), True, pal['text_dim']), (x + 2, ry + 2))

        for (s, e, note, _, _) in app.note_events:
            if note not in note_top:
                continue
            x1 = playhead + int((s - app.elapsed) * pps)
            x2 = playhead + int((e - app.elapsed) * pps)
            if x2 < roll_x or x1 > roll_x + roll_w:
                continue
            color = (pal['note_active']
                     if (note in active_notes and s <= app.elapsed < e)
                     else pal['note'])
            nt, nh = note_top[note], note_h[note]
            nr = (max(roll_x, x1), int(nt),
                  max(1, min(roll_x + roll_w, x2) - max(roll_x, x1)),
                  max(1, round(nh)))
            pygame.draw.rect(screen, color, nr)
            if nr[2] > 2 and nr[3] > 2:
                pygame.draw.rect(screen, pal['note_outline'], nr, 1)

        pygame.draw.line(screen, pal['playhead'], (playhead, ry), (playhead, ry + roll_h), 2)
        screen.set_clip(prev_clip)

        if has_scroll:
            track_r = pygame.Rect(rect.right - SCROLL_W, ry, SCROLL_W, roll_h)
            frac = max(0.0, min(1.0, getattr(app, 'bars_scroll', 0.0)))
            self._scrollbar.draw(screen, track_r, virtual_h, roll_h, frac, pal)

    # ── Internal note layout ────────────────────────────────────────────

    @staticmethod
    def _min_virtual_h():
        n_white = sum(1 for n in range(FIRST_NOTE, LAST_NOTE + 1) if not is_black(n))
        n_black = (LAST_NOTE - FIRST_NOTE + 1) - n_white
        return int(n_white * MIN_WHITE_H + n_black * MIN_WHITE_H * BLACK_KEY_RATIO)

    @staticmethod
    def _build_note_layout(roll_h, ry):
        n_white = sum(1 for n in range(FIRST_NOTE, LAST_NOTE + 1) if not is_black(n))
        n_black = (LAST_NOTE - FIRST_NOTE + 1) - n_white
        wh = roll_h / (n_white + n_black * BLACK_KEY_RATIO)
        bh = wh * BLACK_KEY_RATIO
        tops, heights = {}, {}
        cum = 0.0
        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            h = bh if is_black(note) else wh
            heights[note] = h
            tops[note] = ry + roll_h - cum - h
            cum += h
        return tops, heights, wh

    def _get_label_font(self, size):
        if size not in self._label_cache:
            self._label_cache[size] = pygame.font.SysFont('Arial', size)
        return self._label_cache[size]

    def _draw_piano_strip(self, screen, px, ry, visible_h, note_top, note_h, active_notes, pal):
        pygame.draw.rect(screen, pal['piano_bg'], (px, ry, PIANO_W, visible_h))

        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if is_black(note):
                continue
            nt = int(note_top[note])
            nh = max(1, round(note_h[note]))
            if nt + nh <= ry or nt >= ry + visible_h:
                continue
            color = pal['piano_active'] if note in active_notes else pal['piano_white']
            pygame.draw.rect(screen, color, (px, nt, PIANO_W - 1, nh))
            pygame.draw.rect(screen, pal['piano_border'], (px, nt, PIANO_W - 1, nh), 1)

        bk_w = int(PIANO_W * 0.6)
        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if not is_black(note):
                continue
            nt = int(note_top[note])
            nh = max(1, round(note_h[note]))
            if nt + nh <= ry or nt >= ry + visible_h:
                continue
            color = pal['piano_active'] if note in active_notes else pal['piano_black']
            pygame.draw.rect(screen, color, (px, nt, bk_w, nh))

        label_size = max(7, int(note_h.get(60, 10) * 0.7))
        font = self._get_label_font(label_size)
        for note in range(FIRST_NOTE, LAST_NOTE + 1):
            if note % 12 != 0:
                continue
            octave = note // 12 - 1
            surf = font.render(f'C{octave}', True, pal['piano_label'])
            nt = int(note_top[note])
            nh = max(1, round(note_h[note]))
            if nt + nh <= ry or nt >= ry + visible_h:
                continue
            y = nt + nh - surf.get_height() - 1
            x = px + PIANO_W - surf.get_width() - 3
            screen.blit(surf, (x, y))
