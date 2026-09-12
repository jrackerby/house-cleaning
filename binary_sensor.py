"""Is this chore due; is anything in the house overdue."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NAME, DUE_STATUSES
from .coordinator import HouseCleaningConfigEntry
from .entity import ChoreEntity, HouseEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: HouseCleaningConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([OverdueBinarySensor(coordinator)])
    for sid, sub in entry.subentries.items():
        async_add_entities(
            [DueBinarySensor(coordinator, sid, sub.data.get(CONF_NAME, sub.title))],
            config_subentry_id=sid,
        )


class DueBinarySensor(ChoreEntity, BinarySensorEntity):
    """On when the chore is due today or overdue. `status` carries the case
    is_on cannot: soon, never, ok."""

    _attr_translation_key = "due"

    def __init__(self, coordinator, subentry_id: str, name: str) -> None:
        super().__init__(coordinator, subentry_id, name, "due")

    @property
    def is_on(self) -> bool:
        state = self.row.get("state")
        return bool(state and state.status in DUE_STATUSES)

    @property
    def extra_state_attributes(self) -> dict:
        state = self.row.get("state")
        return {
            "status": state.status if state else None,
            "days_until": state.days_until if state else None,
            "area": self.row.get("area"),
        }


class OverdueBinarySensor(HouseEntity, BinarySensorEntity):
    _attr_translation_key = "overdue"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "overdue")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.rollup()["overdue_items"])

    @property
    def extra_state_attributes(self) -> dict:
        r = self.coordinator.rollup()
        return {"overdue_items": r["overdue_items"], "due_count": r["due_count"]}
