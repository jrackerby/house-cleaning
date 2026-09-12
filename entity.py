"""DeviceInfo, defined once.

TWO KINDS OF DEVICE. A CHORE device is one job in one room, created from a
config subentry; it gets its own device row precisely so it carries an AREA
-- that is what "by room" means here, and nothing parses a room out of an
entity id. Its identifier keys on the SUBENTRY id, never the name, so
renaming "Vacuum the kitchen" to "Vacuum kitchen floor" cannot orphan its
device and mint a second one alongside. The ROLL-UP device is the house:
one per entry, the counts an automation reads.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HouseCleaningCoordinator

MANUFACTURER = "El Coronel Luz"


def chore_identifier(entry_id: str, subentry_id: str) -> tuple[str, str]:
    return (DOMAIN, f"chore_{subentry_id}")


def chore_device_info(entry_id: str, subentry_id: str, name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={chore_identifier(entry_id, subentry_id)},
        name=name,
        manufacturer=MANUFACTURER,
        model="Chore",
    )


def house_device_info(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="House Cleaning",
        manufacturer=MANUFACTURER,
        model="Household chores",
    )


class HouseCleaningEntity(CoordinatorEntity[HouseCleaningCoordinator]):
    """Base for everything this integration publishes. `_attr_has_entity_name`
    so ids slug from the device name: sensor.vacuum_kitchen_floor_next_due."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HouseCleaningCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_{unique_suffix}"

    @property
    def available(self) -> bool:
        # A chore nobody has done is a real, reportable state, and the
        # coordinator never fails. Nothing here is ever "unavailable".
        return True


class ChoreEntity(HouseCleaningEntity):
    """An entity belonging to one chore, created from a subentry."""

    def __init__(self, coordinator: HouseCleaningCoordinator, subentry_id: str, name: str, key: str) -> None:
        super().__init__(coordinator, f"{subentry_id}_{key}")
        self._subentry_id = subentry_id
        self._attr_device_info = chore_device_info(coordinator.entry_id, subentry_id, name)

    @property
    def row(self) -> dict:
        return self.coordinator.data["chores"].get(self._subentry_id) or {}


class HouseEntity(HouseCleaningEntity):
    """An entity on the roll-up device."""

    def __init__(self, coordinator: HouseCleaningCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_device_info = house_device_info(coordinator.entry_id)
