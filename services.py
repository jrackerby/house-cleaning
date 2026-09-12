"""The three actions: `mark_done` (with a date, for backfilling), `undo`
(a mis-tap), and `set_interval` (a cadence, from a board rather than from
Settings).

WHY A SERVICE FOR THE CADENCE. A chore's interval is subentry DATA, and
subentry data is reachable only through the subentry flow -- a form in
Settings. A dashboard has `callService` and nothing else, so without this
action a cadence is editable from Settings and from nowhere else.

WHAT THEY REFUSE, AND WHY THAT IS THE FEATURE. Home Assistant answers a
service call 200 even on a silent no-op, so a board cannot tell a stored
change from an ignored one. Every refusal is a `ServiceValidationError`
with a translation key -- the one class HA reports back to the caller.

EVERY VALUE CHECK LIVES IN `chores.py`, none in the schemas below, so the
suite that runs with Home Assistant absent can reach them.

ADDRESSING. Each action takes `entity_id`: ANY entity on the chore's device
(its done button, its next-due sensor). The entity registry row carries
the subentry it was created against, which is the chore -- so a board
addresses a chore by an id it discovered and never has to learn a subentry
id, and a renamed chore keeps working because the id is frozen at creation.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .chores import ChoreValueError, parse_done_at, validate_interval
from .const import CONF_INTERVAL, DOMAIN

SERVICE_MARK_DONE = "mark_done"
SERVICE_UNDO = "undo"
SERVICE_SET_INTERVAL = "set_interval"

ATTR_ENTITY_ID = "entity_id"
ATTR_DONE_AT = "done_at"

MARK_DONE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_DONE_AT): vol.Any(None, cv.string),
    }
)
UNDO_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})
SET_INTERVAL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(CONF_INTERVAL): vol.Any(int, float, cv.string),
    }
)


def _resolve(hass: HomeAssistant, entity_id: str):
    """The (entry, subentry) an entity belongs to, or a caller-visible error."""
    row = er.async_get(hass).async_get(entity_id)
    if row is None or row.platform != DOMAIN or not row.config_entry_id:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_a_chore",
            translation_placeholders={"entity_id": entity_id},
        )
    entry = hass.config_entries.async_get_entry(row.config_entry_id)
    subentry = entry.subentries.get(row.config_subentry_id) if entry and row.config_subentry_id else None
    if entry is None or subentry is None or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_a_chore",
            translation_placeholders={"entity_id": entity_id},
        )
    return entry, subentry


def _refuse(err: ChoreValueError) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_value",
        translation_placeholders={"field": str(err.field), "value": str(err.value)},
    )


async def _async_mark_done(call: ServiceCall) -> None:
    entry, subentry = _resolve(call.hass, call.data[ATTR_ENTITY_ID])
    try:
        done = parse_done_at(call.data.get(ATTR_DONE_AT), dt_util.now().date())
    except ChoreValueError as err:
        raise _refuse(err) from err
    await entry.runtime_data.async_mark_done(subentry.subentry_id, done)


async def _async_undo(call: ServiceCall) -> None:
    entry, subentry = _resolve(call.hass, call.data[ATTR_ENTITY_ID])
    if not await entry.runtime_data.async_undo(subentry.subentry_id):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="nothing_to_undo",
            translation_placeholders={"name": subentry.title},
        )


async def _async_set_interval(call: ServiceCall) -> None:
    entry, subentry = _resolve(call.hass, call.data[ATTR_ENTITY_ID])
    try:
        days = validate_interval(call.data[CONF_INTERVAL])
    except ChoreValueError as err:
        raise _refuse(err) from err
    if subentry.data.get(CONF_INTERVAL) == days:
        return
    # A subentry update fires the entry's update listener, which reloads it;
    # the new cadence is live on the next reduction.
    call.hass.config_entries.async_update_subentry(
        entry, subentry, data={**subentry.data, CONF_INTERVAL: days}
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the domain's actions. Called once, from `async_setup`."""
    hass.services.async_register(DOMAIN, SERVICE_MARK_DONE, _async_mark_done, schema=MARK_DONE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UNDO, _async_undo, schema=UNDO_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SET_INTERVAL, _async_set_interval, schema=SET_INTERVAL_SCHEMA
    )
