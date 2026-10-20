from types import SimpleNamespace

import pandas as pd
import pytest

from app.pages import (
    build_capacity_df,
    build_no_booking_reason,
    build_people,
    build_person_notes,
    build_problem,
    build_row_notes,
    filter_rows,
    find_seats_for_all_date,
    find_term,
    pick_plural,
)


def make_row(**overrides) -> pd.Series:
    """One register row of a missing KYBER training, with fields overridden."""
    row = {
        "kod_skoleni": "KYBER",
        "status": "missing",
        "state": "not_valid",
        "valid_until": pd.NaT,
        "id_terminu": "",
        "term_date": pd.NaT,
        "term_time": "",
        "is_after_expiry": False,
        "unassigned_reason": "",
        "stav": "aktivní",
        "datum_nastupu": pd.Timestamp("2020-01-01"),
        "datum_ukonceni": pd.NaT,
        "utvar": "Knihovna",
        "advance_record_date": pd.NaT,
    }
    return pd.Series(row | overrides)


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"state": "not_valid"}, "KYBER: neplatné"),
        (
            {"state": "expiring", "valid_until": pd.Timestamp("2026-11-30")},
            "KYBER: platí do 30. 11. 2026",
        ),
    ],
)
def test_build_problem(overrides: dict, problem: str):
    """A training is either not valid or expires on a date."""
    row = make_row(**overrides)
    assert build_problem(row) == problem


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({}, ""),
        ({"id_terminu": "T020"}, ""),
        ({"unassigned_reason": "žádné volné místo"}, "bez místa: žádné volné místo"),
        ({"stav": "rodičovská"}, "nepřihlašovat: rodičovská dovolená"),
    ],
)
def test_build_no_booking_reason(overrides: dict, reason: str):
    """The reason says why there is no term to book, empty when none is needed."""
    row = make_row(**overrides)
    assert build_no_booking_reason(row) == reason


@pytest.mark.parametrize(
    ("overrides", "notes"),
    [
        ({}, []),
        (
            {"advance_record_date": pd.Timestamp("2026-11-05")},
            ["záznam na 5. 11. 2026 zadán předem, nezapočítán"],
        ),
    ],
)
def test_build_row_notes(overrides: dict, notes: list[str]):
    """Data warnings are listed per training."""
    row = make_row(**overrides)
    assert build_row_notes(row) == notes


@pytest.mark.parametrize(
    ("overrides", "notes"),
    [
        ({}, []),
        ({"stav": "rodičovská"}, ["rodičovská dovolená"]),
        ({"datum_nastupu": pd.Timestamp("2026-11-02")}, ["nastupuje 2. 11. 2026"]),
        ({"datum_ukonceni": pd.Timestamp("2027-01-31")}, ["odchází 31. 1. 2027"]),
        ({"utvar": ""}, ["neznámé oddělení: školení podle oddělení nejsou zkontrolována"]),
    ],
)
def test_build_person_notes(overrides: dict, notes: list[str]):
    """Facts about the employee are listed once per person."""
    row = make_row(**overrides)
    assert build_person_notes(row) == notes


@pytest.fixture
def rows_df() -> pd.DataFrame:
    """Register rows of several employees in different states and departments."""
    rows = [
        make_row(id_zamestnance="E2", status="missing", department="Knihovna", is_to_do=True),
        make_row(id_zamestnance="E1", status="expired", department="Knihovna", is_to_do=True),
        make_row(id_zamestnance="E2", status="expiring", department="Knihovna", is_to_do=True),
        make_row(id_zamestnance="E3", status="valid", department="Rektorát", is_to_do=False),
    ]
    rows_df = pd.DataFrame(rows)
    rows_df["name"] = rows_df["id_zamestnance"]
    return rows_df


def test_filter_rows_combines_filters(rows_df: pd.DataFrame):
    """Training and department filters apply together."""
    rows_df.loc[2, "kod_skoleni"] = "GDPR"
    filtered_df = filter_rows(
        rows_df,
        training="KYBER",
        department="Knihovna",
        state="",
        query="",
    )
    assert filtered_df["status"].tolist() == ["missing", "expired"]


def test_filter_rows_by_state(rows_df: pd.DataFrame):
    """The state filter keeps one state."""
    rows_df["state"] = ["not_valid", "not_valid", "expiring", "valid"]
    filtered_df = filter_rows(rows_df, training="", department="", state="expiring", query="")
    assert filtered_df["id_zamestnance"].tolist() == ["E2"]


def test_filter_rows_by_name_ignores_case(rows_df: pd.DataFrame):
    """The search matches part of the name in any case."""
    rows_df["name"] = ["Nová Eva", "Malý Petr", "Nová Eva", "Stará Jana"]
    filtered_df = filter_rows(rows_df, training="", department="", state="", query="nová")
    assert filtered_df["id_zamestnance"].tolist() == ["E2", "E2"]


