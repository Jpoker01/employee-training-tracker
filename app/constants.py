"""Constants shared by the training tracker modules."""

import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# On Render the cleaned CSVs are secret files, so the directory comes from the environment.
CLEAN_DIR = Path(os.environ.get("CLEAN_DIR", PROJECT_ROOT / "data" / "clean"))
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"
STATIC_DIR = PROJECT_ROOT / "app" / "static"

TABLE_NAMES = ["completions", "employees", "catalog", "terms"]
DATE_COLUMNS = ["datum_absolvovani", "platnost_do", "datum_nastupu", "datum_ukonceni", "datum"]
INT_COLUMNS = ["platnost_mesicu", "kapacita", "obsazeno"]

EXPORT_DATE = pd.Timestamp("2026-10-01")
EXPIRING_DAYS = 90
ENDED_STATE = "ukončen"
PARENTAL_LEAVE_STATE = "rodičovská"
CANCELLED_TERM_STATE = "zrušeno"

NEEDS_TRAINING_STATUSES = ["missing", "expired", "expiring"]
NO_FREE_SEAT = "žádné volné místo"
NO_TERM_BEFORE_END = "žádný termín před odchodem"
NO_TERM_AFTER_START = "žádný termín po nástupu"

PAIR_KEY = ["id_zamestnance", "kod_skoleni"]
RECORD_COLUMNS = ["id_zaznamu", *PAIR_KEY, "datum_absolvovani", "platnost_do"]
EMPLOYEE_COLUMNS = ["id_zamestnance", "stav", "utvar", "datum_nastupu", "datum_ukonceni"]

STATUS_ORDER = ["missing", "expired", "expiring", "valid"]
# For HR, never done and expired mean the same: not valid now, book it.
STATE_BY_STATUS = {
    "missing": "not_valid",
    "expired": "not_valid",
    "expiring": "expiring",
    "valid": "valid",
}
STATE_LABELS = {"not_valid": "neplatné", "expiring": "brzy vyprší", "valid": "platné"}
UNKNOWN_DEPARTMENT = "neznámé oddělení"
