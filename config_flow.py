"""Setup, the options flow, and the chore subentry flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .chores import ChoreValueError, validate_interval, validate_soon_days
from .const import (
    CONF_AREA,
    CONF_INTERVAL,
    CONF_NAME,
    CONF_SOON_DAYS,
    CONF_STARTER_SET,
    DEFAULT_INTERVAL,
    DEFAULT_SOON_DAYS,
    DOMAIN,
    MAX_INTERVAL,
    MAX_SOON_DAYS,
    MIN_INTERVAL,
    MIN_SOON_DAYS,
    STARTER_CHORES,
    SUBENTRY_CHORE,
)


def _chore_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Name, room, cadence. The ROOM IS ASKED FOR HERE, on purpose: an
    AreaSelector offers the house's real area list, so there is no second
    copy of the room list to drift, and nobody has to add a chore and then
    go looking for its device to file it. Optional, because "wipe the
    counters" belongs to the kitchen and "vacuum the stairs" belongs to no
    single room."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)): selector.TextSelector(),
            vol.Optional(
                CONF_AREA, description={"suggested_value": defaults.get(CONF_AREA)}
            ): selector.AreaSelector(),
            vol.Required(
                CONF_INTERVAL, default=defaults.get(CONF_INTERVAL, DEFAULT_INTERVAL)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_INTERVAL,
                    max=MAX_INTERVAL,
                    step=1,
                    unit_of_measurement="days",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _clean_chore(user_input: dict[str, Any]) -> dict[str, Any]:
    """The subentry's stored shape. The number selector hands back a float;
    a cadence is stored as the int it is, and a blank room is stored as
    absent rather than as an empty string a reader would then have to
    treat as a room called ''."""
    data: dict[str, Any] = {
        CONF_NAME: user_input[CONF_NAME].strip(),
        CONF_INTERVAL: validate_interval(user_input[CONF_INTERVAL]),
    }
    area = user_input.get(CONF_AREA)
    if area:
        data[CONF_AREA] = area
    return data


class HouseCleaningConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            subentries: list[ConfigSubentryData] = []
            if user_input.get(CONF_STARTER_SET, True):
                subentries = [
                    ConfigSubentryData(
                        data={CONF_NAME: name, CONF_INTERVAL: days},
                        subentry_type=SUBENTRY_CHORE,
                        title=name,
                        unique_id=None,
                    )
                    for name, days in STARTER_CHORES
                ]
            return self.async_create_entry(
                title="House Cleaning",
                data={},
                options={CONF_SOON_DAYS: DEFAULT_SOON_DAYS},
                subentries=subentries,
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_STARTER_SET, default=True): bool}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HouseCleaningOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_CHORE: ChoreSubentryFlow}


class HouseCleaningOptionsFlow(OptionsFlow):
    """One step, one option. Merged over the existing options rather than
    replacing them (`async_create_entry(data=...)` replaces `entry.options`
    wholesale), so a second option added later does not delete this one."""

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                soon = validate_soon_days(user_input[CONF_SOON_DAYS])
            except ChoreValueError:
                errors[CONF_SOON_DAYS] = "invalid_soon_days"
            else:
                return self.async_create_entry(
                    title="", data={**self.config_entry.options, CONF_SOON_DAYS: soon}
                )
        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SOON_DAYS,
                        default=self.config_entry.options.get(CONF_SOON_DAYS, DEFAULT_SOON_DAYS),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_SOON_DAYS,
                            max=MAX_SOON_DAYS,
                            step=1,
                            unit_of_measurement="days",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )


class ChoreSubentryFlow(ConfigSubentryFlow):
    """Add or edit one chore. A chore is a SUBENTRY rather than a row in
    options because that is what gives it its own device, and a device is
    what carries an area."""

    async def async_step_user(self, user_input=None) -> SubentryFlowResult:
        return await self.async_step_add()

    async def async_step_add(self, user_input=None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _clean_chore(user_input)
            except ChoreValueError:
                errors[CONF_INTERVAL] = "invalid_interval"
            else:
                if not data[CONF_NAME]:
                    errors[CONF_NAME] = "empty_name"
                else:
                    return self.async_create_entry(title=data[CONF_NAME], data=data)
        return self.async_show_form(
            step_id="add", errors=errors, data_schema=_chore_schema(user_input or {})
        )

    async def async_step_reconfigure(self, user_input=None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _clean_chore(user_input)
            except ChoreValueError:
                errors[CONF_INTERVAL] = "invalid_interval"
            else:
                if not data[CONF_NAME]:
                    errors[CONF_NAME] = "empty_name"
                else:
                    return self.async_update_and_abort(
                        self._get_entry(), subentry, title=data[CONF_NAME], data=data
                    )
        return self.async_show_form(
            step_id="reconfigure",
            errors=errors,
            data_schema=_chore_schema(user_input or dict(subentry.data)),
        )
