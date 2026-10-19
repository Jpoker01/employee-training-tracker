import pandas as pd
import pytest

from app.constants import NO_FREE_SEAT, NO_TERM_AFTER_START, NO_TERM_BEFORE_END
from app.scheduling import (
    build_candidates_df,
    build_schedule_df,
    build_shortfall_df,
    find_usable_terms,
)


def make_status_df(*rows: dict) -> pd.DataFrame:
    default = {
        "id_zamestnance": "E1",
        "kod_skoleni": "KYBER",
        "status": "missing",
        "valid_until": pd.NaT,
        "is_one_off": False,
        "stav": "aktivní",
        "datum_nastupu": pd.Timestamp("2020-01-01"),
        "datum_ukonceni": pd.NaT,
    }
    status_rows = [default | row for row in rows]
    status_df = pd.DataFrame(status_rows, columns=list(default))
    for column in ["valid_until", "datum_nastupu", "datum_ukonceni"]:
        status_df[column] = pd.to_datetime(status_df[column])
    return status_df


def make_terms_df(*rows: dict) -> pd.DataFrame:
    default = {
        "id_terminu": "T1",
        "kod_skoleni": "KYBER",
        "datum": pd.Timestamp("2026-11-01"),
        "kapacita": 10,
        "obsazeno": 0,
        "stav": "plánováno",
        "is_unknown_code": False,
    }
    term_rows = [default | row for row in rows]
    terms_df = pd.DataFrame(term_rows, columns=list(default))
    terms_df["datum"] = pd.to_datetime(terms_df["datum"])
    return terms_df


def assigned_term(schedule_df: pd.DataFrame, employee_id: str) -> str:
    schedule_by_employee_df = schedule_df.set_index("id_zamestnance")
    return schedule_by_employee_df.loc[employee_id, "id_terminu"]


@pytest.mark.parametrize(
    "override",
    [
        {"datum": pd.Timestamp("2026-09-30")},
        {"datum": pd.NaT},
        {"stav": "zrušeno"},
        {"is_unknown_code": True},
        {"obsazeno": 10},
        {"obsazeno": 11},
    ],
)
def test_find_usable_terms_excludes_unusable(override):
    """Past, undated, cancelled, unknown-code, full and overbooked terms are not usable."""
    assert find_usable_terms(make_terms_df(override)).empty


def test_find_usable_terms_counts_free_seats():
    """Free seats are capacity minus seats already booked."""
    usable_df = find_usable_terms(make_terms_df({"kapacita": 10, "obsazeno": 4}))
    assert usable_df["free_seats"].iloc[0] == 6


@pytest.mark.parametrize("status", ["missing", "expired", "expiring"])
def test_candidates_include_trainings_in_need(status):
    """Missing, expired and expiring trainings are candidates."""
    status_df = make_status_df({"status": status})
    candidates_df = build_candidates_df(status_df, find_usable_terms(make_terms_df({})))
    assert len(candidates_df) == 1


def test_candidates_exclude_parental_leave():
    """People on parental leave are not scheduled."""
    status_df = make_status_df({"stav": "rodičovská"})
    candidates_df = build_candidates_df(status_df, find_usable_terms(make_terms_df({})))
    assert candidates_df.empty


def test_candidates_include_last_chance():
    """A valid training expiring before its last usable term is a candidate."""
    status_df = make_status_df({"status": "valid", "valid_until": pd.Timestamp("2026-12-01")})
    terms_df = make_terms_df({"datum": pd.Timestamp("2026-12-15")})
    candidates_df = build_candidates_df(status_df, find_usable_terms(terms_df))
    assert len(candidates_df) == 1


def test_candidates_exclude_valid_beyond_last_term():
    """A valid training expiring after the last usable term is not a candidate."""
    status_df = make_status_df({"status": "valid", "valid_until": pd.Timestamp("2027-06-01")})
    candidates_df = build_candidates_df(status_df, find_usable_terms(make_terms_df({})))
    assert candidates_df.empty


def test_candidates_exclude_one_off():
    """A completed one-off training (no expiry) is never a candidate."""
    status_df = make_status_df({"status": "valid", "is_one_off": True})
    candidates_df = build_candidates_df(status_df, find_usable_terms(make_terms_df({})))
    assert candidates_df.empty


def test_candidates_priority_order():
    """Missing first, then the oldest expiry, last-chance trainings last."""
    status_df = make_status_df(
        {"id_zamestnance": "E1", "status": "expiring", "valid_until": pd.Timestamp("2026-11-01")},
        {"id_zamestnance": "E2", "status": "missing"},
        {"id_zamestnance": "E3", "status": "expired", "valid_until": pd.Timestamp("2026-05-01")},
        {"id_zamestnance": "E4", "status": "expired", "valid_until": pd.Timestamp("2025-01-01")},
        {"id_zamestnance": "E5", "status": "valid", "valid_until": pd.Timestamp("2027-01-01")},
    )
    terms_df = make_terms_df({"datum": pd.Timestamp("2027-01-15")})
    candidates_df = build_candidates_df(status_df, find_usable_terms(terms_df))
    assert candidates_df["id_zamestnance"].tolist() == ["E2", "E4", "E3", "E1", "E5"]


