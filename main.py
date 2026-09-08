'''MidiVis entry point.

Milestone 3 (UI shell + widgets + slots) replaces Milestone 2's deliberately
throwaway 900x220 debug window with the real app shell: menu bar, dashboard
(file open + track list/mute), and the SlotManager-driven panel stack
(timeline, bars, keyboard, properties) — Plan Part 4's "feature parity with
today's app apart from traditional notation." Only the settings/audio-setup/
engine-construction bootstrapping from Milestone 2's main.py survives; the
window/rendering code is new.
'''
from __future__ import annotations

import os
import signal

import pygame

from midivis import settings as cfg
from midivis.app import App
from midivis.audio import setup as audio_setup
from midivis.audio.fluid_player import FluidPlayerBackend
from midivis.midi import quantize
from midivis.render import fonts as fonts_mod
from midivis.render.dashboard import Dashboard
from midivis.render.slots import KeyboardSlot, PropertiesSlot, SheetSlot, SlotManager, TimelineSlot
from midivis.render.theme import get_theme
from midivis.render.widgets.menu import MenuBar, MenuItem, TopMenu

WIN_W, WIN_H = 1200, 720
LEFT_W = 150
MENU_H = 24
MIN_WIN_W, MIN_WIN_H = 640, 400


def _content_rect(win_w: int, win_h: int) -> pygame.Rect:
    return pygame.Rect(LEFT_W, MENU_H, win_w - LEFT_W, win_h - MENU_H)


def _open_file_dialog() -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(
        title='Open MIDI file', filetypes=[('MIDI files', '*.mid *.midi'), ('All files', '*.*')])
    root.destroy()
    return path or None


