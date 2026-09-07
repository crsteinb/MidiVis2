'''Shared Menu/Submenu widget (Plan Part 3.4).

The old ui/menu_bar.py re-implemented the same "list of items, optional
separators, optional checkmark/arrow" hit-test/draw logic six times (File
dropdown, its Recent-files submenu, View dropdown, its Theme submenu, its
Slots submenu, Keyboard dropdown) with only width/anchor constants differing.
`Dropdown` here is the one parameterized component all six collapse onto;
`MenuBar` composes two Dropdown instances (top-level + one submenu level —
the old menu system never nested deeper than that) to drive them.

Item content is supplied via a zero-arg callable per top-level menu
(`items_fn`) rather than a static list, so it can reflect live state (recent
files, the current theme's checkmark, slot visibility checkmarks) without the
widget needing to know what any of that state means.
'''
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pygame

from midivis.render.fonts import symbol_font

ROW_H = 22
SEP_H = 9


@dataclass
class MenuItem:
    id: str
    label: str = ''
    checked: bool = False
    separator: bool = False
    enabled: bool = True
    # If set, selecting this item opens a nested Dropdown instead of firing
    # an action — evaluated lazily (each time the submenu opens) so it can
    # reflect state that changed since the parent menu was built.
    submenu_fn: Callable[[], list['MenuItem']] | None = None


@dataclass
class TopMenu:
    id: str
    label: str
    items_fn: Callable[[], list[MenuItem]]
    width: int = 200
    submenu_width: int = 220


