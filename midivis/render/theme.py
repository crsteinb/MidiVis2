'''Single consolidated theme source (Plan Part 3.4).

The old MidiVis split this into two dicts (ui/theme.py's SLOT_THEMES +
UI_THEMES) merged ad hoc by SlotBase.get_pal, and the Track dropdown /
Record-arm panel bypassed the theme system entirely with hardcoded color
literals (a real, present bug called out in Plan Part 2 — Light theme did
nothing for them). Here everything — slot infrastructure, dashboard chrome,
menu bar, and the dashboard's track dropdown — lives in one THEMES dict per
palette, so nothing can be left un-themed by construction.
'''
from __future__ import annotations

THEMES: dict[str, dict] = {
    'dark': {
        # Shared slot infrastructure (handle grip, scrollbar)
        'handle':      (78,  82,  88),
        'handle_dash': (46,  48,  52),
        'sb_track':    (30,  30,  38),
        'sb_thumb':    (80,  82,  100),

        # Dashboard panel chrome
        'panel_bg':     (22,  22,  35),
        'panel_line':   (48,  48,  65),
        'sep':          (50,  50,  68),
        'title':        (80,  85,  110),
        'hint':         (90,  95,  118),
        'btn_disabled': ((26, 26, 38),  (42, 42, 55),   (62,  62,  75)),
        'btn_selected': ((62, 76, 118), (92, 108, 160), (210, 222, 255)),
        'btn_hover':    ((48, 51, 72),  (76, 80, 108),  (202, 208, 230)),
        'btn_normal':   ((36, 38, 54),  (60, 63, 88),   (172, 178, 200)),

        # Menu bar / dropdowns
        'menu_bg':      (28,  28,  42),
        'menu_line':    (50,  50,  70),
        'menu_text':    (195, 200, 220),
        'menu_dim':     (90,  90,  115),
        'drop_bg':      (32,  32,  50),
        'drop_sel':     (52,  56,  82),
        'drop_bor':     (62,  65,  95),

        # Track dropdown (previously hardcoded literals, un-themed — Plan Part 2)
        'track_bg':      (26,  26,  42),
        'track_border':  (65,  68,  95),
        'track_row_hov': (44,  47,  68),
        'track_text':    (170, 175, 210),
        'track_text_hov': (225, 230, 250),
        'track_check':   (75,  200, 100),
        'track_sep':     (58,  62,  90),

        # Timeline slot
        'tl_bg':       (28,  28,  32),
        'tl_fill':     (50,  50,  62),
        'tl_mark':     (175, 175, 188),
        'tl_text':     (148, 148, 165),
        'tl_head':     (215, 218, 230),
        'tl_border':   (48,  48,  56),
        'tl_label_bg': (22,  22,  26),

        # Bars (piano-roll) slot
        'bg_roll':      (24,  24,  28),
        'note':         (80,  140, 220),
        'note_active':  (220, 60,  60),
        'note_outline': (15,  15,  18),
        'measure':      (118, 118, 132),
        'octave':       (38,  38,  44),
        'playhead':     (215, 218, 230),
        'text':         (170, 170, 185),
        'text_dim':     (160, 160, 180),
        'piano_bg':     (18,  18,  22),
        'piano_white':  (230, 230, 235),
        'piano_black':  (20,  20,  24),
        'piano_border': (60,  60,  70),
        'piano_label':  (120, 120, 135),
        'piano_active': (220, 60,  60),

        # Keyboard slot
        'key_white':         (255, 255, 255),
        'key_black':         (0,   0,   0),
        'key_active':        (220, 0,   0),
        'key_bg':            (30,  30,  30),
        'key_marker':        (230, 130, 130),
        'key_marker_active': (200, 200, 200),

        # Properties slot
        'props_bg':      (22,  22,  35),
        'props_text':    (195, 200, 220),
        'props_dim':     (158, 162, 185),
        'props_sep':     (50,  50,  68),
        'props_btn_bg':  (40,  42,  60),
        'props_btn_fg':  (160, 165, 195),

        # Traditional (grand staff) notation slot
        'trad_bg':          (24,  24,  28),
        'trad_bg_clef':     (18,  18,  22),
        'trad_divider':     (55,  55,  70),
        'trad_staff':       (185, 185, 200),
        'trad_bar':         (140, 140, 160),
        'trad_playhead':    (220, 60,  60),
        'trad_note':        (80,  140, 220),
        'trad_note_past':   (75,  80,  100),
        'trad_note_act':    (220, 60,  60),
        'trad_note_outline': (15,  15,  18),
        'trad_measure_num': (175, 170, 155),
    },
    'light': {
        'handle':      (180, 178, 170),
        'handle_dash': (130, 125, 115),
        'sb_track':    (210, 205, 192),
        'sb_thumb':    (150, 145, 132),

        'panel_bg':     (235, 232, 222),
        'panel_line':   (185, 180, 165),
        'sep':          (190, 185, 168),
        'title':        (80,  75,  60),
        'hint':         (100, 95,  80),
        'btn_disabled': ((210, 207, 197), (175, 172, 162), (130, 126, 115)),
        'btn_selected': ((140, 165, 220), (100, 130, 185), (25,  45,  110)),
        'btn_hover':    ((200, 196, 182), (165, 162, 148), (30,  28,  20)),
        'btn_normal':   ((218, 215, 205), (175, 172, 158), (60,  58,  48)),

        'menu_bg':      (218, 215, 200),
        'menu_line':    (185, 180, 165),
        'menu_text':    (30,  28,  20),
        'menu_dim':     (120, 115, 100),
        'drop_bg':      (235, 232, 222),
        'drop_sel':     (195, 190, 175),
        'drop_bor':     (170, 165, 150),

        'track_bg':      (235, 232, 222),
        'track_border':  (170, 165, 150),
        'track_row_hov': (215, 211, 196),
        'track_text':    (70,  66,  55),
        'track_text_hov': (30,  28,  20),
        'track_check':   (40,  130, 60),
        'track_sep':     (195, 190, 175),

        'tl_bg':       (215, 212, 200),
        'tl_fill':     (170, 162, 145),
        'tl_mark':     (90,  85,  75),
        'tl_text':     (80,  74,  62),
        'tl_head':     (40,  35,  25),
        'tl_border':   (175, 170, 155),
        'tl_label_bg': (200, 196, 182),

        'bg_roll':      (248, 246, 238),
        'note':         (25,  55,  135),
        'note_active':  (200, 25,  25),
        'note_outline': (200, 195, 180),
        'measure':      (170, 165, 148),
        'octave':       (220, 215, 200),
        'playhead':     (175, 0,   0),
        'text':         (60,  55,  45),
        'text_dim':     (135, 125, 108),
        'piano_bg':     (200, 195, 180),
        'piano_white':  (252, 250, 242),
        'piano_black':  (40,  38,  30),
        'piano_border': (160, 155, 140),
        'piano_label':  (110, 105, 90),
        'piano_active': (200, 25,  25),

        'key_white':         (252, 250, 242),
        'key_black':         (30,  28,  20),
        'key_active':        (190, 40,  40),
        'key_bg':            (190, 185, 172),
        'key_marker':        (200, 100, 100),
        'key_marker_active': (30,  28,  20),

        'props_bg':      (245, 243, 235),
        'props_text':    (30,  28,  20),
        'props_dim':     (80,  75,  60),
        'props_sep':     (190, 185, 168),
        'props_btn_bg':  (218, 215, 205),
        'props_btn_fg':  (60,  58,  48),

        'trad_bg':          (248, 246, 238),
        'trad_bg_clef':     (236, 234, 222),
        'trad_divider':     (170, 165, 148),
        'trad_staff':       (15,  15,  15),
        'trad_bar':         (40,  40,  40),
        'trad_playhead':    (175, 0,   0),
        'trad_note':        (25,  55,  135),
        'trad_note_past':   (125, 125, 158),
        'trad_note_act':    (200, 25,  25),
        'trad_note_outline': (200, 195, 180),
        'trad_measure_num': (140, 120, 90),
    },
}


def get_theme(settings: dict) -> dict:
    name = settings.get('theme', 'dark')
    return THEMES.get(name, THEMES['dark'])
