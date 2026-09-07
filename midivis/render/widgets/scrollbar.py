'''Shared vertical scrollbar widget (Plan Part 3.4).

The old repo reimplemented drag-thumb scrolling independently in
ui/slots/bars_sheet.py (the piano-roll's vertical scroll) and, in a lighter
read-only form, ui/dashboard.py's track dropdown — this is the one shared
implementation both should sit on. Pure geometry/event logic; callers own the
scroll fraction (a float in [0, 1]) as state.
'''
from __future__ import annotations

import pygame


class VerticalScrollbar:
    def __init__(self, width: int = 10) -> None:
        self.width = width
        self._dragging = False
        self._start_y = 0
        self._start_frac = 0.0

    def is_needed(self, content_h: float, visible_h: float) -> bool:
        return content_h > visible_h

    def thumb_rect(self, track: pygame.Rect, content_h: float,
                    visible_h: float, frac: float) -> pygame.Rect | None:
        if not self.is_needed(content_h, visible_h):
            return None
        thumb_h = max(20, int(track.height * visible_h / content_h))
        thumb_y = track.y + int(frac * (track.height - thumb_h))
        return pygame.Rect(track.x, thumb_y, track.width, thumb_h)

    def handle_event(self, event, track: pygame.Rect, content_h: float,
                      visible_h: float, frac: float) -> float | None:
        '''Returns the updated scroll fraction, or None if this event didn't
        change it (either not consumed, or a drag-in-progress with no travel).
        '''
        if self._dragging:
            if event.type == pygame.MOUSEMOTION:
                thumb = self.thumb_rect(track, content_h, visible_h, frac)
                travel = track.height - (thumb.height if thumb else 0)
                if travel <= 0:
                    return None
                delta = (event.pos[1] - self._start_y) / travel
                return max(0.0, min(1.0, self._start_frac + delta))
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._dragging = False
            return None

        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.is_needed(content_h, visible_h)
                and track.collidepoint(event.pos)):
            self._dragging = True
            self._start_y = event.pos[1]
            self._start_frac = frac
            return frac

        return None

    @property
    def dragging(self) -> bool:
        return self._dragging

    def draw(self, screen, track: pygame.Rect, content_h: float,
              visible_h: float, frac: float, pal: dict) -> None:
        if not self.is_needed(content_h, visible_h):
            return
        pygame.draw.rect(screen, pal['sb_track'], track)
        thumb = self.thumb_rect(track, content_h, visible_h, frac)
        if thumb:
            pygame.draw.rect(screen, pal['sb_thumb'], thumb, border_radius=3)
