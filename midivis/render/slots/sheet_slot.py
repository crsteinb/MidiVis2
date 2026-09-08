'''Dispatches the 'sheet' slot between BarsSlot and TraditionalSlot by
`app.view` (Plan Part 3.4/3.3).

Milestone 3 registered `BarsSlot` directly under the 'sheet' id in
`SlotManager` since traditional notation didn't exist yet ("no
render/slots/sheet_slot.py dispatcher this milestone" — see
FullRewriteStatus.md). This is that dispatcher, now that there's a second
view to pick between; `BarsSlot`/`TraditionalSlot` themselves are unchanged.
'''
from __future__ import annotations

from midivis.render.slots.bars import BarsSlot
from midivis.render.slots.slot_base import SlotBase
from midivis.render.slots.traditional import TraditionalSlot


class SheetSlot(SlotBase):
    fixed_height = None

    def __init__(self) -> None:
        super().__init__('sheet')
        self._bars = BarsSlot()
        self._traditional = TraditionalSlot()

    def _active(self, app):
        return self._traditional if getattr(app, 'view', 'bars') == 'traditional' else self._bars

    def handle_event(self, event, rect, app) -> bool:
        return self._active(app).handle_event(event, rect, app)

    def draw(self, screen, rect, app, fonts, settings) -> None:
        self._active(app).draw(screen, rect, app, fonts, settings)
