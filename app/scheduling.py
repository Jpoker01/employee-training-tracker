"""Assign employees who need a training to free seats in upcoming terms."""

import pandas as pd

from app.constants import (
    CANCELLED_TERM_STATE,
    EXPORT_DATE,
    NEEDS_TRAINING_STATUSES,
    NO_FREE_SEAT,
    NO_TERM_AFTER_START,
    NO_TERM_BEFORE_END,
    PARENTAL_LEAVE_STATE,
)


def find_usable_terms(
    terms_df: pd.DataFrame,
    export_date: pd.Timestamp = EXPORT_DATE,
) -> pd.DataFrame:
    """Keep the terms that can take bookings and count their free seats.

    A term is usable when it is after the export date (so it has a valid date), not
    cancelled, has a known training code and at least one free seat. Free seats are
    capacity minus seats already booked.

    Args:
        terms_df: Cleaned terms.
        export_date: Date the schedule is made for.

    Returns:
        The usable terms with `free_seats`, earliest first.
    """
    usable_df = terms_df.copy()
    usable_df["free_seats"] = usable_df["kapacita"] - usable_df["obsazeno"]

    is_future = usable_df["datum"] > export_date
    is_cancelled = usable_df["stav"] == CANCELLED_TERM_STATE
    is_known_code = ~usable_df["is_unknown_code"]
    has_free_seat = usable_df["free_seats"] > 0
    is_usable = is_future & ~is_cancelled & is_known_code & has_free_seat

    usable_df = usable_df[is_usable]
    return usable_df.sort_values(["datum", "id_terminu"])


def find_overbooked_terms(
    terms_df: pd.DataFrame,
    export_date: pd.Timestamp = EXPORT_DATE,
) -> pd.DataFrame:
    """Find upcoming terms with more seats booked than they have.

    Args:
        terms_df: Cleaned terms.
        export_date: Date the schedule is made for.

    Returns:
        The overbooked terms with `extra_seats`, earliest first.
    """
    is_future = terms_df["datum"] > export_date
    is_cancelled = terms_df["stav"] == CANCELLED_TERM_STATE
    is_overbooked = terms_df["obsazeno"] > terms_df["kapacita"]
    is_shown = is_future & ~is_cancelled & is_overbooked

    overbooked_df = terms_df[is_shown].copy()
    overbooked_df["extra_seats"] = overbooked_df["obsazeno"] - overbooked_df["kapacita"]
    return overbooked_df.sort_values(["datum", "id_terminu"])


def build_candidates_df(status_df: pd.DataFrame, usable_terms_df: pd.DataFrame) -> pd.DataFrame:
    """List who should get a seat, most urgent first.

    Candidates are everyone with a missing, expired or expiring training, plus anyone whose
    training expires before that training's last usable term ("last chance"). People on
    parental leave are left out. Whoever has been, or will be, without a valid training the
    longest goes first: missing, then the oldest expiry date. Ties go by employee ID.

    Args:
        status_df: Output of `build_status_df`.
        usable_terms_df: Output of `find_usable_terms`.

    Returns:
        The candidate rows of `status_df` in priority order.
    """
    last_term_dates = usable_terms_df.groupby("kod_skoleni")["datum"].max()
    last_term_date = status_df["kod_skoleni"].map(last_term_dates)

    needs_training = status_df["status"].isin(NEEDS_TRAINING_STATUSES)
    is_valid = status_df["status"] == "valid"
    expires_before_last_term = status_df["valid_until"] <= last_term_date
    is_last_chance = is_valid & ~status_df["is_one_off"] & expires_before_last_term
    is_on_leave = status_df["stav"] == PARENTAL_LEAVE_STATE

    is_candidate = (needs_training | is_last_chance) & ~is_on_leave
    candidates_df = status_df[is_candidate]
    return candidates_df.sort_values(["valid_until", "id_zamestnance"], na_position="first")


