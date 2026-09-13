"""The house as a to-do list: one `todo` entity, one item per chore.

WHY A TODO ENTITY WHEN THE SENSORS ALREADY SAY IT. `sensor.house_cleaning_due_count`
carries the whole table in its attributes, but only this integration's own
consumers read that shape. The `todo` platform is the shape the rest of Home
Assistant already speaks: the To-do panel, the Lovelace to-do card, the
`todo.*` actions an automation calls, and every voice assistant that knows
"what is on my list". Publishing the chores as a list gets all of that
without a card of our own -- and the list is a VIEW over the same store,
not a second one: nothing here is persisted that the coordinator does not
already keep.

WHAT AN ITEM IS. `uid` is the chore's SUBENTRY id, so a rename cannot
orphan it. `summary` is the name. `due` is the next due DATE (no time --
a chore is due on a day, and `TodoItem.due` takes a bare `date`). `status`
is NEEDS_ACTION for anything the list wants done -- never done, overdue,
due today, and due SOON, because surfacing a chore before its day is
exactly what the soon window is for -- and COMPLETED only for a chore
that is up to date. A never-done chore is unchecked deliberately: it has no
anchor to be late against, so the sensors leave it out of the due count,
but the only way it gets an anchor is somebody checking it off, so a list
that showed it checked would be a list nobody can act on.

WHAT A WRITE DOES. Checking an item records a completion now; unchecking
one undoes the most recent -- the same two writes the Done button and the
`undo` action make. Renaming an item renames the chore. Adding an item adds
a chore at the default cadence with no room, so "add clean the oven to house
cleaning" from a voice assistant works and the cadence and room are set
afterwards in Settings or with `set_interval`.

WHAT IT REFUSES, AND WHY. A DUE DATE IS DERIVED -- last completion plus
cadence -- so a due-date edit is refused with a message that says where the
date comes from. Honouring it would mean inventing a completion the
household never asserted, and the completion history is the one thing this
integration exists to keep honest. The description is generated for the
same reason. NO DELETE. `TodoListEntityFeature.DELETE_TODO_ITEM` would also
light up core's `todo.remove_completed_items`, which on this list means
"delete every chore that is currently up to date" -- and deleting a chore
takes its history with it. A chore is removed in Settings, one at a time.

THE FEATURE FLAGS ARE NOT OPTIONAL WHERE THEY LOOK OPTIONAL. The frontend's
checkbox tap (`updateItem` in its `data/todo.ts`) echoes the item's `due`
and `description` back through `todo.update_item`, and core's
`_validate_supported_features` refuses any field whose flag the entity does
not declare. A list that publishes a due date without declaring
SET_DUE_DATE_ON_ITEM therefore cannot be checked from its own card. The two
flags are declared so the tap lands; the values are compared, and only a
CHANGE is refused.
"""

from __future__ import annotations

from datetime import date

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .chores import ChoreState
from .const import (
    CONF_INTERVAL,
    CONF_NAME,
    DEFAULT_INTERVAL,
    DOMAIN,
    LISTED_STATUSES,
    SUBENTRY_CHORE,
)
from .coordinator import HouseCleaningConfigEntry
from .entity import HouseEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: HouseCleaningConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ChoreList(entry.runtime_data)])


def _refuse(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders
    )


class ChoreList(HouseEntity, TodoListEntity):
    """`todo.house_cleaning`: the roll-up device's list."""

    # No name of its own: the entity takes the device's, so the id is
    # todo.house_cleaning rather than todo.house_cleaning_house_cleaning.
    _attr_name = None
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "list")

    # -- the view -----------------------------------------------------------

    @property
    def todo_items(self) -> list[TodoItem]:
        areas = ar.async_get(self.hass)
        return [self._item(row, areas) for row in self.coordinator.rows()]

    def _item(self, row: dict, areas: ar.AreaRegistry) -> TodoItem:
        state: ChoreState = row["state"]
        listed = state.status in LISTED_STATUSES
        return TodoItem(
            uid=row["subentry_id"],
            summary=row["name"],
            status=TodoItemStatus.NEEDS_ACTION if listed else TodoItemStatus.COMPLETED,
            due=state.due,
            description=self._description(row, areas),
            completed=None if listed else row["done_at"],
        )

    @staticmethod
    def _description(row: dict, areas: ar.AreaRegistry) -> str:
        parts: list[str] = []
        if row["area"] and (area := areas.async_get_area(row["area"])):
            parts.append(area.name)
        days = row["interval_days"]
        parts.append("every day" if days == 1 else f"every {days} days")
        done: date | None = row["state"].last_done
        parts.append(f"last done {done.isoformat()}" if done else "never done")
        return " · ".join(parts)

    def _current(self, uid: str | None) -> tuple[dict, TodoItem]:
        row = self.coordinator.data["chores"].get(uid) if uid else None
        if row is None:
            raise _refuse("item_not_found", item=str(uid))
        return row, self._item(row, ar.async_get(self.hass))

    # -- the writes ---------------------------------------------------------

    async def async_create_todo_item(self, item: TodoItem) -> None:
        name = (item.summary or "").strip()
        if not name:
            raise _refuse("unknown_value", field=CONF_NAME, value=repr(item.summary))
        if item.due is not None:
            raise _refuse("due_is_derived", name=name)
        if item.description:
            raise _refuse("description_is_derived", name=name)
        entry = self.coordinator.entry
        # The update listener reloads the entry; the chore's device and
        # entities exist on the far side of that reload, like one added in
        # Settings.
        self.hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data={CONF_NAME: name, CONF_INTERVAL: DEFAULT_INTERVAL},
                subentry_type=SUBENTRY_CHORE,
                title=name,
                unique_id=None,
            ),
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        row, current = self._current(item.uid)
        name = current.summary
        if item.due is not None and item.due != current.due:
            raise _refuse("due_is_derived", name=name)
        if item.description is not None and item.description != current.description:
            raise _refuse("description_is_derived", name=name)

        # Status first: the store write below survives the reload a rename
        # triggers, and the reload re-reads it.
        if item.status is not None and item.status != current.status:
            if item.status == TodoItemStatus.COMPLETED:
                await self.coordinator.async_mark_done(row["subentry_id"])
            elif not await self.coordinator.async_undo(row["subentry_id"]):
                raise _refuse("nothing_to_undo", name=name)

        new_name = (item.summary or "").strip()
        if item.summary is not None and not new_name:
            raise _refuse("unknown_value", field=CONF_NAME, value=repr(item.summary))
        if new_name and new_name != name:
            entry = self.coordinator.entry
            subentry = entry.subentries[row["subentry_id"]]
            self.hass.config_entries.async_update_subentry(
                entry, subentry, title=new_name, data={**subentry.data, CONF_NAME: new_name}
            )
