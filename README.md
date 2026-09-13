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
  actions and their refusals, the config and subentry flows.

## Removal

Settings → Devices & Services → House Cleaning → Delete. Takes every chore
device, entity and the completion store with it.
