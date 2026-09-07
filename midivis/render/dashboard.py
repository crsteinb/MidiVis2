'''Left-panel dashboard — file open/new, playback controls, track list with
per-track mute. Ported from the old ui/dashboard.py, trimmed to Milestone 3's
scope: no record-arm panel, no view-mode toggle (traditional notation is
Milestone 4), no per-track delete (tied to the recording workflow, Milestone
5). Built on the shared Button widget instead of a copy of it (Plan Part
3.4); the track dropdown is themed via midivis.render.theme like everything
else, closing the "Track dropdown bypasses the theme system" bug Plan Part 2
called out in the old repo.
'''
from __future__ import annotations

import math

import mido
import pygame

from midivis import settings as cfg
from midivis.render.theme import get_theme
from midivis.render.widgets.button import Button


# ─── Icons ────────────────────────────────────────────────────────────────

def _icon_new(screen, rect, enabled):
    cx, cy = rect.left + 18, rect.centery
    c = (140, 185, 230) if enabled else (55, 72, 90)
    pts = [(cx - 8, cy - 9), (cx + 4, cy - 9), (cx + 9, cy - 4), (cx + 9, cy + 9), (cx - 8, cy + 9)]
    pygame.draw.polygon(screen, c, pts)
    pygame.draw.lines(screen, tuple(min(v + 40, 255) for v in c), True, pts, 1)
    pc = (255, 255, 255) if enabled else (80, 80, 80)
    pygame.draw.line(screen, pc, (cx, cy - 2), (cx, cy + 3), 2)
    pygame.draw.line(screen, pc, (cx - 2, cy + 1), (cx + 3, cy + 1), 2)


def _icon_open(screen, rect, enabled):
    cx, cy = rect.left + 18, rect.centery
    c = (180, 160, 55) if enabled else (80, 72, 35)
    pts = [(cx - 9, cy + 6), (cx - 9, cy - 4), (cx - 3, cy - 4), (cx - 3, cy - 7),
           (cx + 9, cy - 7), (cx + 9, cy + 6)]
    pygame.draw.polygon(screen, c, pts)
    pygame.draw.lines(screen, (min(c[0] + 40, 255), min(c[1] + 40, 255), c[2]), True, pts, 1)


def _icon_play(screen, rect, enabled):
    cx, cy = rect.left + 18, rect.centery
    c = (0, 190, 65) if enabled else (0, 70, 28)
    pygame.draw.circle(screen, c, (cx, cy), 11)
    pygame.draw.polygon(screen, (255, 255, 255) if enabled else (60, 60, 60),
                         [(cx - 4, cy - 6), (cx - 4, cy + 6), (cx + 6, cy)])


def _icon_pause(screen, rect, enabled):
    cx, cy = rect.left + 18, rect.centery
    c = (210, 160, 30) if enabled else (80, 62, 18)
    pygame.draw.rect(screen, c, (cx - 7, cy - 8, 5, 16))
    pygame.draw.rect(screen, c, (cx + 2, cy - 8, 5, 16))


def _icon_reset(screen, rect, enabled):
    '''Circular arrow: an arc plus a triangular arrowhead at its start point,
    the tip pointing along the arc's direction of travel.
    '''
    cx, cy = rect.centerx, rect.centery
    c = (80, 150, 220) if enabled else (35, 60, 90)
    r = 7
    pygame.draw.arc(screen, c, (cx - r, cy - r, r * 2, r * 2),
                     math.radians(60), math.radians(330), 2)
    a = math.radians(60)
    tx, ty = cx + r * math.cos(a), cy - r * math.sin(a)
    tang_x, tang_y = -math.sin(a), -math.cos(a)   # direction of travel at the arc's start
    perp_x, perp_y = -tang_y, tang_x              # rotate 90 degrees -- the base of the arrowhead
    sz, w = 5, 2.5
    tip = (tx + sz * tang_x, ty + sz * tang_y)
    p1 = (tx + w * perp_x, ty + w * perp_y)
    p2 = (tx - w * perp_x, ty - w * perp_y)
    pygame.draw.polygon(screen, c, [tip, p1, p2])


