"""The real layout against real core: entry + subentries -> entities -> writes."""
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _today():
    """The calendar the integration itself keeps.

    NOT ``date.today()``: that is the runner's clock, which is UTC in CI, while
    the coordinator dates everything with ``dt_util.now().date()`` under the
    fixture's time zone. The two disagree by a day for the hours where UTC
    and HA-local straddle midnight, and a backfill built on the wrong one
    read ``days_until`` off by one only in the evening (#1).
    """
    return dt_util.now().date()

DOMAIN = "house_cleaning"


async def _setup(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN, title="House Cleaning", data={}, options={"soon_days": 2},
        subentries_data=[
            ConfigSubentryData(data={"name": "Vacuum kitchen floor", "area": "kitchen_all", "interval_days": 7}, subentry_type="chore", title="Vacuum kitchen floor", unique_id=None),
            ConfigSubentryData(data={"name": "Clean windows", "interval_days": 90}, subentry_type="chore", title="Clean windows", unique_id=None),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities_devices_and_area(hass: HomeAssistant):
    entry = await _setup(hass)
    ids = sorted(s.entity_id for s in hass.states.async_all() if s.entity_id.split(".")[1].startswith(("vacuum_kitchen", "clean_windows", "house_cleaning")))
    print(ids)
    assert "sensor.vacuum_kitchen_floor_next_due" in ids
    assert "sensor.vacuum_kitchen_floor_last_done" in ids
    assert "binary_sensor.vacuum_kitchen_floor_due" in ids
    assert "button.vacuum_kitchen_floor_done" in ids
    assert "sensor.house_cleaning_due_count" in ids
    assert "sensor.house_cleaning_next_chore" in ids
    assert "binary_sensor.house_cleaning_overdue" in ids

    # never done: unknown, status never, not in the due count
    nd = hass.states.get("sensor.vacuum_kitchen_floor_next_due")
    assert nd.state == "unknown" and nd.attributes["status"] == "never"
    assert hass.states.get("sensor.house_cleaning_due_count").state == "0"
    assert hass.states.get("sensor.house_cleaning_due_count").attributes["never_items"] == ["Clean windows", "Vacuum kitchen floor"]

    # the chore's device sits in the room the subentry named
    reg = er.async_get(hass)
    row = reg.async_get("button.vacuum_kitchen_floor_done")
    dev = dr.async_get(hass).async_get(row.device_id)
    assert dev.area_id == "kitchen_all"
    assert row.config_subentry_id in entry.subentries
    # and the roomless one has none
    row2 = reg.async_get("button.clean_windows_done")
    assert dr.async_get(hass).async_get(row2.device_id).area_id is None


async def test_done_button_then_services(hass: HomeAssistant):
    await _setup(hass)
    await hass.services.async_call("button", "press", {"entity_id": "button.vacuum_kitchen_floor_done"}, blocking=True)
    await hass.async_block_till_done()
    nd = hass.states.get("sensor.vacuum_kitchen_floor_next_due")
    assert nd.attributes["status"] == "ok" and nd.attributes["days_until"] == 7
    assert hass.states.get("sensor.vacuum_kitchen_floor_last_done").state != "unknown"
    assert hass.states.get("sensor.house_cleaning_next_chore").state == "Vacuum kitchen floor"

    # backfill 10 days ago -> latest stays today; history has 2
    ten_ago = (_today() - timedelta(days=10)).isoformat()
    await hass.services.async_call(DOMAIN, "mark_done", {"entity_id": "sensor.vacuum_kitchen_floor_next_due", "done_at": ten_ago}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.vacuum_kitchen_floor_last_done").attributes["done_count"] == 2
    assert hass.states.get("sensor.vacuum_kitchen_floor_next_due").attributes["days_until"] == 7

    # undo twice -> back to never; a third undo is refused
    await hass.services.async_call(DOMAIN, "undo", {"entity_id": "button.vacuum_kitchen_floor_done"}, blocking=True)
    await hass.services.async_call(DOMAIN, "undo", {"entity_id": "button.vacuum_kitchen_floor_done"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.vacuum_kitchen_floor_next_due").attributes["status"] == "never"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "undo", {"entity_id": "button.vacuum_kitchen_floor_done"}, blocking=True)

    # a future date is refused, a bad interval is refused, a not-a-chore is refused
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "mark_done", {"entity_id": "button.vacuum_kitchen_floor_done", "done_at": (_today() + timedelta(days=1)).isoformat()}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_interval", {"entity_id": "button.vacuum_kitchen_floor_done", "interval_days": 0}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "undo", {"entity_id": "sensor.house_cleaning_due_count"}, blocking=True)

    # set_interval reloads the entry with the new cadence
    await hass.services.async_call(DOMAIN, "set_interval", {"entity_id": "button.vacuum_kitchen_floor_done", "interval_days": 3}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.vacuum_kitchen_floor_next_due").attributes["interval_days"] == 3


async def test_overdue_after_backfill(hass: HomeAssistant):
    await _setup(hass)
    await hass.services.async_call(DOMAIN, "mark_done", {"entity_id": "button.clean_windows_done", "done_at": (_today() - timedelta(days=100)).isoformat()}, blocking=True)
    await hass.async_block_till_done()
    nd = hass.states.get("sensor.clean_windows_next_due")
    assert nd.attributes["status"] == "overdue" and nd.attributes["days_until"] == -10
    assert hass.states.get("binary_sensor.clean_windows_due").state == "on"
    assert hass.states.get("binary_sensor.house_cleaning_overdue").state == "on"
    assert hass.states.get("sensor.house_cleaning_due_count").state == "1"
    assert hass.states.get("sensor.house_cleaning_due_count").attributes["by_room"] == {"": {"total": 1, "due": 1, "never": 0}, "kitchen_all": {"total": 1, "due": 0, "never": 1}}


async def test_config_flow_seeds_starter_set(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"starter_set": True})
    assert result["type"] == "create_entry"
    entry = result["result"]
    assert len(entry.subentries) == 9
    await hass.async_block_till_done()
    assert hass.states.get("sensor.vacuum_floors_next_due") is not None


async def test_subentry_flow_add_and_reconfigure(hass: HomeAssistant):
    entry = await _setup(hass)
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "chore"), context={"source": "user"})
    assert result["type"] == "form" and result["step_id"] == "add"
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "  Scrub tub ", "area": "main_bath_all", "interval_days": 14.0})
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    sub = next(s for s in entry.subentries.values() if s.title == "Scrub tub")
    assert sub.data == {"name": "Scrub tub", "interval_days": 14, "area": "main_bath_all"}
    assert hass.states.get("sensor.scrub_tub_next_due") is not None

    # a fractional or out-of-range interval never reaches storage: the
    # NumberSelector (min 1, step 1) refuses it at the schema
    from homeassistant.data_entry_flow import InvalidData
    for bad in (0.5, 0, 400):
        result = await hass.config_entries.subentries.async_init((entry.entry_id, "chore"), context={"source": "user"})
        with pytest.raises(InvalidData):
            await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "X", "interval_days": bad})

    # reconfigure moves the room and the device follows on reload
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "chore"), context={"source": "reconfigure", "subentry_id": sub.subentry_id})
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"name": "Scrub tub", "area": "bath_1_all", "interval_days": 14})
    assert result["type"] == "abort"
    await hass.async_block_till_done()
    row = er.async_get(hass).async_get("button.scrub_tub_done")
    assert dr.async_get(hass).async_get(row.device_id).area_id == "bath_1_all"


