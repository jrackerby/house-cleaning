"""Names and constants for the house_cleaning integration.

Everything the resolver and the platforms agree on lives here, so a status
word or a config key is spelled in exactly one place. This module imports
nothing from Home Assistant -- the test suite runs with core absent
(tests/conftest.py) and enforces that.
"""

DOMAIN = "house_cleaning"

# What a chore is, right now, against its own cadence. NEVER is its own word
# rather than a flavour of overdue: a chore nobody has recorded has no anchor
# to be late against, so folding it into the due count would make a fresh
# install read as a house that is behind on everything, and hiding it would
# make it read as a house that is caught up. It is neither.
STATUS_NEVER = "never"
STATUS_OVERDUE = "overdue"
STATUS_DUE = "due"  # due today
STATUS_SOON = "soon"  # inside the soon window, not yet today
STATUS_OK = "ok"
STATUSES = (STATUS_NEVER, STATUS_OVERDUE, STATUS_DUE, STATUS_SOON, STATUS_OK)

# The two statuses that put a chore on today's list.
DUE_STATUSES = (STATUS_OVERDUE, STATUS_DUE)

# The statuses that leave a chore UNCHECKED on the to-do list -- wider than
# DUE_STATUSES on purpose. Never-done is on it because checking it off is
# the only way it gets an anchor; soon is on it because surfacing a chore
# ahead of its day is what the soon window is for. Only `ok` is checked.
LISTED_STATUSES = (STATUS_NEVER, STATUS_OVERDUE, STATUS_DUE, STATUS_SOON)

CONF_NAME = "name"
CONF_AREA = "area"
CONF_INTERVAL = "interval_days"
CONF_SOON_DAYS = "soon_days"
CONF_STARTER_SET = "starter_set"

DEFAULT_INTERVAL = 7
DEFAULT_SOON_DAYS = 2
MIN_INTERVAL = 1
MAX_INTERVAL = 365
MIN_SOON_DAYS = 0
MAX_SOON_DAYS = 14

SUBENTRY_CHORE = "chore"

# How many completions each chore keeps. Enough for a wall panel's history
# view to answer "when did this last actually get done", not a ledger.
HISTORY_LIMIT = 20

# The starter set the config flow can seed on first install: whole-house
# chores with no room, so a fresh entry has something on the glass before
# anyone has added a chore of their own. Each is (name, interval in days).
# A household edits or deletes them like any other subentry.
STARTER_CHORES: tuple[tuple[str, int], ...] = (
    ("Vacuum floors", 7),
    ("Mop floors", 14),
    ("Dust surfaces", 14),
    ("Clean bathrooms", 7),
    ("Change bed sheets", 14),
    ("Wipe kitchen counters", 1),
    ("Clean the fridge", 30),
    ("Wash towels", 7),
    ("Clean windows", 90),
)