def _icon_tracks(screen, rect, enabled):
    cx, cy = rect.left + 18, rect.centery
    c = (120, 185, 140) if enabled else (50, 72, 55)
    for i in range(3):
        pygame.draw.line(screen, c, (cx - 9, cy - 5 + i * 5), (cx + 7, cy - 5 + i * 5), 2)
    pygame.draw.line(screen, c, (cx + 5, cy + 5), (cx + 9, cy + 9), 2)
    pygame.draw.line(screen, c, (cx + 9, cy + 9), (cx + 13, cy + 5), 2)


def _create_empty_midi(path: str) -> None:
    mf = mido.MidiFile(type=1, ticks_per_beat=480)
    t = mido.MidiTrack()
    mf.tracks.append(t)
    t.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    t.append(mido.MetaMessage('time_signature', numerator=4, denominator=4,
                               clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0))
    t.append(mido.MetaMessage('end_of_track', time=0))
    mf.save(path)


# ─── Track dropdown ───────────────────────────────────────────────────────

class _TrackDropdown:
    ROW_H = 22
    DROP_W = 210
    MAX_ROWS = 12
    PAD = 5

    def __init__(self, button_rect, left_w):
        self.button_rect = pygame.Rect(button_rect)
        self._left_w = left_w
        self.open = False
        self.scroll_off = 0
        self._hover_row = -1

    def toggle(self, enabled):
        if enabled:
            self.open = not self.open
            if self.open:
                self.scroll_off = 0

    def close(self):
        self.open = False

    def collidepoint(self, pos, tracks):
        return self.open and self._panel_rect(len(tracks)).collidepoint(pos)

    def _sorted_tracks(self, app):
        tc = app.track_channels
        melodic = sorted((tid, name) for tid, name in app.tracks.items() if 9 not in tc.get(tid, set()))
        drums = sorted((tid, name) for tid, name in app.tracks.items() if 9 in tc.get(tid, set()))
        return melodic + drums, len(melodic)

    def _panel_rect(self, n_tracks):
        visible = min(n_tracks + 2, self.MAX_ROWS)
        h = visible * self.ROW_H + self.PAD * 2 + 4
        y = min(self.button_rect.top, pygame.display.get_surface().get_height() - h)
        return pygame.Rect(self._left_w, y, self.DROP_W, h)

    def _row_at(self, pos, n_tracks):
        panel = self._panel_rect(n_tracks)
        if not panel.collidepoint(pos):
            return None
        local_y = pos[1] - panel.top - self.PAD
        return None if local_y < 0 else local_y // self.ROW_H

    def handle_event(self, event, app) -> bool:
        if not self.open:
            return False
        sorted_trks, _ = self._sorted_tracks(app)
        n_tracks = len(sorted_trks)
        panel = self._panel_rect(n_tracks)
        max_off = max(0, n_tracks - (self.MAX_ROWS - 2))
        self.scroll_off = min(self.scroll_off, max_off)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if not panel.collidepoint(event.pos):
                self.close()
                return True
            if event.button == 1:
                row = self._row_at(event.pos, n_tracks)
                if row is not None:
                    if row == 0:
                        app.set_all_tracks(True)
                    elif row == 1:
                        app.set_all_tracks(False)
                    else:
                        idx = row - 2 + self.scroll_off
                        if 0 <= idx < len(sorted_trks):
                            app.toggle_track(sorted_trks[idx][0])
            elif event.button == 4:
                self.scroll_off = max(0, self.scroll_off - 1)
            elif event.button == 5:
                self.scroll_off = min(max_off, self.scroll_off + 1)
            return True

        if event.type == pygame.MOUSEMOTION:
            row = self._row_at(event.pos, n_tracks)
            self._hover_row = row if panel.collidepoint(event.pos) and row is not None else -1
            return False

        return False

    def draw(self, screen, app, font, pal):
        if not self.open:
            return
        sorted_trks, n_melodic = self._sorted_tracks(app)
        n_tracks = len(sorted_trks)
        panel = self._panel_rect(n_tracks)
        all_checked = len(app.enabled_tracks) == n_tracks and n_tracks > 0
        none_checked = len(app.enabled_tracks) == 0

        pygame.draw.rect(screen, pal['track_bg'], panel, border_radius=5)
        pygame.draw.rect(screen, pal['track_border'], panel, 1, border_radius=5)

        fixed = [('All', all_checked), ('None', none_checked)]
        track_page = sorted_trks[self.scroll_off: self.scroll_off + self.MAX_ROWS - 2]
        all_rows = fixed + [(name, tid in app.enabled_tracks) for tid, name in track_page]

        for i, (label, checked) in enumerate(all_rows):
            ry = panel.top + self.PAD + i * self.ROW_H
            hover = (i == self._hover_row)
            if hover:
                pygame.draw.rect(screen, pal['track_row_hov'],
                                  (panel.left + 2, ry, panel.width - 4, self.ROW_H - 1), border_radius=3)
            cb = pygame.Rect(panel.left + 8, ry + 4, 13, 13)
            pygame.draw.rect(screen, pal['track_bg'], cb, border_radius=2)
            pygame.draw.rect(screen, pal['track_border'], cb, 1, border_radius=2)
            if checked:
                pygame.draw.lines(screen, pal['track_check'], False,
                                   [(cb.left + 2, cb.centery), (cb.left + 5, cb.bottom - 3),
                                    (cb.right - 2, cb.top + 2)], 2)
            c = pal['track_text_hov'] if hover else pal['track_text']
            screen.blit(font.render(label, True, c), (panel.left + 27, ry + 4))

        sep_y = panel.top + self.PAD + 2 * self.ROW_H - 1
        pygame.draw.line(screen, pal['track_sep'], (panel.left + 4, sep_y), (panel.right - 4, sep_y))

        n_drums = n_tracks - n_melodic
        if n_melodic > 0 and n_drums > 0:
            melodic_visible = max(0, n_melodic - self.scroll_off)
            if 0 < melodic_visible < (self.MAX_ROWS - 2):
                dsep_row = 2 + melodic_visible
                dsep_y = panel.top + self.PAD + dsep_row * self.ROW_H
                if panel.top < dsep_y <= panel.bottom:
                    pygame.draw.line(screen, pal['track_sep'],
                                      (panel.left + 4, dsep_y - 1), (panel.right - 14, dsep_y - 1))
                    lbl = font.render('Drums', True, pal['menu_dim'])
                    screen.blit(lbl, (panel.left + 27, dsep_y - lbl.get_height()))