def run() -> None:
    signal.signal(signal.SIGINT, lambda *_: os._exit(1))

    user_settings = cfg.load()
    if not audio_setup.ensure_audio_paths(user_settings):
        print('FluidSynth setup incomplete — cannot continue without a '
              'FluidSynth install and a SoundFont file.')
        return
    cfg.save(user_settings)
    audio_cfg = user_settings['audio']

    pygame.mixer.pre_init(0, 0, 0, 0)  # audio is handled by FluidSynth, not pygame's mixer
    pygame.init()
    flags = pygame.RESIZABLE | pygame.DOUBLEBUF
    screen = pygame.display.set_mode((WIN_W, WIN_H), flags)
    pygame.display.set_caption('MidiVis')
    win_w, win_h = WIN_W, WIN_H
    clock = pygame.time.Clock()
    fonts = fonts_mod.get_fonts()

    engine = None
    try:
        engine = FluidPlayerBackend(audio_cfg['fluidsynth_bin'], audio_cfg['soundfont'])
    except Exception as e:
        print(f'FluidSynth init failed: {e}')

    app = App(engine)
    app.notation_snap_grid = user_settings.get('notation', {}).get(
        'snap_grid', quantize.DEFAULT_SNAP_GRID)

    dashboard = Dashboard(left_w=LEFT_W, menu_h=MENU_H)
    slot_manager = SlotManager([
        TimelineSlot(),
        SheetSlot(),
        KeyboardSlot(),
        PropertiesSlot(),
    ])

    def _file_items() -> list[MenuItem]:
        recent = user_settings.get('recent_files', [])
        items = [MenuItem('new_file', 'New File...'), MenuItem('open', 'Open...')]
        if recent:
            items.append(MenuItem('sep', separator=True))
            items.append(MenuItem('recent', 'Recent Files', submenu_fn=_recent_items))
        return items

    def _recent_items() -> list[MenuItem]:
        recent = user_settings.get('recent_files', [])
        if not recent:
            return [MenuItem('none', '(no recent files)', enabled=False)]
        return [MenuItem(f'recent:{p}', os.path.basename(p)) for p in recent]

    def _view_items() -> list[MenuItem]:
        return [
            MenuItem('theme', 'Color Theme', submenu_fn=_theme_items),
            MenuItem('slots', 'Slots', submenu_fn=_slots_items),
            MenuItem('note_accuracy', 'Note Accuracy', submenu_fn=_note_accuracy_items),
        ]

    def _theme_items() -> list[MenuItem]:
        current = user_settings.get('theme', 'dark')
        return [
            MenuItem('theme:dark', 'Dark', checked=(current == 'dark')),
            MenuItem('theme:light', 'Light', checked=(current == 'light')),
        ]

    # "Note accuracy threshold" for the traditional (sheet music) view --
    # readability over exact MIDI timing (see midi/quantize.py's
    # snap_note_span). 0 = exact timing, no snapping.
    _SNAP_GRID_OPTIONS = [
        (0, 'Exact Timing'), (16, "1/16 Note"), (32, "1/32 Note (Recommended)"), (64, "1/64 Note"),
    ]

    def _note_accuracy_items() -> list[MenuItem]:
        current = user_settings.get('notation', {}).get('snap_grid', quantize.DEFAULT_SNAP_GRID)
        return [MenuItem(f'snap_grid:{value}', label, checked=(current == value))
                for value, label in _SNAP_GRID_OPTIONS]

    def _slots_items() -> list[MenuItem]:
        entries = [('timeline', 'Timeline'), ('sheet', 'Sheet'),
                   ('keyboard', 'Keyboard'), ('properties', 'Properties')]
        return [MenuItem(f'slot_toggle:{sid}', label, checked=slot_manager.is_visible(sid))
                for sid, label in entries]

    menu = MenuBar([
        TopMenu('file', 'File', _file_items, width=200, submenu_width=240),
        # 210 (was 145) -- 145 was sized for Color Theme/Slots' short labels
        # only; "1/32 Note (Recommended)" (the Note Accuracy submenu's
        # longest item) needed ~189px including its checkmark, so 145
        # clipped it. All of the View top-menu's submenus share one width
        # (Dropdown/TopMenu don't support a per-submenu size), so this
        # widens Color Theme/Slots too -- harmless, just some empty space
        # to the right of their short labels.
        TopMenu('view', 'View', _view_items, width=200, submenu_width=210),
    ], height=MENU_H)

    def _cleanup() -> None:
        app.shutdown()

    import atexit
    atexit.register(_cleanup)

    recent = user_settings.get('recent_files', [])
    if recent and os.path.isfile(recent[0]):
        dashboard.load_file(app, user_settings, recent[0])

    content = _content_rect(win_w, win_h)
    running = True

    while running:
        mouse_pos = pygame.mouse.get_pos()
        dashboard.update(mouse_pos)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.VIDEORESIZE:
                win_w = max(MIN_WIN_W, event.w)
                win_h = max(MIN_WIN_H, event.h)
                content = _content_rect(win_w, win_h)

            action = menu.handle_event(event, fonts['normal'])
            if action in ('new_file', 'open'):
                menu.close()
                if action == 'new_file':
                    dashboard.new_file_dialog(app, user_settings)
                else:
                    dashboard.open_file_dialog(app, user_settings)
                continue
            if action and action.startswith('recent:'):
                dashboard.load_file(app, user_settings, action[len('recent:'):])
                continue
            if action and action.startswith('theme:'):
                user_settings['theme'] = action[len('theme:'):]
                cfg.save(user_settings)
                continue
            if action and action.startswith('snap_grid:'):
                value = int(action[len('snap_grid:'):])
                user_settings.setdefault('notation', {})['snap_grid'] = value
                cfg.save(user_settings)
                app.set_notation_snap_grid(value)
                continue
            if action and action.startswith('slot_toggle:'):
                slot_manager.toggle_visible(action[len('slot_toggle:'):])
                continue
            if action == 'consumed':
                continue

            slot_manager.handle_event(
                event, content, app,
                pre_reorder_cb=lambda e: dashboard.handle_dropdown_event(e, app),
                menu_open=menu.is_open,
            )

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE and app.loaded:
                    app.pause() if app.playing else app.play()
                elif event.key == pygame.K_o and pygame.key.get_mods() & pygame.KMOD_CTRL:
                    path = _open_file_dialog()
                    if path:
                        dashboard.load_file(app, user_settings, path)

            dashboard.handle_panel_event(event, app, user_settings, menu)

        seek_delta = slot_manager.take_seek_delta()
        if seek_delta:
            app.seek(app.elapsed + seek_delta)

        app.update()
        pal = get_theme(user_settings)
        screen.fill((10, 10, 18))   # barely visible -- panels fully cover the window
        slot_manager.render(screen, content, app, fonts, user_settings)
        slot_manager.draw_drag_indicator(screen, content)
        dashboard.draw(screen, fonts, app, win_h, user_settings)
        menu.draw(screen, fonts['normal'], pal, win_w)
        pygame.display.flip()
        clock.tick(60)

    app.shutdown()
    pygame.quit()


if __name__ == '__main__':
    run()