class Dropdown:
    '''One flat list of MenuItems anchored at a screen position: hit-testing
    and drawing only, no open/closed state of its own (MenuBar owns that).
    '''

    def __init__(self, width: int = 200) -> None:
        self.width = width

    def height(self, items: list[MenuItem]) -> int:
        return sum(SEP_H if it.separator else ROW_H for it in items) + 8

    def rect(self, origin: tuple[int, int], items: list[MenuItem]) -> pygame.Rect:
        return pygame.Rect(origin[0], origin[1], self.width, self.height(items))

    def hit_test(self, pos, origin: tuple[int, int], items: list[MenuItem]) -> int | None:
        y = origin[1] + 2
        for i, it in enumerate(items):
            if it.separator:
                y += SEP_H
                continue
            if pygame.Rect(origin[0] + 1, y, self.width - 2, ROW_H).collidepoint(pos):
                return i
            y += ROW_H
        return None

    def item_y(self, origin: tuple[int, int], items: list[MenuItem], index: int) -> int:
        y = origin[1] + 2
        for i, it in enumerate(items):
            if i == index:
                return y
            y += SEP_H if it.separator else ROW_H
        return y

    def draw(self, screen, origin: tuple[int, int], items: list[MenuItem],
              font, pal: dict, hover_idx: int | None) -> None:
        r = self.rect(origin, items)
        pygame.draw.rect(screen, pal['drop_bg'], r, border_radius=3)
        pygame.draw.rect(screen, pal['drop_bor'], r, 1, border_radius=3)

        y = r.top + 2
        for i, it in enumerate(items):
            if it.separator:
                pygame.draw.line(screen, pal['drop_bor'],
                                  (r.left + 6, y + 4), (r.right - 6, y + 4))
                y += SEP_H
                continue
            row = pygame.Rect(r.left + 1, y, self.width - 2, ROW_H)
            if i == hover_idx:
                pygame.draw.rect(screen, pal['drop_sel'], row, border_radius=2)
            color = pal['menu_dim'] if not it.enabled else pal['menu_text']
            surf = font.render(it.label, True, color)
            screen.blit(surf, (row.left + 8, row.top + (ROW_H - surf.get_height()) // 2))

            if it.submenu_fn is not None:
                ar = symbol_font(font.get_height()).render('►', True, pal['menu_dim'])
                screen.blit(ar, (row.right - ar.get_width() - 6,
                                 row.top + (ROW_H - ar.get_height()) // 2))
            elif it.checked:
                ck = font.render('✓', True, pal['menu_dim'])
                screen.blit(ck, (row.right - ck.get_width() - 6, row.top + 4))
            y += ROW_H


class MenuBar:
    '''Top-level bar of named menus, each opening a Dropdown (and, for items
    with a submenu_fn, one nested Dropdown to the right).
    '''

    def __init__(self, menus: list[TopMenu], height: int = 24) -> None:
        self._menus = {m.id: m for m in menus}
        self._order = [m.id for m in menus]
        self.height = height
        self._top_rects: dict[str, pygame.Rect] | None = None

        self._open: str | None = None
        self._hover_idx: int | None = None
        self._sub_open_idx: int | None = None   # index into the open menu's items
        self._sub_items: list[MenuItem] = []
        self._sub_hover_idx: int | None = None

    def _layout(self, font) -> None:
        if self._top_rects is not None:
            return
        rects, x = {}, 0
        for mid in self._order:
            w = font.size(f'  {self._menus[mid].label}  ')[0]
            rects[mid] = pygame.Rect(x, 0, w, self.height)
            x += w
        self._top_rects = rects

    def close(self) -> None:
        self._open = None
        self._hover_idx = None
        self._sub_open_idx = None
        self._sub_items = []
        self._sub_hover_idx = None

    @property
    def is_open(self) -> bool:
        return self._open is not None

    def _sub_origin(self, top: TopMenu, anchor_y: int) -> tuple[int, int]:
        r = self._top_rects[top.id]
        return (r.left + top.width, anchor_y)

    def handle_event(self, event, font) -> str | None:
        '''Returns a leaf item's id when one is selected, 'consumed' when the
        event was swallowed without producing an action (e.g. closing a menu
        via Escape), or None if the event wasn't ours.
        '''
        self._layout(font)

        if event.type == pygame.MOUSEMOTION:
            pos = event.pos
            if pos[1] < self.height:
                self._hover_idx = self._sub_hover_idx = None
                if self._open is not None:
                    for mid, r in self._top_rects.items():
                        if r.collidepoint(pos) and mid != self._open:
                            self._open = mid
                            self._sub_open_idx = None
                            self._sub_items = []
                return None
            if self._open is None:
                return None

            top = self._menus[self._open]
            items = top.items_fn()
            drop = Dropdown(top.width)
            origin = (self._top_rects[self._open].left, self.height)
            hit = drop.hit_test(pos, origin, items)
            self._hover_idx = hit

            if hit is not None and items[hit].submenu_fn is not None:
                if self._sub_open_idx != hit:
                    self._sub_open_idx = hit
                    self._sub_items = items[hit].submenu_fn()
                anchor_y = drop.item_y(origin, items, hit)
                sub_origin = self._sub_origin(top, anchor_y)
                sub_drop = Dropdown(top.submenu_width)
                self._sub_hover_idx = sub_drop.hit_test(pos, sub_origin, self._sub_items)
            elif self._sub_open_idx is not None:
                top_local = top
                anchor_y = drop.item_y(origin, items, self._sub_open_idx)
                sub_origin = self._sub_origin(top_local, anchor_y)
                sub_drop = Dropdown(top.submenu_width)
                if not sub_drop.rect(sub_origin, self._sub_items).collidepoint(pos):
                    self._sub_open_idx = None
                    self._sub_items = []
                    self._sub_hover_idx = None
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos

            for mid, r in self._top_rects.items():
                if r.collidepoint(pos):
                    self._open = None if self._open == mid else mid
                    self._hover_idx = self._sub_hover_idx = None
                    self._sub_open_idx = None
                    self._sub_items = []
                    return None

            if self._open is None:
                return None
            top = self._menus[self._open]
            items = top.items_fn()
            drop = Dropdown(top.width)
            origin = (self._top_rects[self._open].left, self.height)

            if self._sub_open_idx is not None:
                anchor_y = drop.item_y(origin, items, self._sub_open_idx)
                sub_origin = self._sub_origin(top, anchor_y)
                sub_drop = Dropdown(top.submenu_width)
                hit_sub = sub_drop.hit_test(pos, sub_origin, self._sub_items)
                if hit_sub is not None and self._sub_items[hit_sub].enabled:
                    item_id = self._sub_items[hit_sub].id
                    self.close()
                    return item_id

            hit = drop.hit_test(pos, origin, items)
            if hit is not None:
                it = items[hit]
                if it.submenu_fn is not None:
                    return None   # opens on hover; click does nothing extra
                if it.enabled:
                    self.close()
                    return it.id
            self.close()
            return None

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self._open:
            self.close()
            return 'consumed'

        return None

    def draw(self, screen, font, pal: dict, win_w: int) -> None:
        self._layout(font)
        pygame.draw.rect(screen, pal['menu_bg'], (0, 0, win_w, self.height))
        pygame.draw.line(screen, pal['menu_line'], (0, self.height - 1), (win_w, self.height - 1))

        for mid in self._order:
            r = self._top_rects[mid]
            active = self._open == mid
            pygame.draw.rect(screen, pal['drop_sel'] if active else pal['menu_bg'], r)
            lbl = font.render(self._menus[mid].label, True, pal['menu_text'])
            screen.blit(lbl, lbl.get_rect(center=r.center))

        if self._open is None:
            return
        top = self._menus[self._open]
        items = top.items_fn()
        drop = Dropdown(top.width)
        origin = (self._top_rects[self._open].left, self.height)
        drop.draw(screen, origin, items, font, pal, self._hover_idx)

        if self._sub_open_idx is not None:
            anchor_y = drop.item_y(origin, items, self._sub_open_idx)
            sub_origin = self._sub_origin(top, anchor_y)
            sub_drop = Dropdown(top.submenu_width)
            sub_drop.draw(screen, sub_origin, self._sub_items, font, pal, self._sub_hover_idx)
