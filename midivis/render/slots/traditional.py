'''Traditional grand-staff notation slot (Plan Part 3.3/3.4/4).

Replaces the old `ui/slots/traditional_sheet.py`'s three specifically-called-
out weak points (Plan Part 2) with the sprite atlas (`notation/glyphs.py`)
and the pre-computed layout from `notation/engraver.py`:
  - Clefs: `GlyphAtlas` blit instead of an OS-font Unicode lookup that
    silently drew nothing if `segoeuisymbol` lacked the glyph.
  - Accidentals: sharp/flat/natural chosen from `app.engraving` (which ran
    every note through `midi/spelling.py`) instead of a hardcoded '#'.
  - Rests: `GlyphAtlas` blit instead of hand-tuned Bezier curves.

Stems, beams, ledger lines, staff lines, and (new — the old renderer never
drew these because it never computed ties) tie arcs stay procedural
`pygame.draw` calls, per Plan 3.3's "keep stems/beams/ledger-lines/staff-
lines procedural... they already look fine and are naturally resolution-
independent."

Staff size (LS) is a fixed constant, not tied to `app.sheet_zoom` — matching
the old renderer's own behavior (zoom there only ever affected horizontal
note spacing/time scale, never vertical staff scale; resizing the panel
reveals more/less vertical context via scrolling, it doesn't rescale the
staff). LS is deliberately set to the atlas's 'md' tier's staff-space size so
no runtime glyph rescaling is needed at all; the 'sm'/'lg' tiers exist for a
future per-DPI or staff-zoom setting to pick without rebuilding the atlas —
see FullRewriteStatus.md's Milestone 4 deviations.
'''
from __future__ import annotations

import pygame

from midivis.notation.glyphs import GlyphAtlas
from midivis.render.slots.slot_base import SlotBase, draw_handle, HANDLE_W
from midivis.render.widgets.scrollbar import VerticalScrollbar

LS = 24                 # staff-space px -- matches build_atlas.py's 'md' tier
GLYPH_TIER = 'md'
CLEF_W = 100
MEASURES_VISIBLE = 8
PH_RATIO = 0.22
SCROLL_W = 10

# Diatonic steps (octave*7 + letter index, C4 = 28 -- see midi/spelling.py)
# of the bottom line of each staff, and of the line each clef's SMuFL
# reference point sits on.
TREBLE_REF_STEP = 30    # E4, bottom line of the treble staff
BASS_REF_STEP = 18      # G2, bottom line of the bass staff
TREBLE_CLEF_STEP = 32   # G4, the line the G-clef wraps around
BASS_CLEF_STEP = 24     # F3, the line between the F-clef's two dots

_MIDDLE_STEP = {'treble': TREBLE_REF_STEP + 4, 'bass': BASS_REF_STEP + 4}

_BEAM_H = max(3, int(LS * 0.22))
_BEAM_GAP = max(2, int(LS * 0.18))


