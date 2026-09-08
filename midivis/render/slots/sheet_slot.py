'''Dispatches the 'sheet' slot between BarsSlot and TraditionalSlot by
`app.view` (Plan Part 3.4/3.3).

Milestone 3 registered `BarsSlot` directly under the 'sheet' id in
`SlotManager` since traditional notation didn't exist yet ("no
render/slots/sheet_slot.py dispatcher this milestone" — see
FullRewriteStatus.md). This is that dispatcher, now that there's a second
view to pick between; `BarsSlot`/`TraditionalSlot` themselves are unchanged.

Also owns ctrl+wheel zoom / wheel scroll / horizontal-wheel seek — this used
to live in main.py as a special case that bypassed the slot `handle_event`
contract entirely (hand-rolled hit-testing against `slot_manager.rects(...)`,
direct writes to `app.sheet_zoom`/`app.bars_scroll`). That produced a real
bug: the scroll branch always wrote `bars_scroll` even when the traditional
view (which reads `trad_scroll`) was active, so wheel-scroll silently did
nothing there. Handling it here, where the active view is already known,
fixes that for free.
'''
from __future__ import annotations

import pygame

from midivis.render.slots.bars import BarsSlot
from midivis.render.slots.slot_base import SlotBase
from midivis.render.slots.traditional import TraditionalSlot

# Ctrl+wheel zoom bounds/step and plain-wheel scroll step, unchanged from the
# old main.py block. Max raised from 4.0 -- at MEASURES_VISIBLE=8
# (bars.py/traditional.py), 4.0 only ever got down to 2 measures across the
# full width, not enough to make individual notes/stems legible in a dense
# passage. 16.0 gets to half a measure -- room to raise further if still not
# tight enough.
_ZOOM_MIN, _ZOOM_MAX, _ZOOM_STEP = 0.25, 16.0, 1.15
_SCROLL_STEP = 0.08


class SheetSlot(SlotBase):
    fixed_height = None

    def __init__(self) -> None:
        super().__init__('sheet')
        self._bars = BarsSlot()
        self._traditional = TraditionalSlot()

    def _active(self, app):
        return self._traditional if getattr(app, 'view', 'bars') == 'traditional' else self._bars

    def handle_event(self, event, rect, app) -> bool | tuple[str, float]:
        if event.type == pygame.MOUSEWHEEL:
            return self._handle_wheel(event, rect, app)
        return self._active(app).handle_event(event, rect, app)

    def _handle_wheel(self, event, rect, app) -> bool | tuple[str, float]:
        # MOUSEWHEEL events carry no `pos` (unlike click/motion events), so
        # hit-testing needs the live cursor position instead of event data.
        if not getattr(app, 'loaded', False) or not rect.collidepoint(pygame.mouse.get_pos()):
            return False

        consumed = False
        if event.y != 0:
            if pygame.key.get_mods() & pygame.KMOD_CTRL:
                app.sheet_zoom = max(_ZOOM_MIN, min(_ZOOM_MAX, app.sheet_zoom * _ZOOM_STEP ** event.y))
            else:
                attr = 'trad_scroll' if getattr(app, 'view', 'bars') == 'traditional' else 'bars_scroll'
                current = getattr(app, attr, 0.0)
                setattr(app, attr, max(0.0, min(1.0, current + _SCROLL_STEP * (-event.y))))
            consumed = True
        if event.x != 0:
            return ('seek', (60.0 / app.bpm) * event.x)
        return consumed

    def draw(self, screen, rect, app, fonts, settings) -> None:
        self._active(app).draw(screen, rect, app, fonts, settings)
