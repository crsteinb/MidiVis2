'''Shared single-line text input widget (Plan Part 3.4).

Replaces the hand-rolled cursor/insert/delete/click-to-position code that used
to live inline in the old ui/dashboard.py's record-arm track-name field
(cursor blink, arrow-key/Home/End/Backspace/Delete navigation, click-to-cursor
by measuring glyph widths). Nothing in Milestone 3's scope uses this yet — the
record-arm panel it was extracted from is Milestone 5 (recording) — but it's
built now, as its own tested unit, per Plan Part 3.4's widget list, so M5 can
wire it in directly instead of re-deriving this logic.

Pure editing-state logic lives here (handle_key/click_to_cursor), separate
from draw(), so it's testable without a real display surface.
'''
from __future__ import annotations

import pygame


class TextInput:
    def __init__(self, text: str = '') -> None:
        self.text = text
        self.cursor = len(text)
        self.focused = False

    def set_text(self, text: str) -> None:
        self.text = text
        self.cursor = len(text)

    def handle_key(self, event) -> bool:
        '''Apply a pygame.KEYDOWN event. Returns True if it was consumed
        (caller should not also treat it as a global hotkey).
        '''
        if event.type != pygame.KEYDOWN:
            return False
        if event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_TAB):
            self.focused = False
        elif event.key == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
        elif event.key == pygame.K_RIGHT:
            self.cursor = min(len(self.text), self.cursor + 1)
        elif event.key == pygame.K_HOME:
            self.cursor = 0
        elif event.key == pygame.K_END:
            self.cursor = len(self.text)
        elif event.key == pygame.K_BACKSPACE:
            if self.cursor > 0:
                self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
        elif event.key == pygame.K_DELETE:
            if self.cursor < len(self.text):
                self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        elif event.unicode and event.unicode.isprintable():
            self.text = self.text[:self.cursor] + event.unicode + self.text[self.cursor:]
            self.cursor += 1
        else:
            return False
        return True

    def click_to_cursor(self, click_x: float, field_left: float, font,
                         scroll_x: float = 0) -> None:
        '''Move the cursor to the character boundary closest to a click at
        click_x (screen space), given the field's left edge and current
        horizontal scroll offset.
        '''
        target = click_x - field_left + scroll_x
        best_i, best_d = 0, float('inf')
        for i in range(len(self.text) + 1):
            d = abs(font.size(self.text[:i])[0] - target)
            if d < best_d:
                best_d, best_i = d, i
        self.cursor = best_i

    def draw(self, screen, rect: pygame.Rect, font, text_color, cursor_color,
              blink: bool = True) -> None:
        '''Render the (possibly scrolled, so the cursor stays visible) text
        and a blinking caret when focused.
        '''
        clip_w = rect.width - 8
        full_surf = font.render(self.text, True, text_color)
        full_w = full_surf.get_width()
        cursor_px = font.size(self.text[:self.cursor])[0]
        scroll_x = max(0, min(cursor_px - clip_w + 4, full_w - clip_w)) if full_w > clip_w else 0

        if full_w > clip_w:
            src_x = max(0, min(scroll_x, full_w - clip_w))
            text_surf = full_surf.subsurface((src_x, 0, clip_w, full_surf.get_height()))
        else:
            text_surf = full_surf

        ty = rect.centery - text_surf.get_height() // 2
        screen.blit(text_surf, (rect.left + 4, ty))

        if self.focused and (not blink or (pygame.time.get_ticks() // 500) % 2 == 0):
            cx = rect.left + 4 + (cursor_px - scroll_x)
            cx = max(rect.left + 4, min(cx, rect.right - 4))
            pygame.draw.line(screen, cursor_color, (cx, rect.top + 4), (cx, rect.bottom - 4))
