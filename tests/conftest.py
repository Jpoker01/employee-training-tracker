from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.constants import CLEAN_FILE_NAMES
from app.main import create_app

CLEAN_TABLES = {
    "employees": [
        {
            "id_zamestnance": "E1",
            "jmeno": "<b>Eva</b>",
            "prijmeni": "Nová",
            "email": "eva.nova@example.test",
            "utvar": "Knihovna",
            "pozice": "Referent",
            "datum_nastupu": "2020-01-01",
            "datum_ukonceni": "",
            "stav": "aktivní",
            "poznamka": '=HYPERLINK("http://example.test")',
        },
        {
            "id_zamestnance": "E2",
            "jmeno": "Petr",
            "prijmeni": "Malý",
            "email": "petr.maly@example.test",
            "utvar": "",
            "pozice": "Referent",
            "datum_nastupu": "2020-01-01",
            "datum_ukonceni": "",
            "stav": "aktivní",
            "poznamka": "",
        },
        {
            "id_zamestnance": "E3",
            "jmeno": "Jana",
            "prijmeni": "Stará",
            "email": "jana.stara@example.test",
            "utvar": "Knihovna",
            "pozice": "Referent",
            "datum_nastupu": "2020-01-01",
            "datum_ukonceni": "2026-01-31",
            "stav": "ukončen",
            "poznamka": "",
        },
    ],
    "catalog": [
        {
            "kod": "BOZP-Z",
            "nazev": "BOZP – základní školení",
            "platnost_mesicu": "24",
            "povinne_pro": "VSICHNI",
        },
    ],
    "completions": [
        {
            "id_zaznamu": "Z000001",
            "id_zamestnance": "E1",
            "kod_skoleni": "BOZP-Z",
            "datum_absolvovani": "2025-06-01",
            "platnost_do": "2027-06-01",
            "is_unknown_code": "False",
            "is_name_mismatch": "False",
            "is_future": "False",
        },
    ],
    "terms": [
        {
            "id_terminu": "T001",
            "kod_skoleni": "BOZP-Z",
            "datum": "2026-11-01",
            "cas": "09:00-12:00",
            "misto": "Aula A",
            "kapacita": "10",
            "obsazeno": "0",
            "stav": "plánováno",
            "is_unknown_code": "False",
        },
    ],
}


@pytest.fixture
def clean_dir(tmp_path: Path) -> Path:
    for name, rows in CLEAN_TABLES.items():
        pd.DataFrame(rows).to_csv(tmp_path / CLEAN_FILE_NAMES[name], index=False)
    return tmp_path


@pytest.fixture
def client(clean_dir: Path) -> Iterator[TestClient]:
    with TestClient(create_app(clean_dir)) as test_client:
        yield test_client
