'''Song timeline scrubber slot. Ported from the old ui/slots/timeline.py,
adapted to the new App (Milestone 2's AudioEngine-owns-the-clock design —
see app.py's seek_preview()/seek() split for how drag-preview now works
without a local wall-clock field to freely overwrite).
'''
from __future__ import annotations

import pygame

from midivis.render.slots.slot_base import SlotBase, draw_handle, HANDLE_W

TIMELINE_H = 30
LABEL_W = 72


class TimelineSlot(SlotBase):
    fixed_height = TIMELINE_H

    def __init__(self) -> None:
        super().__init__('timeline')
        self._dragging = False
        self._was_playing = False

    def _scrub_dim(self, rect):
        return rect.x + HANDLE_W, rect.width - HANDLE_W - LABEL_W

    def handle_event(self, event, rect, app) -> bool:
        scrub_x, scrub_w = self._scrub_dim(rect)

        if self._dragging:
            if event.type == pygame.MOUSEMOTION and app.loaded:
                clamped = max(scrub_x, min(scrub_x + scrub_w - 1, event.pos[0]))
                app.seek_preview((clamped - scrub_x) / scrub_w * app.total_dur)
                return True
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._dragging = False
                app.seek(app.elapsed)
                if self._was_playing:
                    app.play()
                return True
            return False

        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and app.loaded and rect.collidepoint(event.pos)):
            if scrub_x <= event.pos[0] < scrub_x + scrub_w:
                self._was_playing = app.playing
                if app.playing:
                    app.pause()
                app.seek_preview((event.pos[0] - scrub_x) / scrub_w * app.total_dur)
                self._dragging = True
                return True

        return False

    def draw(self, screen, rect, app, fonts, settings) -> None:
        small = fonts['small']
        pal = self.get_pal(settings)

        draw_handle(screen, rect.x, rect.y, rect.height, pal)
        scrub_x, scrub_w = self._scrub_dim(rect)
        total = app.total_dur
        progress = min(1.0, app.elapsed / total) if total > 0 else 0.0

        pygame.draw.rect(screen, pal['tl_bg'], (scrub_x, rect.y, scrub_w, rect.height))

        fill_w = int(scrub_w * progress)
        if fill_w > 0:
            pygame.draw.rect(screen, pal['tl_fill'], (scrub_x, rect.y, fill_w, rect.height))

        if total > 0:
            for i in range(1, 11):
                x = scrub_x + int(scrub_w * i / 10)
                t = total * i / 10
                pygame.draw.line(screen, pal['tl_mark'],
                                  (x, rect.y), (x, rect.y + rect.height - 1), 1)
                lbl = small.render(_fmt_time(t), True, pal['tl_text'])
                lx = x + 3
                if lx + lbl.get_width() < scrub_x + scrub_w - 4:
                    screen.blit(lbl, (lx, rect.y + (rect.height - lbl.get_height()) // 2))

        px = scrub_x + fill_w
        pygame.draw.line(screen, pal['tl_head'], (px, rect.y), (px, rect.y + rect.height - 1), 2)
        pygame.draw.line(screen, pal['tl_border'],
                          (scrub_x, rect.y + rect.height - 1), (scrub_x + scrub_w, rect.y + rect.height - 1))

        label_x = scrub_x + scrub_w
        pygame.draw.rect(screen, pal['tl_label_bg'], (label_x, rect.y, LABEL_W, rect.height))
        pygame.draw.line(screen, pal['tl_border'], (label_x, rect.y), (label_x, rect.y + rect.height - 1))

        el_surf = small.render(_fmt_time(app.elapsed), True, pal['tl_head'])
        to_surf = small.render(f'/ {_fmt_time(total)}', True, pal['tl_text'])
        total_w = el_surf.get_width() + 3 + to_surf.get_width()
        tx = label_x + (LABEL_W - total_w) // 2
        ty = rect.y + (rect.height - el_surf.get_height()) // 2
        screen.blit(el_surf, (tx, ty))
        screen.blit(to_surf, (tx + el_surf.get_width() + 3, ty))


def _fmt_time(s):
    m = int(s // 60)
    return f'{m}:{int(s % 60):02d}'
