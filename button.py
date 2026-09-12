"""Done: the one event worth a button."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NAME
from .coordinator import HouseCleaningConfigEntry
from .entity import ChoreEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: HouseCleaningConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    for sid, sub in entry.subentries.items():
        async_add_entities(
            [DoneButton(coordinator, sid, sub.data.get(CONF_NAME, sub.title))],
            config_subentry_id=sid,
        )


class DoneButton(ChoreEntity, ButtonEntity):
    """Stamps now. A backdated completion, or undoing one, is the
    `mark_done` / `undo` action -- a button has no fields."""

    _attr_translation_key = "done"

    def __init__(self, coordinator, subentry_id: str, name: str) -> None:
        super().__init__(coordinator, subentry_id, name, "done")

    async def async_press(self) -> None:
        await self.coordinator.async_mark_done(self._subentry_id)