class TraditionalSlot(SlotBase):
    fixed_height = None

    def __init__(self, atlas: GlyphAtlas | None = None) -> None:
        super().__init__('traditional')
        self._atlas = atlas or GlyphAtlas()
        self._scrollbar = VerticalScrollbar(SCROLL_W)
        self._notehead_w = self._atlas.get('noteheadBlack', GLYPH_TIER).surface.get_width()

    # ── Scroll geometry ──────────────────────────────────────────────────

    def _scroll_info(self, rect, app):
        visible_h = rect.height
        engraving = getattr(app, 'engraving', None)
        steps = []
        if engraving:
            enabled = getattr(app, 'enabled_tracks', None)
            for n in engraving.notes:
                if enabled is not None and n.track_id not in enabled:
                    continue
                steps.extend(p[1] for p in n.pitches)
        if not steps:
            return visible_h, 0, False
        span = (max(steps) - min(steps)) + 8   # padding steps
        virtual_h = max(visible_h, int(span * LS / 2))
        has_scroll = self._scrollbar.is_needed(virtual_h, visible_h)
        frac = max(0.0, min(1.0, getattr(app, 'trad_scroll', 0.5)))
        scroll_px = int(frac * (virtual_h - visible_h)) if has_scroll else 0
        return virtual_h, scroll_px, has_scroll

    # ── Events ───────────────────────────────────────────────────────────

    def handle_event(self, event, rect, app) -> bool:
        virtual_h, _, _ = self._scroll_info(rect, app)
        track_r = pygame.Rect(rect.right - SCROLL_W, rect.y, SCROLL_W, rect.height)
        frac = max(0.0, min(1.0, getattr(app, 'trad_scroll', 0.5)))
        was_dragging = self._scrollbar.dragging
        new_frac = self._scrollbar.handle_event(event, track_r, virtual_h, rect.height, frac)
        if new_frac is not None:
            app.trad_scroll = new_frac
            return True
        return was_dragging

    # ── Rendering ────────────────────────────────────────────────────────

    def draw(self, screen, rect, app, fonts, settings) -> None:
        measure_font = fonts.get('measure_trad', fonts['small'])
        pal = self.get_pal(settings)
        rx, ry, rw, rh = rect.x, rect.y, rect.width, rect.height

        draw_handle(screen, rx, ry, rh, pal)
        rx += HANDLE_W
        rw -= HANDLE_W

        virtual_h, scroll_px, has_scroll = self._scroll_info(rect, app)
        if has_scroll:
            rw -= SCROLL_W

        pygame.draw.rect(screen, pal['trad_bg'], (rx + CLEF_W, ry, rw - CLEF_W, rh))
        pygame.draw.rect(screen, pal['trad_bg_clef'], (rx, ry, CLEF_W, rh))
        pygame.draw.line(screen, pal['trad_divider'], (rx + CLEF_W, ry), (rx + CLEF_W, ry + rh))

        virtual_mid = ry + virtual_h // 2 - scroll_px
        treble_bot = virtual_mid - LS
        bass_bot = treble_bot + 7 * LS
        treble_top = treble_bot - 4 * LS

        staff_x0 = rx + CLEF_W
        staff_w = rw - CLEF_W
        playhead_x = staff_x0 + int(staff_w * PH_RATIO)
        zoom = getattr(app, 'sheet_zoom', 1.0)
        measure_dur = (60.0 / app.bpm) * app.time_sig[0]
        pps = staff_w / (measure_dur * (MEASURES_VISIBLE / zoom))
        margin = _visibility_margin(measure_dur, pps)

        clef_x = rx + 26
        self._atlas.blit(screen, 'gClef', GLYPH_TIER, clef_x,
                          _step_y(TREBLE_CLEF_STEP, TREBLE_REF_STEP, treble_bot),
                          color=pal['trad_staff'])
        self._atlas.blit(screen, 'fClef', GLYPH_TIER, clef_x,
                          _step_y(BASS_CLEF_STEP, BASS_REF_STEP, bass_bot),
                          color=pal['trad_staff'])

        # Clip everything from here on (staff lines, measures, notes/ties/
        # rests, playhead) to the staff area only -- excludes the clef box
        # to its left, so scrolled-back note content can't bleed under the
        # clef the way it did before this clip's left edge was tightened
        # from the whole panel (rx) to just past the clef (staff_x0).
        prev_clip = screen.get_clip()
        screen.set_clip(pygame.Rect(staff_x0, ry, staff_w + (SCROLL_W if has_scroll else 0), rh))

        _draw_staff_lines(screen, staff_x0, staff_w, treble_bot, pal['trad_staff'])
        _draw_staff_lines(screen, staff_x0, staff_w, bass_bot, pal['trad_staff'])
        pygame.draw.line(screen, pal['trad_staff'], (staff_x0, treble_top), (staff_x0, bass_bot))
        pygame.draw.line(screen, pal['trad_staff'], (staff_x0 + staff_w - 1, treble_top),
                          (staff_x0 + staff_w - 1, bass_bot))

        for n, t in app.measure_times:
            x = playhead_x + int((t - app.elapsed) * pps)
            if staff_x0 <= x <= staff_x0 + staff_w:
                pygame.draw.line(screen, pal['trad_bar'], (x, treble_top), (x, bass_bot))
                lbl = measure_font.render(str(n + 1), True, pal['trad_measure_num'])
                screen.blit(lbl, (x + 2, treble_top - lbl.get_height() - 2))

        engraving = getattr(app, 'engraving', None)
        if engraving is not None:
            enabled = getattr(app, 'enabled_tracks', set())
            ref_bot = {'treble': treble_bot, 'bass': bass_bot}
            active = getattr(app, 'active_notes', set())

            visible_notes = [n for n in engraving.notes if n.track_id in enabled]
            geoms = {}   # id(note) -> (note_x, [(step, y, midi_note, accidental)], color)
            for n in visible_notes:
                # note_x is the notehead's time-based *left* edge (matching
                # how bars.py positions note rectangles); GlyphAtlas anchors
                # noteheads at their own left edge too (minx=0 for all three
                # notehead glyphs), so blitting straight at note_x lines up
                # correctly. But every downstream formula below (stems,
                # ledger lines, dots, ties) was ported from the old hand-
                # drawn renderer, which positioned noteheads by their
                # *center* -- shifting to that same convention here, once,
                # keeps all of them correct instead of auditing each one's
                # offset math individually. (This was a real bug: without
                # the shift, a stem's "+notehead_w/2" landed at the glyph's
                # horizontal center, not its right edge, making stems look
                # like they cut through the notehead instead of attaching
                # to its side.)
                left_x = playhead_x + int((n.start_s - app.elapsed) * pps)
                if left_x < staff_x0 - margin or left_x > staff_x0 + staff_w + margin:
                    continue
                note_x = left_x + self._notehead_w // 2
                rb = ref_bot[n.staff]
                ref_step = TREBLE_REF_STEP if n.staff == 'treble' else BASS_REF_STEP
                any_active = any(m in active and n.start_s <= app.elapsed < n.end_s
                                  for m, _step, _acc in n.pitches)
                color = (pal['trad_note_act'] if any_active
                          else pal['trad_note_past'] if left_x < playhead_x
                          else pal['trad_note'])
                positions = [(step, _step_y(step, ref_step, rb), midi_note, acc)
                             for midi_note, step, acc in n.pitches]
                geoms[id(n)] = (note_x, positions, color)

            for n in visible_notes:
                if id(n) not in geoms:
                    continue
                note_x, positions, _color = geoms[id(n)]
                rb = ref_bot[n.staff]
                ref_step = TREBLE_REF_STEP if n.staff == 'treble' else BASS_REF_STEP
                for step, _y, _note, _acc in positions:
                    # _draw_ledger_lines' thresholds are staff-relative (0 =
                    # bottom line, 8 = top line) -- `step` here is the
                    # absolute diatonic step from midi/spelling.py, so it
                    # must be re-based against this staff's own bottom line
                    # first. Passing the absolute step directly (the
                    # original bug) made every note's step land far above
                    # the >= 10 threshold regardless of its actual staff
                    # position, drawing bogus ledger lines through/around
                    # essentially every note.
                    _draw_ledger_lines(screen, note_x, step - ref_step, rb,
                                       pal['trad_staff'], self._notehead_w)

            beamed = set()
            for group in engraving.beam_groups:
                chords = [(id(engraving.notes[i]), engraving.notes[i]) for i in group
                          if id(engraving.notes[i]) in geoms]
                if len(chords) < 2:
                    continue
                self._draw_beam_group(screen, [(nid, n, geoms[nid]) for nid, n in chords], pal)
                beamed.update(nid for nid, _ in chords)

            for n in visible_notes:
                nid = id(n)
                if nid not in geoms or nid in beamed:
                    continue
                note_x, positions, color = geoms[nid]
                self._draw_chord(screen, note_x, positions, n.note_type, n.dots, color, n.staff, pal)

            for i, n in enumerate(engraving.notes):
                if not n.tie_next or i + 1 >= len(engraving.notes):
                    continue
                nxt = engraving.notes[i + 1]
                if n.track_id not in enabled or id(n) not in geoms or id(nxt) not in geoms:
                    continue
                x1, pos1, color = geoms[id(n)]
                x2, pos2, _ = geoms[id(nxt)]
                stem_up = _group_stem_up([pos1], _MIDDLE_STEP[n.staff])
                for (_step1, y1, _m1, _a1), (_step2, y2, _m2, _a2) in zip(pos1, pos2):
                    _draw_tie(screen, x1 + self._notehead_w // 2, y1,
                              x2 - self._notehead_w // 2, y2, stem_up, color)

            for r in engraving.rests:
                if r.staff not in ref_bot or r.track_id not in enabled:
                    continue
                rx_r = playhead_x + int(((r.start_s + r.end_s) / 2 - app.elapsed) * pps)
                if rx_r < staff_x0 - margin or rx_r > staff_x0 + staff_w + margin:
                    continue
                glyph_name = _REST_GLYPH.get(r.rest_type, 'restQuarter')
                self._atlas.blit(screen, glyph_name, GLYPH_TIER, rx_r,
                                  ref_bot[r.staff] - 2 * LS, color=pal['trad_staff'])

        pygame.draw.line(screen, pal['trad_playhead'],
                          (playhead_x, treble_top - 16), (playhead_x, bass_bot + 16), 2)
        screen.set_clip(prev_clip)

        if has_scroll:
            track_r = pygame.Rect(rect.right - SCROLL_W, ry, SCROLL_W, rh)
            frac = max(0.0, min(1.0, getattr(app, 'trad_scroll', 0.5)))
            self._scrollbar.draw(screen, track_r, virtual_h, rh, frac, pal)

    # ── Chord / beam drawing ─────────────────────────────────────────────

    def _draw_chord_heads(self, screen, note_x, positions, note_type, color, pal):
        acc_glyph = {1: 'accidentalSharp', -1: 'accidentalFlat'}
        name = 'noteheadWhole' if note_type == 'whole' else (
            'noteheadHalf' if note_type == 'half' else 'noteheadBlack')
        head_x = note_x - self._notehead_w // 2
        # A close interval (e.g. a second) draws its two noteheads at nearly
        # the same spot, and same-color fills alone read as one indistinct
        # blob (reported by the user from a screenshot). Draw highest pitch
        # first / lowest last so the lower note -- conventionally the more
        # structurally important voice -- ends up on top, fully outlined,
        # rather than partly covered by whatever was drawn after it.
        for _step, y, _note, accidental in sorted(positions, key=lambda p: p[2], reverse=True):
            # note_x is this chord's notehead *center* (see the caller);
            # GlyphAtlas anchors noteheads at their own left edge, so shift
            # left by half the (reference) notehead width to center it.
            self._atlas.blit(screen, name, GLYPH_TIER, head_x, y, color=color)
            self._atlas.draw_outline(screen, name, GLYPH_TIER, head_x, y, pal['trad_note_outline'])
            if accidental in acc_glyph:
                glyph = self._atlas.get(acc_glyph[accidental], GLYPH_TIER)
                # `blit`'s x is the glyph's left edge (accidentals' anchor_x
                # is 0, same as noteheads) -- subtracting only half the
                # glyph's width here (as if centering it) left its right half
                # overlapping the notehead. Subtract the full width instead
                # so the accidental sits entirely to the left, with a gap.
                self._atlas.blit(screen, acc_glyph[accidental], GLYPH_TIER,
                                  note_x - self._notehead_w // 2 - glyph.surface.get_width() - 2,
                                  y, color=color)

    def _draw_dots(self, screen, note_x, positions, dots, color):
        if dots <= 0:
            return
        dot_x = note_x + self._notehead_w // 2 + 4
        for step, y, _note, _acc in positions:
            on_line = step % 2 == 0
            dy = y - LS // 4 if on_line else y   # nudge into the adjacent space
            for d in range(dots):
                self._atlas.blit(screen, 'augmentationDot', GLYPH_TIER, dot_x + d * 6, dy, color=color)

    def _draw_chord(self, screen, note_x, positions, note_type, dots, color, staff, pal):
        self._draw_chord_heads(screen, note_x, positions, note_type, color, pal)
        self._draw_dots(screen, note_x, positions, dots, color)
        if note_type == 'whole':
            return
        stem_up = _group_stem_up([positions], _MIDDLE_STEP[staff])
        sx, y_base, y_tip = _stem_data(note_x, positions, stem_up, self._notehead_w)
        pygame.draw.line(screen, color, (sx, y_base), (sx, y_tip), 2)
        if note_type in ('eighth', 'sixteenth', 'thirty_second'):
            flag = ('flag8thUp' if stem_up else 'flag8thDown') if note_type == 'eighth' \
                else ('flag16thUp' if stem_up else 'flag16thDown')
            self._atlas.blit(screen, flag, GLYPH_TIER, sx, y_tip, color=color)

    def _draw_beam_group(self, screen, chords, pal):
        middle_step = _MIDDLE_STEP[chords[0][1].staff]
        stem_up = _group_stem_up([positions for _nid, _n, (_x, positions, _c) in chords], middle_step)
        stem_ext = int(LS * 2.5)
        stems = [_stem_data(x, positions, stem_up, self._notehead_w, stem_ext)
                 for _nid, _n, (x, positions, _c) in chords]
        beam_y = int(sum(t for _s, _b, t in stems) / len(stems))

        for _nid, n, (x, positions, color) in chords:
            self._draw_chord_heads(screen, x, positions, n.note_type, color, pal)

        for (_nid, _n, (_x, _pos, color)), (sx, y_base, _tip) in zip(chords, stems):
            pygame.draw.line(screen, color, (sx, y_base), (sx, beam_y), 2)

        beam_color = chords[0][2][2]
        x0, x1 = stems[0][0], stems[-1][0]
        by = beam_y if stem_up else beam_y - _BEAM_H
        pygame.draw.rect(screen, beam_color, (min(x0, x1), by, abs(x1 - x0), _BEAM_H))

        run = []
        for i, (_nid, n, _g) in enumerate(chords):
            if n.note_type in ('sixteenth', 'thirty_second'):
                run.append(i)
            else:
                if run:
                    _draw_secondary_beam(screen, run, stems, beam_y, stem_up, beam_color, self._notehead_w)
                    run = []
        if run:
            _draw_secondary_beam(screen, run, stems, beam_y, stem_up, beam_color, self._notehead_w)


_REST_GLYPH = {
    'whole': 'restWhole', 'half': 'restHalf', 'quarter': 'restQuarter',
    'eighth': 'rest8th', 'sixteenth': 'rest16th', 'thirty_second': 'rest32nd',
}


def _visibility_margin(measure_dur: float, pps: float) -> int:
    '''How far beyond the visible edges to still compute note/rest
    positions for (not just draw): a fixed pixel margin doesn't scale with
    zoom, and a tied note's *partner* segment can be up to one full measure
    away in time (quantize.split_across_barlines splits at measure
    boundaries) -- at high zoom that's far more than a fixed couple hundred
    pixels away on screen even though it's the very next segment. A fixed
    margin left ties popping in/out while still visible: as soon as one
    endpoint crossed the fixed cutoff the whole tie vanished, even though
    the note itself (and the tie arc) could still be on screen. Sizing the
    margin to a full measure's worth of pixels (floored at a sane minimum
    for very zoomed-out/fast-tempo views, where a measure might be only a
    handful of pixels) guarantees both of a tie's segments are always
    computed together, at any zoom level.
    '''
    return max(200, int(measure_dur * pps))


def _step_y(step: int, ref_step: int, ref_bottom_y: float) -> int:
    return int(ref_bottom_y - (step - ref_step) * (LS / 2))


def _draw_staff_lines(screen, x0, width, bottom_y, color):
    for i in range(5):
        y = int(bottom_y - i * LS)
        pygame.draw.line(screen, color, (x0, y), (x0 + width, y))


def _draw_ledger_lines(screen, note_x, step, bottom_y, color, notehead_w):
    half_w = notehead_w // 2 + 5
    if step <= -2:
        s = -2
        while s >= step - 1:
            y = int(bottom_y - s * (LS / 2))
            pygame.draw.line(screen, color, (note_x - half_w, y), (note_x + half_w, y))
            s -= 2
    elif step >= 10:
        s = 10
        while s <= step + 1:
            y = int(bottom_y - s * (LS / 2))
            pygame.draw.line(screen, color, (note_x - half_w, y), (note_x + half_w, y))
            s += 2


def _stem_data(note_x, positions, stem_up, notehead_w, stem_ext=None):
    if stem_ext is None:
        # 3.5 staff-spaces -- must comfortably clear a flag glyph's own
        # height (measured ~3.3 staff-spaces for Bravura's flag8th/flag16th
        # at this tier). The previous 2.2 was shorter than the flag itself,
        # so the flag's notehead-ward end overshot past the stem's base and
        # visually wrapped over the notehead instead of hanging cleanly
        # above/below it (reported: "note head rendering is still quite
        # broken", every flagged note looked like a hook stuck to the head).
        stem_ext = int(LS * 3.5)
    ys = [y for _step, y, _note, _acc in positions]
    if stem_up:
        return note_x + notehead_w // 2, max(ys), min(ys) - stem_ext
    return note_x - notehead_w // 2, min(ys), max(ys) + stem_ext


def _group_stem_up(all_positions, middle_step):
    '''Stems point up when the group's average staff position sits at or
    below the staff's middle line, down otherwise -- standard notation
    convention. `middle_step` must be the *absolute* diatonic step of that
    staff's middle line (TREBLE_REF_STEP/BASS_REF_STEP + 4), not a bare
    constant: comparing against a fixed relative threshold without
    accounting for which staff (and thus which absolute step range) a note
    is on made every stem point the same direction regardless of pitch.
    '''
    steps = [step for pos in all_positions for step, *_ in pos]
    return (sum(steps) / len(steps)) <= middle_step if steps else True


def _draw_secondary_beam(screen, run, stems, beam_y, stem_up, color, notehead_w):
    step = _BEAM_H + _BEAM_GAP
    ty = (beam_y + step) if stem_up else (beam_y - step - _BEAM_H)
    stub_w = max(notehead_w, int(notehead_w * 1.1))
    if len(run) >= 2:
        x0, x1 = stems[run[0]][0], stems[run[-1]][0]
        pygame.draw.rect(screen, color, (min(x0, x1), ty, abs(x1 - x0), _BEAM_H))
    else:
        i = run[0]
        sx = stems[i][0]
        x0 = (sx - stub_w) if i == len(stems) - 1 else sx
        pygame.draw.rect(screen, color, (x0, ty, stub_w, _BEAM_H))


def _draw_tie(screen, x1, y1, x2, y2, stem_up, color):
    '''Shallow arc connecting two tied noteheads, bulging away from the stem
    side (standard notation convention) -- new: the old renderer never
    computed ties at all, so it never needed this.
    '''
    if x2 <= x1:
        return
    bulge = max(4, int(LS * 0.3)) * (1 if stem_up else -1)
    mid_y = (y1 + y2) / 2 + bulge
    pts = []
    n = 16
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u * u * x1 + 2 * u * t * (x1 + x2) / 2 + t * t * x2
        y = u * u * y1 + 2 * u * t * mid_y + t * t * y2
        pts.append((int(x), int(y)))
    pygame.draw.lines(screen, color, False, pts, 2)