def test_build_people_groups_to_dos_most_urgent_first(rows_df: pd.DataFrame):
    """People are listed in order of their most urgent to-do, without the ones with none."""
    people = build_people(rows_df)
    assert [person["id_zamestnance"] for person in people] == ["E2", "E1"]
    assert people[0]["to_dos"]["status"].tolist() == ["missing", "expiring"]


@pytest.mark.parametrize(
    ("count", "word"),
    [(0, "zaměstnanců"), (1, "zaměstnanec"), (4, "zaměstnanci"), (56, "zaměstnanců")],
)
def test_pick_plural(count: int, word: str):
    """The word form follows the Czech plural rules."""
    assert pick_plural(count, "zaměstnanec", "zaměstnanci", "zaměstnanců") == word


@pytest.fixture
def kyber_terms_df() -> pd.DataFrame:
    """Two upcoming KYBER terms with free seats."""
    return pd.DataFrame(
        {
            "id_terminu": ["T1", "T2"],
            "kod_skoleni": ["KYBER", "KYBER"],
            "datum": pd.to_datetime(["2026-10-14", "2026-10-28"]),
            "free_seats": [3, 40],
        }
    )


@pytest.fixture
def titles_by_code() -> pd.Series:
    """Catalog names of the trainings used in the capacity tests."""
    return pd.Series(
        {
            "KYBER": "Kybernetická bezpečnost",
            "GDPR": "Ochrana osobních údajů",
            "BOZP-Z": "BOZP – základní školení",
        }
    )


@pytest.mark.parametrize(
    ("needed", "date"),
    [(3, pd.Timestamp("2026-10-14")), (4, pd.Timestamp("2026-10-28"))],
)
def test_find_seats_for_all_date_adds_seats_from_the_earliest_term(
    kyber_terms_df: pd.DataFrame, needed: int, date: pd.Timestamp
):
    """The date is the first term by which the free seats add up to everyone needed."""
    assert find_seats_for_all_date(kyber_terms_df, needed) == date


def test_find_seats_for_all_date_empty_when_terms_are_not_enough(kyber_terms_df: pd.DataFrame):
    """When all terms together have fewer seats than needed, there is no date."""
    assert pd.isna(find_seats_for_all_date(kyber_terms_df, 44))


def test_build_capacity_df_counts_people_and_seat_dates(
    kyber_terms_df: pd.DataFrame, titles_by_code: pd.Series
):
    """Per training: people to book, the first term and the date everyone has a seat."""
    shortfall_df = pd.DataFrame({"kod_skoleni": ["KYBER"], "candidates": [4], "without_seat": [0]})
    capacity_df = build_capacity_df(kyber_terms_df, shortfall_df, titles_by_code)
    assert capacity_df.to_dict("records") == [
        {
            "kod_skoleni": "KYBER",
            "candidates": 4,
            "nazev": "Kybernetická bezpečnost",
            "first_term_date": pd.Timestamp("2026-10-14"),
            "first_term_seats": 3,
            "seats_for_all_date": pd.Timestamp("2026-10-28"),
            "fits_first_term": False,
        }
    ]


def test_build_capacity_df_training_without_terms_does_not_fit(
    kyber_terms_df: pd.DataFrame, titles_by_code: pd.Series
):
    """A training with people to book but no usable term does not fit and keeps its name."""
    shortfall_df = pd.DataFrame({"kod_skoleni": ["GDPR"], "candidates": [2], "without_seat": [2]})
    capacity_df = build_capacity_df(kyber_terms_df, shortfall_df, titles_by_code)
    gdpr_row = capacity_df.iloc[0]
    assert gdpr_row["nazev"] == "Ochrana osobních údajů"
    assert not gdpr_row["fits_first_term"]


def test_build_capacity_df_latest_seat_date_first(titles_by_code: pd.Series):
    """The training whose seats for everyone come latest is listed first."""
    terms_df = pd.DataFrame(
        {
            "id_terminu": ["T1", "T2"],
            "kod_skoleni": ["GDPR", "BOZP-Z"],
            "datum": pd.to_datetime(["2026-11-05", "2027-02-03"]),
            "free_seats": [88, 30],
        }
    )
    shortfall_df = pd.DataFrame(
        {"kod_skoleni": ["BOZP-Z", "GDPR"], "candidates": [1, 1], "without_seat": [0, 0]}
    )
    capacity_df = build_capacity_df(terms_df, shortfall_df, titles_by_code)
    assert capacity_df["kod_skoleni"].tolist() == ["BOZP-Z", "GDPR"]


def test_find_term_lists_most_urgent_first():
    """The bookings keep the register order (most urgent first), not the name order."""
    terms_df = pd.DataFrame({"id_terminu": ["T1"], "free_seats": [2]})
    rows_df = pd.DataFrame(
        {
            "id_terminu": ["T1", "T1"],
            "name": ["Zelená Ana", "Adam Petr"],
            "status": ["missing", "expiring"],
        }
    )
    register = SimpleNamespace(terms_df=terms_df, rows_df=rows_df)
    term = find_term(register, "T1")
    assert term["bookings"]["name"].tolist() == ["Zelená Ana", "Adam Petr"]
