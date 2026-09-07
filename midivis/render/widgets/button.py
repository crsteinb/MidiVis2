'''Shared Button widget (Plan Part 3.4) — replaces the copy that used to live
inline in the old ui/dashboard.py. Behavior is unchanged: enabled/selected/hover
states map to (bg, border, fg) triples pulled from the theme, with an optional
icon-drawing callback for the dashboard's icon+label buttons.
'''
from __future__ import annotations

import pygame


class Button:
    def __init__(self, rect, text: str = '') -> None:
        self.rect = pygame.Rect(rect)
        self.text = text
        self.enabled = True
        self.selected = False
        self._hover = False

    def update(self, pos) -> None:
        self._hover = self.enabled and self.rect.collidepoint(pos)

    def clicked(self, event) -> bool:
        return (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.enabled and self.rect.collidepoint(event.pos))

    def draw(self, screen, font, pal: dict, icon_fn=None) -> None:
        if not self.enabled:
            bg, border, fg = pal['btn_disabled']
        elif self.selected:
            bg, border, fg = pal['btn_selected']
        elif self._hover:
            bg, border, fg = pal['btn_hover']
        else:
            bg, border, fg = pal['btn_normal']

        pygame.draw.rect(screen, bg, self.rect, border_radius=6)
        pygame.draw.rect(screen, border, self.rect, 1, border_radius=6)

        if icon_fn:
            icon_fn(screen, self.rect, self.enabled)
            surf = font.render(self.text, True, fg)
            r = surf.get_rect(centery=self.rect.centery)
            r.left = self.rect.left + 32
            screen.blit(surf, r)
        elif self.text:
            lbl = font.render(self.text, True, fg)
            screen.blit(lbl, lbl.get_rect(center=self.rect.center))