def test_candidates_tie_broken_by_employee_id():
    """Equally urgent candidates are ordered by employee ID."""
    status_df = make_status_df({"id_zamestnance": "E2"}, {"id_zamestnance": "E1"})
    candidates_df = build_candidates_df(status_df, find_usable_terms(make_terms_df({})))
    assert candidates_df["id_zamestnance"].tolist() == ["E1", "E2"]


def test_schedule_last_seat_goes_to_most_urgent():
    """With one seat, the expired employee gets it and the expiring one is left without."""
    status_df = make_status_df(
        {"id_zamestnance": "E1", "status": "expiring", "valid_until": pd.Timestamp("2026-11-20")},
        {"id_zamestnance": "E2", "status": "expired", "valid_until": pd.Timestamp("2026-06-01")},
    )
    schedule_df = build_schedule_df(status_df, make_terms_df({"kapacita": 1}))
    schedule_by_employee_df = schedule_df.set_index("id_zamestnance")
    assert schedule_by_employee_df.loc["E2", "id_terminu"] == "T1"
    assert pd.isna(schedule_by_employee_df.loc["E1", "id_terminu"])
    assert schedule_by_employee_df.loc["E1", "unassigned_reason"] == NO_FREE_SEAT


def test_schedule_full_term_moves_to_later_term():
    """When the earliest term fills up, the next candidate gets the next term."""
    status_df = make_status_df({"id_zamestnance": "E1"}, {"id_zamestnance": "E2"})
    terms_df = make_terms_df(
        {"id_terminu": "T1", "datum": pd.Timestamp("2026-11-01"), "kapacita": 1},
        {"id_terminu": "T2", "datum": pd.Timestamp("2026-12-01"), "kapacita": 1},
    )
    schedule_df = build_schedule_df(status_df, terms_df)
    assert assigned_term(schedule_df, "E1") == "T1"
    assert assigned_term(schedule_df, "E2") == "T2"


def test_schedule_respects_booked_seats():
    """Seats already booked are not handed out again."""
    status_df = make_status_df({"id_zamestnance": "E1"}, {"id_zamestnance": "E2"})
    schedule_df = build_schedule_df(status_df, make_terms_df({"kapacita": 2, "obsazeno": 1}))
    assert schedule_df["id_terminu"].notna().sum() == 1


def test_schedule_no_term_after_end_date():
    """A leaving employee is not booked into a term after their last day."""
    status_df = make_status_df({"datum_ukonceni": pd.Timestamp("2026-10-15")})
    schedule_df = build_schedule_df(status_df, make_terms_df({}))
    assert pd.isna(schedule_df["id_terminu"].iloc[0])
    assert schedule_df["unassigned_reason"].iloc[0] == NO_TERM_BEFORE_END


def test_schedule_term_before_end_date():
    """A leaving employee is booked into a term before their last day."""
    status_df = make_status_df({"datum_ukonceni": pd.Timestamp("2026-12-01")})
    schedule_df = build_schedule_df(status_df, make_terms_df({}))
    assert schedule_df["id_terminu"].iloc[0] == "T1"


def test_schedule_no_term_before_start_date():
    """A new employee is not booked into a term before their first day."""
    status_df = make_status_df({"datum_nastupu": pd.Timestamp("2026-12-01")})
    schedule_df = build_schedule_df(status_df, make_terms_df({}))
    assert pd.isna(schedule_df["id_terminu"].iloc[0])
    assert schedule_df["unassigned_reason"].iloc[0] == NO_TERM_AFTER_START


def test_schedule_term_after_start_date():
    """A new employee is booked into the first term on or after their first day."""
    status_df = make_status_df({"datum_nastupu": pd.Timestamp("2026-11-15")})
    terms_df = make_terms_df(
        {"id_terminu": "T1", "datum": pd.Timestamp("2026-11-01")},
        {"id_terminu": "T2", "datum": pd.Timestamp("2026-11-15")},
    )
    schedule_df = build_schedule_df(status_df, terms_df)
    assert schedule_df["id_terminu"].iloc[0] == "T2"


def test_schedule_flags_term_after_expiry():
    """A term after a still-valid training expires is flagged."""
    status_df = make_status_df({"status": "expiring", "valid_until": pd.Timestamp("2026-10-20")})
    schedule_df = build_schedule_df(status_df, make_terms_df({}))
    assert schedule_df["is_after_expiry"].iloc[0]


def test_schedule_trainings_do_not_share_seats():
    """A term of one training never takes a candidate for another."""
    status_df = make_status_df({"kod_skoleni": "GDPR"})
    schedule_df = build_schedule_df(status_df, make_terms_df({}))
    assert pd.isna(schedule_df["id_terminu"].iloc[0])
    assert schedule_df["unassigned_reason"].iloc[0] == NO_FREE_SEAT


def test_shortfall_counts_candidates_without_seat():
    """The shortfall per training is candidates minus assigned seats."""
    status_df = make_status_df({"id_zamestnance": "E1"}, {"id_zamestnance": "E2"})
    schedule_df = build_schedule_df(status_df, make_terms_df({"kapacita": 1}))
    shortfall_df = build_shortfall_df(schedule_df)
    assert shortfall_df.to_dict("records") == [
        {"kod_skoleni": "KYBER", "candidates": 2, "assigned": 1, "without_seat": 1}
    ]
