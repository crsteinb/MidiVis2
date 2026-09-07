'''SlotManager — layout, rendering, and event dispatch for all slot panels
(Plan Part 3.4).

Fixes the two bugs Plan Part 2/3.4 call out in the old ui/slot_manager.py,
made while the panel system was being rebuilt rather than patched after:

1. **Click-priority-vs-visual-order mismatch**: the old handle_event() walked
   a hardcoded ('sheet', 'keyboard', 'properties') tuple regardless of how the
   user had actually dragged-to-reorder the slots, so e.g. dragging
   'properties' above 'sheet' never changed which one got first crack at a
   click. Here, non-timeline slots are dispatched in `self._order` — the same
   list drag-to-reorder mutates — so click priority always matches what's
   drawn. (In practice this is rarely observable since stacked slots don't
   overlap, but it's a real, previously-silent invariant violation, and it
   matters once a future slot ever *can* overlap, e.g. a floating panel.)
2. **Single-flex-slot limitation**: the old rects() gave 100% of the leftover
   height to *any* slot with fixed_height=None, so two simultaneously-flexible
   slots would fully overlap. rects() now splits leftover height evenly across
   however many flex slots are visible (remainder pixels go to the last one,
   so rounding never leaves a 1px gap at the bottom).

Also fixes render()'s O(n) per-slot rects() recomputation (Plan Part 2:
"rects() is redundantly recomputed once per slot per frame") — computed once
per render() call instead.
'''
from __future__ import annotations

import pygame

from midivis.render.slots.slot_base import SlotBase, HANDLE_W, C_DRAG_LINE


class SlotManager:
    def __init__(self, slots: list[SlotBase]) -> None:
        self._slots = {s.slot_id: s for s in slots}
        self._order = [s.slot_id for s in slots]
        self._heights: dict[str, int | None] = {s.slot_id: s.fixed_height for s in slots}
        self._hidden: set[str] = set()
        self._drag_id: str | None = None
        self._drag_y: int = 0

    # ── Layout ────────────────────────────────────────────────────────────

    def rects(self, content: pygame.Rect) -> dict[str, pygame.Rect]:
        cx, cy, cw, ch = content.x, content.y, content.width, content.height
        visible = [sid for sid in self._order if sid not in self._hidden]
        fixed_total = sum(h for sid in visible if (h := self._heights[sid]) is not None)
        flex_ids = [sid for sid in visible if self._heights[sid] is None]

        flex_total = max(0, ch - fixed_total)
        n_flex = len(flex_ids)
        flex_h = {}
        if n_flex:
            base = flex_total // n_flex
            for sid in flex_ids:
                flex_h[sid] = base
            flex_h[flex_ids[-1]] += flex_total - base * n_flex   # remainder

        rects, y = {}, cy
        for sid in visible:
            h = self._heights[sid]
            if h is None:
                h = max(20, flex_h[sid])
            rects[sid] = pygame.Rect(cx, y, cw, h)
            y += h
        return rects

    def set_height(self, slot_id: str, height: int) -> None:
        if slot_id in self._heights:
            self._heights[slot_id] = height

    def toggle_visible(self, slot_id: str) -> None:
        if slot_id in self._hidden:
            self._hidden.discard(slot_id)
        else:
            self._hidden.add(slot_id)

    def is_visible(self, slot_id: str) -> bool:
        return slot_id not in self._hidden

    def get_slot(self, slot_id: str) -> SlotBase | None:
        return self._slots.get(slot_id)

    @property
    def order(self) -> list[str]:
        return list(self._order)

    # ── Rendering ─────────────────────────────────────────────────────────

    def render(self, screen, content: pygame.Rect, app, fonts, settings) -> None:
        rects = self.rects(content)
        for sid in self._order:
            r = rects.get(sid)
            if r:
                self._slots[sid].draw(screen, r, app, fonts, settings)

    def draw_drag_indicator(self, screen, content: pygame.Rect) -> None:
        if self._drag_id is None:
            return
        rects = self.rects(content)
        pygame.draw.line(screen, C_DRAG_LINE,
                          (content.x, self._drag_y), (content.right, self._drag_y), 2)
        r = rects.get(self._drag_id)
        if r:
            s = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
            s.fill((0, 0, 0, 80))
            screen.blit(s, r.topleft)

    # ── Event dispatch ───────────────────────────────────────────────────

    def handle_event(self, event, content: pygame.Rect, app,
                      pre_reorder_cb=None, menu_open: bool = False) -> bool:
        '''Dispatch event to slots.

        Priority:
          1. Timeline (intercepts scrub drag before reorder logic runs)
          2. pre_reorder_cb (optional; used for the dashboard's track dropdown)
          3. Drag-to-reorder on handle strips
          4. All other visible slots, in current visual order (only when the
             menu bar isn't open)

        Returns True if the event was consumed.
        '''
        rects = self.rects(content)
        consumed = False

        tl = self._slots.get('timeline')
        tl_r = rects.get('timeline')
        if tl and tl_r and tl.handle_event(event, tl_r, app):
            consumed = True

        if not consumed and pre_reorder_cb is not None:
            consumed = bool(pre_reorder_cb(event))

        if not consumed and self._handle_drag(event, content):
            consumed = True

        if not consumed and not menu_open:
            for slot_id in self._order:
                if slot_id == 'timeline' or consumed:
                    continue
                slot = self._slots.get(slot_id)
                r = rects.get(slot_id)
                if not (slot and r):
                    continue
                result = slot.handle_event(event, r, app)
                if slot_id == 'properties' and result == 'properties_toggle':
                    props = self._slots.get('properties')
                    if props is not None:
                        new_h = (props.expanded_height(app)
                                 if getattr(app, 'properties_expanded', False)
                                 else props.fixed_height)
                        self.set_height('properties', new_h)
                    consumed = True
                elif result:
                    consumed = True

        return consumed

    # ── Internal drag-reorder ────────────────────────────────────────────

    def _handle_drag(self, event, content: pygame.Rect) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            rects = self.rects(content)
            for sid in self._order:
                if sid not in rects:
                    continue
                r = rects[sid]
                if pygame.Rect(r.x, r.y, HANDLE_W, r.height).collidepoint(event.pos):
                    self._drag_id = sid
                    self._drag_y = event.pos[1]
                    return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._drag_id is not None:
                self._finish_drag(event.pos[1], content)
                self._drag_id = None
                return True

        elif event.type == pygame.MOUSEMOTION:
            if self._drag_id is not None:
                self._drag_y = event.pos[1]
                return True

        return False

    def _finish_drag(self, mouse_y: int, content: pygame.Rect) -> None:
        rects = self.rects(content)
        centres = [(sid, rects[sid].centery)
                   for sid in self._order if sid != self._drag_id and sid in rects]
        if not centres:
            return
        target = min(centres, key=lambda sc: abs(mouse_y - sc[1]))[0]
        new_i = self._order.index(target)
        if mouse_y > rects[target].centery:
            new_i = min(new_i + 1, len(self._order) - 1)
        self._order.remove(self._drag_id)
        self._order.insert(new_i, self._drag_id)