# -- the to-do list --------------------------------------------------------

async def _items(hass: HomeAssistant, **kw) -> dict[str, dict]:
    """The list as `todo.get_items` returns it, keyed by summary."""
    resp = await hass.services.async_call("todo", "get_items", {"entity_id": "todo.house_cleaning", **kw}, blocking=True, return_response=True)
    return {i["summary"]: i for i in resp["todo.house_cleaning"]["items"]}


async def test_todo_list_view(hass: HomeAssistant):
    """One item per chore; never/overdue/due/soon unchecked, ok checked."""
    await _setup(hass)
    assert hass.states.get("todo.house_cleaning").state == "2"  # both never done
    items = await _items(hass)
    assert set(items) == {"Vacuum kitchen floor", "Clean windows"}
    v = items["Vacuum kitchen floor"]
    assert v["status"] == "needs_action" and "due" not in v
    assert v["description"] == "every 7 days · never done"

    # done today -> checked, due in 7 days, description carries the date
    await hass.services.async_call("button", "press", {"entity_id": "button.vacuum_kitchen_floor_done"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("todo.house_cleaning").state == "1"
    v = (await _items(hass))["Vacuum kitchen floor"]
    assert v["status"] == "completed"
    assert v["due"] == (_today() + timedelta(days=7)).isoformat()
    assert v["description"] == f"every 7 days · last done {_today().isoformat()}"
    assert v["completed"] is not None

    # inside the soon window (2 days) -> back on the list, still with a due date
    await hass.services.async_call(DOMAIN, "undo", {"entity_id": "button.vacuum_kitchen_floor_done"}, blocking=True)
    await hass.services.async_call(DOMAIN, "mark_done", {"entity_id": "button.vacuum_kitchen_floor_done", "done_at": (_today() - timedelta(days=6)).isoformat()}, blocking=True)
    await hass.async_block_till_done()
    v = (await _items(hass))["Vacuum kitchen floor"]
    assert v["status"] == "needs_action" and v["due"] == (_today() + timedelta(days=1)).isoformat()
    assert hass.states.get("sensor.house_cleaning_due_count").state == "0"  # soon is listed, not due

    # the sensor and the list disagree on `never` by design: listed, not counted
    assert hass.states.get("todo.house_cleaning").state == "2"
    assert (await _items(hass, status="completed")) == {}


async def test_todo_check_uncheck_rename(hass: HomeAssistant):
    await _setup(hass)
    # checking records a completion now
    await hass.services.async_call("todo", "update_item", {"entity_id": "todo.house_cleaning", "item": "Clean windows", "status": "completed"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.clean_windows_last_done").attributes["done_count"] == 1
    assert hass.states.get("sensor.clean_windows_next_due").attributes["status"] == "ok"

    # the frontend's checkbox tap echoes due and description back unchanged;
    # that must land, not be refused as an edit
    cur = (await _items(hass))["Clean windows"]
    await hass.services.async_call("todo", "update_item", {"entity_id": "todo.house_cleaning", "item": cur["uid"], "rename": cur["summary"], "status": "needs_action", "due_date": cur["due"], "description": cur["description"]}, blocking=True)
    await hass.async_block_till_done()
    # ...and unchecking undid the completion
    assert hass.states.get("sensor.clean_windows_next_due").attributes["status"] == "never"
    assert hass.states.get("sensor.clean_windows_last_done").attributes["done_count"] == 0

    # a status that is already the item's is a no-op, not a second undo
    await hass.services.async_call("todo", "update_item", {"entity_id": "todo.house_cleaning", "item": "Clean windows", "status": "needs_action"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.clean_windows_next_due").attributes["status"] == "never"

    # a CHANGED due date is refused: it is derived, and no completion is invented
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("todo", "update_item", {"entity_id": "todo.house_cleaning", "item": "Vacuum kitchen floor", "due_date": _today().isoformat()}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("todo", "update_item", {"entity_id": "todo.house_cleaning", "item": "Vacuum kitchen floor", "description": "x"}, blocking=True)
    assert hass.states.get("sensor.vacuum_kitchen_floor_next_due").attributes["status"] == "never"

    # renaming renames the chore; the uid (subentry) and the entity ids are frozen
    uid = (await _items(hass))["Vacuum kitchen floor"]["uid"]
    await hass.services.async_call("todo", "update_item", {"entity_id": "todo.house_cleaning", "item": "Vacuum kitchen floor", "rename": " Vacuum the kitchen "}, blocking=True)
    await hass.async_block_till_done()
    items = await _items(hass)
    assert "Vacuum kitchen floor" not in items and items["Vacuum the kitchen"]["uid"] == uid
    assert hass.states.get("sensor.vacuum_kitchen_floor_next_due") is not None
    # a blank rename never reaches the platform: core's own schema refuses it
    import voluptuous as vol
    with pytest.raises(vol.Invalid):
        await hass.services.async_call("todo", "update_item", {"entity_id": "todo.house_cleaning", "item": "Vacuum the kitchen", "rename": "  "}, blocking=True)


async def test_todo_add_item_and_no_delete(hass: HomeAssistant):
    entry = await _setup(hass)
    await hass.services.async_call("todo", "add_item", {"entity_id": "todo.house_cleaning", "item": "Clean the oven"}, blocking=True)
    await hass.async_block_till_done()
    sub = next(s for s in entry.subentries.values() if s.title == "Clean the oven")
    assert sub.data == {"name": "Clean the oven", "interval_days": 7}
    assert hass.states.get("button.clean_the_oven_done") is not None
    assert (await _items(hass))["Clean the oven"]["status"] == "needs_action"

    # a due date on add is refused for the same reason as on update
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("todo", "add_item", {"entity_id": "todo.house_cleaning", "item": "Wash the car", "due_date": _today().isoformat()}, blocking=True)
    assert not any(s.title == "Wash the car" for s in entry.subentries.values())

    # no delete: removing an item, and clearing completed items, are both
    # refused by core because the feature is not declared -- a chore's
    # history goes with it, so that stays a Settings action
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("todo", "remove_item", {"entity_id": "todo.house_cleaning", "item": "Clean the oven"}, blocking=True)
    await hass.services.async_call("button", "press", {"entity_id": "button.clean_the_oven_done"}, blocking=True)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("todo", "remove_completed_items", {"entity_id": "todo.house_cleaning"}, blocking=True)
    assert len(entry.subentries) == 3