def choose_term(
    code: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    usable_terms_df: pd.DataFrame,
    free_seats: dict[str, int],
) -> tuple[str | None, str]:
    """Pick the earliest term of a training with a seat while the employee works here.

    Args:
        code: Training code.
        start_date: The employee's first day; terms before it are skipped.
        end_date: The employee's last day, NaT when not leaving.
        usable_terms_df: Output of `find_usable_terms`, earliest first.
        free_seats: Seats still free per term ID.

    Returns:
        The chosen term ID and "", or None and the reason no term was found.
    """
    code_terms_df = usable_terms_df[usable_terms_df["kod_skoleni"] == code]
    after_start_df = code_terms_df
    if pd.notna(start_date):
        after_start_df = code_terms_df[code_terms_df["datum"] >= start_date]
    reachable_terms_df = after_start_df
    if pd.notna(end_date):
        reachable_terms_df = after_start_df[after_start_df["datum"] < end_date]

    for term_id in reachable_terms_df["id_terminu"]:
        if free_seats[term_id] > 0:
            return term_id, ""
    if code_terms_df.empty:
        return None, NO_FREE_SEAT
    if after_start_df.empty:
        return None, NO_TERM_AFTER_START
    if reachable_terms_df.empty:
        return None, NO_TERM_BEFORE_END
    return None, NO_FREE_SEAT


def assign_terms(candidates_df: pd.DataFrame, usable_terms_df: pd.DataFrame) -> pd.DataFrame:
    """Give each candidate, in priority order, the earliest term with a free seat.

    Args:
        candidates_df: Output of `build_candidates_df`.
        usable_terms_df: Output of `find_usable_terms`.

    Returns:
        The candidates with `id_terminu` and `term_date` (empty when no seat was found),
        `unassigned_reason` and `is_after_expiry` (the term is after a still-valid training
        expires).
    """
    free_seats = dict(zip(usable_terms_df["id_terminu"], usable_terms_df["free_seats"]))
    term_ids = []
    reasons = []
    for candidate in candidates_df.itertuples(index=False):
        term_id, reason = choose_term(
            code=candidate.kod_skoleni,
            start_date=candidate.datum_nastupu,
            end_date=candidate.datum_ukonceni,
            usable_terms_df=usable_terms_df,
            free_seats=free_seats,
        )
        if term_id is not None:
            free_seats[term_id] -= 1
        term_ids.append(term_id)
        reasons.append(reason)

    assignments_df = candidates_df.copy()
    assignments_df["id_terminu"] = term_ids
    assignments_df["unassigned_reason"] = reasons

    term_dates = usable_terms_df.set_index("id_terminu")["datum"]
    assignments_df["term_date"] = assignments_df["id_terminu"].map(term_dates)
    is_valid_today = assignments_df["status"].isin(["expiring", "valid"])
    is_term_late = assignments_df["term_date"] > assignments_df["valid_until"]
    assignments_df["is_after_expiry"] = is_valid_today & is_term_late
    return assignments_df


def build_shortfall_df(assignments_df: pd.DataFrame) -> pd.DataFrame:
    """Count per training how many candidates got a seat and how many did not.

    Args:
        assignments_df: Output of `assign_terms`.

    Returns:
        One row per training: `candidates`, `assigned`, `without_seat`.
    """
    has_term = assignments_df["id_terminu"].notna()
    counted_df = assignments_df.assign(has_term=has_term)
    shortfall_df = counted_df.groupby("kod_skoleni", as_index=False).agg(
        candidates=("id_zamestnance", "size"),
        assigned=("has_term", "sum"),
    )
    shortfall_df["without_seat"] = shortfall_df["candidates"] - shortfall_df["assigned"]
    return shortfall_df


def build_schedule_df(
    status_df: pd.DataFrame,
    terms_df: pd.DataFrame,
    export_date: pd.Timestamp = EXPORT_DATE,
) -> pd.DataFrame:
    """Plan who goes to which upcoming term.

    Args:
        status_df: Output of `build_status_df`.
        terms_df: Cleaned terms.
        export_date: Date the schedule is made for.

    Returns:
        One row per candidate with the assigned term or the reason there is none.
    """
    usable_terms_df = find_usable_terms(terms_df, export_date)
    candidates_df = build_candidates_df(status_df, usable_terms_df)
    return assign_terms(candidates_df, usable_terms_df)
