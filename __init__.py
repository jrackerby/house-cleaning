"""House Cleaning -- household chores by room, each with a cadence and a
last-done record."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CONF_AREA, CONF_NAME, DOMAIN
from .coordinator import HouseCleaningConfigEntry, HouseCleaningCoordinator
from .entity import MANUFACTURER, chore_identifier
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.TODO,
]

# Nothing here is configurable from YAML; the entry is the only way in.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the domain's actions, once, whether or not an entry exists.

    In `async_setup` rather than `async_setup_entry` deliberately: an action
    registered per-entry disappears while the entry reloads, so a board
    calling it mid-reload gets "service not found" instead of an answer.
    """
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HouseCleaningConfigEntry) -> bool:
    coordinator = HouseCleaningCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_prune()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _place_chore_devices(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Adding, editing or removing a chore is a subentry change, and a subentry
    # change does not reload the entry on its own -- without this a chore
    # added in the UI appears only after a restart.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


def _place_chore_devices(hass: HomeAssistant, entry: HouseCleaningConfigEntry) -> None:
    """Create each chore's device and put it in the room its subentry names.

    THE SUBENTRY'S ROOM WINS WHENEVER IT IS SET. The add form asks for a
    room so nobody has to add a chore, then go find its device, then set an
    area by hand -- the friction waste_collection's receptacle flow left in
    place. The cost is that dragging the device to another area in the
    device UI is undone on the next reload; edit the chore instead. A chore
    whose subentry names no room keeps whatever area the device UI gave it.
    """
    registry = dr.async_get(hass)
    for sid, sub in entry.subentries.items():
        device = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=sid,
            identifiers={chore_identifier(entry.entry_id, sid)},
            name=sub.data.get(CONF_NAME, sub.title),
            manufacturer=MANUFACTURER,
            model="Chore",
        )
        area = sub.data.get(CONF_AREA)
        if area and device.area_id != area:
            registry.async_update_device(device.id, area_id=area)


async def _async_reload(hass: HomeAssistant, entry: HouseCleaningConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HouseCleaningConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass: HomeAssistant, entry: HouseCleaningConfigEntry, device) -> bool:
    """Let a stale chore device be deleted from the UI, and refuse one the
    entry still owns."""
    live = {chore_identifier(entry.entry_id, sid)[1] for sid in entry.subentries}
    live.add(entry.entry_id)
    return not any(ident[1] in live for ident in device.identifiers if ident[0] == DOMAIN)
