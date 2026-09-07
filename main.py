'''MidiVis entry point.

Milestone 2 (Audio engine v1): FluidPlayerBackend behind the AudioEngine interface,
wired to a deliberately minimal shell UI — this window exists to prove the audio
engine end-to-end (open a file, play/pause, seek by clicking the timeline bar, see
elapsed/total time), not as the real app shell. render/widgets, SlotManager, and the
actual views (bars/traditional/keyboard/properties) are Milestone 3 (Plan Part 4) —
this UI is throwaway and gets replaced wholesale then, not incrementally grown.
'''
from __future__ import annotations

import os
import signal
import sys

import pygame

from midivis import settings as cfg
from midivis.audio import setup as audio_setup
from midivis.audio.fluid_player import FluidPlayerBackend
from midivis.app import App

WIN_W, WIN_H = 900, 220
TIMELINE_Y = 140
TIMELINE_H = 24
MARGIN = 24


def _open_file_dialog() -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title='Open MIDI file',
        filetypes=[('MIDI files', '*.mid *.midi'), ('All files', '*.*')])
    root.destroy()
    return path or None


def _fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


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
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption('MidiVis')
    clock = pygame.time.Clock()
    font = pygame.font.SysFont('segoeui', 18)
    small_font = pygame.font.SysFont('segoeui', 14)

    engine = None
    try:
        engine = FluidPlayerBackend(audio_cfg['fluidsynth_bin'], audio_cfg['soundfont'])
    except Exception as e:
        print(f'FluidSynth init failed: {e}')

    app = App(engine)

    recent = user_settings.get('recent_files', [])
    if recent and os.path.isfile(recent[0]):
        app.load(recent[0])

    timeline_rect = pygame.Rect(MARGIN, TIMELINE_Y, WIN_W - 2 * MARGIN, TIMELINE_H)

    def _open_file() -> None:
        path = _open_file_dialog()
        if path and app.load(path):
            cfg.add_recent_file(user_settings, path)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE and app.loaded:
                    if app.playing:
                        app.pause()
                    else:
                        app.play()
                elif event.key == pygame.K_o and pygame.key.get_mods() & pygame.KMOD_CTRL:
                    _open_file()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if app.loaded and timeline_rect.collidepoint(event.pos):
                    frac = (event.pos[0] - timeline_rect.x) / timeline_rect.w
                    app.seek(frac * app.total_dur)

        app.update()

        screen.fill((18, 18, 24))

        title = app.title if app.loaded else 'No file loaded — Ctrl+O to open'
        screen.blit(font.render(title, True, (230, 230, 235)), (MARGIN, 24))

        hint = 'Space = play/pause    Ctrl+O = open    click bar = seek    Esc = quit'
        screen.blit(small_font.render(hint, True, (140, 140, 150)), (MARGIN, 56))

        pygame.draw.rect(screen, (60, 60, 70), timeline_rect, border_radius=4)
        if app.loaded and app.total_dur > 0:
            frac = max(0.0, min(1.0, app.elapsed / app.total_dur))
            fill_w = int(timeline_rect.w * frac)
            if fill_w > 0:
                fill_rect = pygame.Rect(timeline_rect.x, timeline_rect.y, fill_w, timeline_rect.h)
                pygame.draw.rect(screen, (90, 160, 220), fill_rect, border_radius=4)

        time_text = (f'{_fmt_time(app.elapsed)} / {_fmt_time(app.total_dur)}'
                     if app.loaded else '--:-- / --:--')
        screen.blit(small_font.render(time_text, True, (200, 200, 210)),
                    (MARGIN, TIMELINE_Y + TIMELINE_H + 8))

        status = ('playing' if app.playing else 'paused') if app.loaded else ''
        driver = f'  [{engine.driver_name} driver]' if engine else '  [no audio — FluidSynth init failed]'
        screen.blit(small_font.render(status + driver, True, (140, 140, 150)),
                    (MARGIN, TIMELINE_Y + TIMELINE_H + 30))

        pygame.display.flip()
        clock.tick(60)

    app.shutdown()
    pygame.quit()


if __name__ == '__main__':
    run()
