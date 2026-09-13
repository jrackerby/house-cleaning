<p align="center">
  <picture>
    <!-- The wordmark is deep blue and vanishes on a dark ground, so which file
         is the FALLBACK matters: HACS renders this README inside Home
         Assistant's frontend, which is dark by default, and a renderer that
         drops <source> lands on the <img>. The dark-safe variant is the img;
         the light one is the opt-in source. The mark itself is identical in
         both -- only the wordmark is lifted. -->
    <source media="(prefers-color-scheme: light)" srcset="brand/logo.png">
    <img src="brand/dark_logo.png" alt="House Cleaning" width="420">
  </picture>
</p>

# House Cleaning

Tracks household cleaning chores **by room**, each with its own cadence and a
record of when it was last done.

A chore is one job — *Vacuum kitchen floor*, *Scrub tub*, *Change bed
sheets* — with a room, a number of days between doings, and a history of
completions. The integration holds one table (which chores are overdue, due
today, due soon, never recorded) and publishes it as entities, so a wall
panel can render it and an automation can read it. Marking a chore done is
one tap.

**Devices supported: none.** Everything here is something a person asserts.

## Why a component rather than helpers and templates

Each chore would need an `input_datetime` (last done) and an `input_number`
(cadence), and a template sensor to compare them — per chore, per room,
declared in YAML, with the room encoded in the helper's name because a helper
cannot carry an area. Adding a chore was a deploy. Here a chore is a **config
subentry**: it is added in a form, gets its own device, and its device sits in
a Home Assistant **area**, which is what "by room" means. Nothing parses a
room out of an entity id.

A fresh `input_datetime` also comes up seeded to *today*, so an untouched
house asserts every chore was just done. Here a chore nobody has recorded is
`never` — a named state, not a stale date, and not overdue either: there is no
anchor to be late against.

## Setup

Install through HACS (custom repository `jrackerby/house-cleaning`, category
Integration), restart, then Settings → Devices & Services → Add integration →
**House Cleaning**. The
one question is whether to seed a starter set: nine whole-house chores
(vacuum, mop, dust, bathrooms, sheets, counters, fridge, towels, windows)
with sensible cadences, editable or deletable like any other.

Then **Add chore** on the integration's page: a name, a room (the house's
own area list; leave it empty for a whole-house job) and how often, in
days. The chore's device is placed in that room automatically. To move a
chore, edit the chore — the room set here wins over a drag in the device
page on the next reload.

**Configure** on the entry sets the due-soon window (default 2 days).

## Entities

### Per chore (device in its room)

With `has_entity_name`, ids slug from the chore's name at creation:
*Vacuum kitchen floor* → `sensor.vacuum_kitchen_floor_next_due`. Renaming
the chore renames the device; the ids are frozen.

| Entity | What it says |
| --- | --- |
| `sensor.<chore>_next_due` | Timestamp of the next due date (midday local). `unknown` when never done. Attributes: `status` (`never` / `overdue` / `due` / `soon` / `ok`), `date`, `days_until` (negative once overdue), `days_since`, `interval_days`, `area`. |
| `sensor.<chore>_last_done` | Timestamp of the latest completion. Attributes: `history` (newest first, last 20), `done_count`, `interval_days`, `area`. |
| `binary_sensor.<chore>_due` | On when due today or overdue. Attribute `status` carries the rest. |
| `button.<chore>_done` | Stamps now. |

### The house (one roll-up device, *House Cleaning*)

| Entity | What it says |
| --- | --- |
| `sensor.house_cleaning_due_count` | How many chores are due today or overdue. Never-done chores are **not** counted; they are listed in `never_items`. Attributes: `overdue_items`, `due_items`, `soon_items`, `never_items`, `by_room` (`{area_id: {total, due, never}}`), `rows` (the whole table). |
| `sensor.house_cleaning_next_chore` | The chore due soonest (overdue counts as soonest). Attributes: `status`, `due`, `days_until`, `area`. |
| `binary_sensor.house_cleaning_overdue` | Anything past its cadence. |
| `todo.house_cleaning` | The chores as a Home Assistant **to-do list** — one item per chore, state is how many are unchecked. See below. |

## The to-do list

`todo.house_cleaning` publishes the same table through Home Assistant's
native `todo` platform, so the To-do panel, the `todo-list` card, the
`todo.*` actions and a voice assistant that knows "what's on my list" all
work without anything of this integration's own. It is a **view** over the
completion store, not a second list: nothing is stored that the sensors do
not already read.