# ─── Dashboard ──────────────────────────────────────────────────────────────

class Dashboard:
    _BTN_W = 130
    _BTN_H = 42
    _RST_W = 26
    _BTN_X = 10

    def __init__(self, left_w: int, menu_h: int) -> None:
        self._lw = left_w
        self._mh = menu_h
        y0 = menu_h

        # +30 (not the old repo's +16) for the first button's top: the "MIDI VIS"
        # title above it is only 6px below pt, and small_font's rendered height
        # varies enough across systems/font-fallback that +16 let the two overlap
        # on some machines (reported: title text visibly overlapping "New File").
        self.btn_new = Button((self._BTN_X, y0 + 30, self._BTN_W, self._BTN_H), 'New File')
        self.btn_open = Button((self._BTN_X, y0 + 80, self._BTN_W, self._BTN_H), 'Open File')
        self.btn_play = Button((self._BTN_X, y0 + 164, 100, self._BTN_H), 'Play')
        self.btn_reset = Button((114, y0 + 164, self._RST_W, self._BTN_H), '')
        self.btn_tracks = Button((self._BTN_X, y0 + 248, self._BTN_W, self._BTN_H), 'Tracks')

        self.btn_play.enabled = False
        self.btn_reset.enabled = False
        self.btn_tracks.enabled = False

        self._all_buttons = (self.btn_new, self.btn_open, self.btn_play, self.btn_reset, self.btn_tracks)
        self._dropdown = _TrackDropdown(self.btn_tracks.rect, left_w)

    # ── Public state queries ────────────────────────────────────────────

    def dropdown_collidepoint(self, pos, tracks) -> bool:
        return self._dropdown.collidepoint(pos, tracks)

    def _enable_file_dependent_buttons(self) -> None:
        self.btn_play.enabled = True
        self.btn_reset.enabled = True
        self.btn_tracks.enabled = True

    # ── File operations ─────────────────────────────────────────────────

    def load_file(self, app, settings, path: str) -> bool:
        if app.load(path):
            cfg.add_recent_file(settings, path)
            self._enable_file_dependent_buttons()
            return True
        return False

    def open_file_dialog(self, app, settings) -> None:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title='Open MIDI File', filetypes=[('MIDI Files', '*.mid *.midi'), ('All Files', '*.*')])
        root.destroy()
        if path:
            self.load_file(app, settings, path)

    def new_file_dialog(self, app, settings) -> None:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.asksaveasfilename(
            title='New MIDI File', defaultextension='.mid',
            filetypes=[('MIDI Files', '*.mid'), ('All Files', '*.*')])
        root.destroy()
        if path:
            _create_empty_midi(path)
            self.load_file(app, settings, path)

    # ── Main loop helpers ───────────────────────────────────────────────

    def update(self, mouse_pos) -> None:
        for btn in self._all_buttons:
            btn.update(mouse_pos)

    def handle_dropdown_event(self, event, app) -> bool:
        return self._dropdown.handle_event(event, app)

    def handle_panel_event(self, event, app, settings, menu) -> bool:
        if self.btn_new.clicked(event):
            self._dropdown.close()
            if menu:
                menu.close()
            self.new_file_dialog(app, settings)
            return True

        if self.btn_open.clicked(event):
            self._dropdown.close()
            if menu:
                menu.close()
            self.open_file_dialog(app, settings)
            return True

        if self.btn_play.clicked(event):
            app.pause() if app.playing else app.play()
            return True

        if self.btn_reset.clicked(event):
            app.seek(0.0)
            return True

        if self.btn_tracks.clicked(event):
            if menu:
                menu.close()
            self._dropdown.toggle(self.btn_tracks.enabled)
            return True

        return False

    # ── Drawing ──────────────────────────────────────────────────────────

    def draw(self, screen, fonts, app, win_h: int, settings: dict | None = None) -> None:
        pal = get_theme(settings or {})
        font = fonts.get('normal')
        small_font = fonts.get('small')
        pt = self._mh

        pygame.draw.rect(screen, pal['panel_bg'], (0, pt, self._lw, win_h - pt))
        pygame.draw.line(screen, pal['panel_line'], (self._lw - 1, pt), (self._lw - 1, win_h))

        title = small_font.render('MIDI VIS', True, pal['title'])
        screen.blit(title, (self._lw // 2 - title.get_width() // 2, pt + 6))

        for dy in (154, 238):
            pygame.draw.line(screen, pal['sep'], (10, pt + dy), (self._lw - 10, pt + dy))

        self.btn_play.text = 'Pause' if app.playing else 'Play'
        play_icon = _icon_pause if app.playing else _icon_play

        self.btn_new.draw(screen, font, pal, _icon_new)
        self.btn_open.draw(screen, font, pal, _icon_open)
        self.btn_play.draw(screen, font, pal, play_icon)
        self.btn_reset.draw(screen, font, pal, _icon_reset)
        self.btn_tracks.draw(screen, font, pal, _icon_tracks)

        if app.loaded:
            n_en, n_tot = len(app.enabled_tracks), len(app.tracks)
            hint = small_font.render(f'{n_en}/{n_tot} tracks', True, pal['hint'])
            screen.blit(hint, (self._lw // 2 - hint.get_width() // 2, self.btn_tracks.rect.bottom + 4))

        self._dropdown.draw(screen, app, font, pal)