| Item field | Comes from |
| --- | --- |
| `summary` | The chore's name. |
| `uid` | The chore's subentry id — frozen; a rename keeps it. |
| `status` | **Unchecked** (`needs_action`) when never done, overdue, due today or due soon. **Checked** (`completed`) only when up to date. |
| `due` | The next due date. Absent when never done. |
| `description` | `Kitchen · every 7 days · last done 2026-09-10` — room, cadence, last completion. |
| `completed` | The last completion, on a checked item. |

Two things differ from the sensors on purpose. A **never-done chore is
unchecked**: the sensors leave it out of the due count because it has no
anchor to be late against, but the only way it gets one is somebody
checking it off, so a checked item would be one nobody can act on. And a
chore **due soon is unchecked**: surfacing it before its day is what the
soon window is for, so the list's state can read `3` while
`sensor.house_cleaning_due_count` reads `1`. Set the window to `0` in
Configure for a list that matches the count.

| Doing this on the list | Does this |
| --- | --- |
| Check an item | Records a completion now — the Done button. |
| Uncheck an item | Removes the most recent completion — `house_cleaning.undo`. |
| Rename an item | Renames the chore. Entity ids stay as they were. |
| Add an item (`todo.add_item`, or the panel's field) | Adds a chore at the default cadence (7 days) with no room. Set the cadence with `house_cleaning.set_interval` and the room by editing the chore. |
| Change the due date | **Refused.** The due date is the last completion plus the cadence; honouring an edit would mean inventing a completion nobody asserted. Change the cadence, or backfill with `house_cleaning.mark_done`. |
| Edit the description | **Refused.** It is generated. |
| Remove an item, or *clear completed* | **Not offered.** Deleting a chore takes its history with it, and *clear completed* on this list would mean "delete every chore that is up to date". A chore is removed in Settings, one at a time. |

Each refusal is raised to the caller, like the actions below.

## Actions

Each takes `entity_id`: **any** entity of the chore (its Done button, say).
Every refusal is raised to the caller — a service call answers 200 on a
silent no-op, so a wall panel could not otherwise tell a stored change from
an ignored one.

| Action | What it does | What it refuses |
| --- | --- | --- |
| `house_cleaning.mark_done` | Records a completion. `done_at` (a date) backfills; empty means now. The latest completion stays the latest, so backfilling last week never moves a chore done yesterday. | A date in the future; anything unparseable. |
| `house_cleaning.undo` | Removes the most recent completion — a mis-tap. | A chore with nothing recorded. |
| `house_cleaning.set_interval` | Changes the cadence; the entry reloads. | Anything not a whole number of days from 1 to 365 — refused, never rounded. |

The standard `todo` actions work on `todo.house_cleaning` as the table
above describes: `todo.get_items` (with `status` to filter), `todo.add_item`,
`todo.update_item` (an item is addressed by its name or its uid; `status`,
`rename`). `todo.remove_item` and `todo.remove_completed_items` are refused.

## Dashboard examples

Everything below is a core Lovelace card — nothing custom to install. Paste
into a view's YAML (edit dashboard → ⋮ → *Raw configuration editor*, or a
card's *Show code editor*). Entity ids follow the chore's name at creation
(`sensor.vacuum_kitchen_floor_next_due`); substitute your own.

### The list, as a card

The `todo-list` card is the whole integration on one card: unchecked items
are what needs doing, most urgent first; a tap records a completion, a
second tap undoes it.

```yaml
type: todo-list
entity: todo.house_cleaning
title: Chores
```

Hide the checked ones so it reads as a to-do list rather than a ledger:

```yaml
type: todo-list
entity: todo.house_cleaning
title: Chores
hide_completed: true
```

### One chore

A tile with the due date, and the Done button as its action:

```yaml
type: tile
entity: sensor.vacuum_kitchen_floor_next_due
name: Vacuum kitchen floor
icon: mdi:robot-vacuum
state_content:
  - state
  - days_until
tap_action:
  action: perform-action
  perform_action: house_cleaning.mark_done
  target:
    entity_id: sensor.vacuum_kitchen_floor_next_due
hold_action:
  action: more-info
```

Or as a row in an `entities` card, where the button is its own row:

```yaml
type: entities
title: Kitchen
entities:
  - entity: sensor.vacuum_kitchen_floor_next_due
    name: Vacuum
    secondary_info: last-changed
  - entity: sensor.wipe_kitchen_counters_next_due
    name: Counters
  - entity: button.vacuum_kitchen_floor_done
    name: Vacuumed just now
```

### The house, at a glance

The roll-up in a glance row, colour-coded by the binary sensor:

```yaml
type: glance
title: House Cleaning
entities:
  - entity: sensor.house_cleaning_due_count
    name: Due
  - entity: sensor.house_cleaning_next_chore
    name: Next up
  - entity: binary_sensor.house_cleaning_overdue
    name: Overdue
```

### Overdue, by name

The due-count sensor carries the lists as attributes, so a `markdown` card
can name what is late without one card per chore:

```yaml
type: markdown
title: Behind on
content: |
  {% set s = states.sensor.house_cleaning_due_count %}
  {% if s.attributes.overdue_items %}
  - **Overdue:** {{ s.attributes.overdue_items | join(', ') }}
  {% endif %}
  {% if s.attributes.due_items | reject('in', s.attributes.overdue_items) | list %}
  - **Today:** {{ s.attributes.due_items | reject('in', s.attributes.overdue_items) | join(', ') }}
  {% endif %}
  {% if s.attributes.soon_items %}
  - *Soon:* {{ s.attributes.soon_items | join(', ') }}
  {% endif %}
  {% if s.state == '0' and not s.attributes.soon_items %}
  All caught up.
  {% endif %}
```

Shown only when something is due, with a `conditional` card around it:

```yaml
type: conditional
conditions:
  - condition: numeric_state
    entity: sensor.house_cleaning_due_count
    above: 0
card:
  type: markdown
  content: |
    **{{ states('sensor.house_cleaning_due_count') }} due:**
    {{ state_attr('sensor.house_cleaning_due_count', 'due_items') | join(', ') }}
```

### The whole table

`rows` on the due-count sensor is every chore, most urgent first, with its
`status`, `due`, `days_until`, `last_done` and `area` — one card for the
house:

```yaml
type: markdown
title: All chores
content: |
  | Chore | Room | Status | Due |
  |---|---|---|---|
  {% for r in state_attr('sensor.house_cleaning_due_count', 'rows') -%}
  | {{ r.name }} | {{ area_name(r.area) if r.area else '—' }} | {{ r.status }} | {{ r.due or '—' }} |
  {% endfor %}
```

### A room, in a sections view

A section per room with the `todo-list` card at the top and the room's
chores under it. `by_room` on the due-count sensor carries the counts per
area id if a heading should say how many are due.

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: heading
        heading: Kitchen
        badges:
          - type: entity
            entity: sensor.house_cleaning_due_count
            state_content: state
      - type: tile
        entity: sensor.vacuum_kitchen_floor_next_due
        name: Vacuum
        tap_action:
          action: perform-action
          perform_action: house_cleaning.mark_done
          target:
            entity_id: sensor.vacuum_kitchen_floor_next_due
      - type: tile
        entity: sensor.wipe_kitchen_counters_next_due
        name: Counters
        tap_action:
          action: perform-action
          perform_action: house_cleaning.mark_done
          target:
            entity_id: sensor.wipe_kitchen_counters_next_due
  - type: grid
    cards:
      - type: heading
        heading: Everything
      - type: todo-list
        entity: todo.house_cleaning
        hide_completed: true
```

### Backfilling from a card

Cards do not render templates in `data`, so "I did this yesterday" is a
script the card calls:

```yaml
# scripts.yaml, or Settings → Automations & scenes → Scripts
sheets_done_yesterday:
  alias: Sheets changed yesterday
  sequence:
    - action: house_cleaning.mark_done
      data:
        entity_id: button.change_bed_sheets_done
        done_at: "{{ (now() - timedelta(days=1)).date() }}"
```

```yaml
type: button
name: Sheets changed yesterday
icon: mdi:bed
tap_action:
  action: perform-action
  perform_action: script.sheets_done_yesterday
```

## Storage

Completions live in `.storage/house_cleaning.<entry_id>`, keyed on the
chore's subentry id — never its name. Everything else (`status`,
`days_until`, the due date) is recomputed from that plus the clock, every
five minutes and on every write, and is never persisted. Removing a chore
drops its completions on the next reload. Removing the integration deletes
the store: export first if the history matters.

## Known limitations

- A chore's cadence is an interval from its last completion, not a fixed
  weekday. "Every Saturday" is `7` days from whichever day it was last done.
- Nothing here measures anything. "Done" is an assertion by a person.

## Tests

- `tools/run_tests.sh` — the rule (`chores.py`), with Home Assistant absent.
- `tools/run_e2e.sh` — the real layout against real core (Python 3.14 + the
  version `hacs.json` names + `pytest-homeassistant-custom-component`):
  entries, subentries, devices in areas, entities, the button, all three
  actions and their refusals, the to-do list and its writes, the config and
  subentry flows.

## Removal

Settings → Devices & Services → House Cleaning → Delete. Takes every chore
device, entity and the completion store with it.
