"""Shape the compliance and scheduling results into what the pages show."""

from dataclasses import dataclass

import pandas as pd

from app.compliance import build_status_df
from app.constants import (
    ENDED_STATE,
    EXPORT_DATE,
    NEEDS_TRAINING_STATUSES,
    PAIR_KEY,
    PARENTAL_LEAVE_STATE,
    STATE_BY_STATUS,
    STATE_LABELS,
    STATUS_ORDER,
    UNKNOWN_DEPARTMENT,
)
from app.scheduling import build_schedule_df, build_shortfall_df, find_usable_terms


@dataclass(frozen=True)
class Register:
    """Everything the pages show, computed once at startup.

    Attributes:
        rows_df: One row per employee and required training, with status, term and notes.
        terms_df: Usable terms with free seats and the training's `nazev`, earliest first.
        capacity_df: Per training, bookings that come too late or not at all.
        employees_df: Cleaned employees.
    """

    rows_df: pd.DataFrame
    terms_df: pd.DataFrame
    capacity_df: pd.DataFrame
    employees_df: pd.DataFrame


def format_date(value: pd.Timestamp) -> str:
    """Format a date for the pages, "" when empty.

    Args:
        value: A date or NaT.

    Returns:
        The date in Czech format, like "7. 10. 2026".
    """
    if pd.isna(value):
        return ""
    return f"{value.day}. {value.month}. {value.year}"


def pick_plural(count: int, one: str, few: str, many: str) -> str:
    """Pick the Czech word form that goes with a count.

    Args:
        count: The count.
        one: Form for 1, e.g. "zaměstnanec".
        few: Form for 2 to 4, e.g. "zaměstnanci".
        many: Form for 0 and 5 or more, e.g. "zaměstnanců".

    Returns:
        The matching form.
    """
    if count == 1:
        return one
    if 2 <= count <= 4:
        return few
    return many


def build_problem(row: pd.Series) -> str:
    """Describe in words what is wrong with one required training.

    Args:
        row: One register row.

    Returns:
        For example "GDPR: neplatné" or "KYBER: platí do 30. 11. 2026".
    """
    code = row["kod_skoleni"]
    if row["state"] == "not_valid":
        return f"{code}: neplatné"
    return f"{code}: platí do {format_date(row['valid_until'])}"


def build_no_booking_reason(row: pd.Series) -> str:
    """Explain why a required training has no term to book.

    Args:
        row: One register row.

    Returns:
        For example "bez místa: žádné volné místo", "" when the training has a term or
        needs none.
    """
    if row["unassigned_reason"]:
        return f"bez místa: {row['unassigned_reason']}"
    if row["stav"] == PARENTAL_LEAVE_STATE:
        return "nepřihlašovat: rodičovská dovolená"
    return ""


def build_row_notes(row: pd.Series) -> list[str]:
    """List the data warnings for one required training.

    Args:
        row: One register row.

    Returns:
        The notes, empty when there is nothing to warn about.
    """
    notes = []
    if pd.notna(row["advance_record_date"]):
        advance_date = row["advance_record_date"]
        notes.append(f"záznam na {format_date(advance_date)} zadán předem, nezapočítán")
    return notes


def build_person_notes(row: pd.Series) -> list[str]:
    """List what HR should know about the employee of a register row.

    Args:
        row: Any register row of the employee.

    Returns:
        The notes, empty when there is nothing to note.
    """
    notes = []
    if row["stav"] == PARENTAL_LEAVE_STATE:
        notes.append("rodičovská dovolená")
    if row["datum_nastupu"] > EXPORT_DATE:
        notes.append(f"nastupuje {format_date(row['datum_nastupu'])}")
    if pd.notna(row["datum_ukonceni"]):
        notes.append(f"odchází {format_date(row['datum_ukonceni'])}")
    if row["utvar"] == "":
        notes.append("neznámé oddělení: školení podle oddělení nejsou zkontrolována")
    return notes


def build_rows_df(
    status_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    employees_df: pd.DataFrame,
    catalog_df: pd.DataFrame,
    terms_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join status, schedule, names and training titles into one row per required training.

    A row is a to-do when the training is missing, expired or expiring, or when it got
    (or needed) a seat in an upcoming term.

    Args:
        status_df: Output of `build_status_df`.
        schedule_df: Output of `build_schedule_df`.
        employees_df: Cleaned employees.
        catalog_df: Cleaned training catalog.
        terms_df: Cleaned terms.

    Returns:
        The rows, most urgent status first, then the oldest expiry.
    """
    names_df = employees_df[["id_zamestnance", "jmeno", "prijmeni", "pozice"]]
    titles_df = catalog_df[["kod", "nazev"]]
    titles_df = titles_df.rename(columns={"kod": "kod_skoleni"})
    schedule_columns = [
        *PAIR_KEY,
        "id_terminu",
        "term_date",
        "is_after_expiry",
        "unassigned_reason",
    ]

    rows_df = status_df.merge(names_df, on="id_zamestnance", how="left")
    rows_df = rows_df.merge(titles_df, on="kod_skoleni", how="left")
    scheduled_df = schedule_df[schedule_columns]
    rows_df = rows_df.merge(scheduled_df, on=PAIR_KEY, how="left")

    # Rows that are not scheduling candidates get NaN from the left merge.
    rows_df["id_terminu"] = rows_df["id_terminu"].fillna("")
    rows_df["unassigned_reason"] = rows_df["unassigned_reason"].fillna("")
    rows_df["is_after_expiry"] = rows_df["is_after_expiry"].eq(True)
    times_by_term = terms_df.set_index("id_terminu")["cas"]
    rows_df["term_time"] = rows_df["id_terminu"].map(times_by_term)

    needs_training = rows_df["status"].isin(NEEDS_TRAINING_STATUSES)
    has_term = rows_df["id_terminu"] != ""
    has_no_seat = rows_df["unassigned_reason"] != ""
    rows_df["is_to_do"] = needs_training | has_term | has_no_seat

    rows_df["name"] = rows_df["prijmeni"] + " " + rows_df["jmeno"]
    rows_df["department"] = rows_df["utvar"].replace("", UNKNOWN_DEPARTMENT)
    rows_df["state"] = rows_df["status"].map(STATE_BY_STATUS)
    rows_df["state_label"] = rows_df["state"].map(STATE_LABELS)
    rows_df["problem"] = [build_problem(row) for _, row in rows_df.iterrows()]
    rows_df["no_booking_reason"] = [build_no_booking_reason(row) for _, row in rows_df.iterrows()]
    rows_df["notes"] = [build_row_notes(row) for _, row in rows_df.iterrows()]

    status_rank = {status: rank for rank, status in enumerate(STATUS_ORDER)}
    rows_df["status_rank"] = rows_df["status"].map(status_rank)
    sort_columns = ["status_rank", "valid_until", "id_zamestnance"]
    return rows_df.sort_values(sort_columns, na_position="first")


def build_register(tables: dict[str, pd.DataFrame]) -> Register:
    """Compute compliance and the schedule and shape them for the pages.

    Args:
        tables: Output of `load_clean_tables`.

    Returns:
        The register the pages read from.
    """
    status_df = build_status_df(
        employees_df=tables["employees"],
        catalog_df=tables["catalog"],
        completions_df=tables["completions"],
    )
    terms_df = find_usable_terms(tables["terms"])
    titles_by_code = tables["catalog"].set_index("kod")["nazev"]
    terms_df["nazev"] = terms_df["kod_skoleni"].map(titles_by_code)
    schedule_df = build_schedule_df(status_df, tables["terms"])
    rows_df = build_rows_df(
        status_df=status_df,
        schedule_df=schedule_df,
        employees_df=tables["employees"],
        catalog_df=tables["catalog"],
        terms_df=tables["terms"],
    )
    shortfall_df = build_shortfall_df(schedule_df)
    capacity_df = build_capacity_df(terms_df, shortfall_df)
    return Register(
        rows_df=rows_df,
        terms_df=terms_df,
        capacity_df=capacity_df,
        employees_df=tables["employees"],
    )


def find_seats_for_all_date(code_terms_df: pd.DataFrame, needed: int) -> pd.Timestamp:
    """Find the term by which the free seats, counted from the earliest term, cover everyone.

    Args:
        code_terms_df: Usable terms of one training, earliest first.
        needed: How many people need a seat.

    Returns:
        The date of that term, NaT when all published terms together are not enough.
    """
    cumulative_seats = code_terms_df["free_seats"].cumsum()
    is_enough = cumulative_seats >= needed
    if not is_enough.any():
        return pd.NaT
    enough_dates = code_terms_df.loc[is_enough, "datum"]
    return enough_dates.iloc[0]


def build_capacity_df(terms_df: pd.DataFrame, shortfall_df: pd.DataFrame) -> pd.DataFrame:
    """Show per training how many people need a term and when there is a seat for all of them.

    The date counts free seats only, so it shows whether the published terms come in time;
    one person's start or end date does not move it.

    Args:
        terms_df: Usable terms with `free_seats` and `nazev`, earliest first.
        shortfall_df: Output of `build_shortfall_df`.

    Returns:
        One row per training with people to book: `kod_skoleni`, `nazev`, `candidates`, the
        date and free seats of the first term, `seats_for_all_date` and `fits_first_term`.
        Latest `seats_for_all_date` first, trainings whose terms are not enough at the top.
    """
    capacity_df = shortfall_df.set_index("kod_skoleni")[["candidates"]]
    first_terms_df = terms_df.groupby("kod_skoleni").nth(0)
    first_terms_df = first_terms_df.set_index("kod_skoleni")
    capacity_df["nazev"] = first_terms_df["nazev"]
    capacity_df["first_term_date"] = first_terms_df["datum"]
    capacity_df["first_term_seats"] = first_terms_df["free_seats"].astype("Int64")
    seats_for_all_dates = []
    for code, needed in capacity_df["candidates"].items():
        is_code_term = terms_df["kod_skoleni"] == code
        code_terms_df = terms_df[is_code_term]
        seats_for_all_dates.append(find_seats_for_all_date(code_terms_df, needed))
    capacity_df["seats_for_all_date"] = seats_for_all_dates
    capacity_df["fits_first_term"] = capacity_df["candidates"] <= capacity_df["first_term_seats"]

    has_candidates = capacity_df["candidates"] > 0
    capacity_df = capacity_df[has_candidates]
    capacity_df = capacity_df.sort_values(
        "seats_for_all_date", ascending=False, na_position="first"
    )
    return capacity_df.reset_index()


def build_summary(register: Register) -> dict[str, int]:
    """Count the headline numbers of the pages.

    Args:
        register: Output of `build_register`.

    Returns:
        Employees in scope, with a to-do, with a training not valid (`employees_not_valid`)
        and with one expiring soon (`employees_expiring`), bookings, bookings after expiry
        and the employees they belong to (`employees_after_expiry`), and to-dos without a seat.
    """
    rows_df = register.rows_df
    employee_ids = rows_df["id_zamestnance"]
    has_term = rows_df["id_terminu"] != ""
    has_no_seat = rows_df["unassigned_reason"] != ""
    is_to_do = rows_df["is_to_do"]
    is_late = rows_df["is_after_expiry"]
    summary = {
        "employees": employee_ids.nunique(),
        "employees_with_to_do": employee_ids[is_to_do].nunique(),
        "bookings": int(has_term.sum()),
        "after_expiry": int(is_late.sum()),
        "employees_after_expiry": employee_ids[is_late].nunique(),
        "without_seat": int(has_no_seat.sum()),
    }
    for state in ["not_valid", "expiring"]:
        has_state = rows_df["state"] == state
        summary[f"employees_{state}"] = employee_ids[has_state].nunique()
    return summary


def count_by_state(rows_df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Count required trainings per state for each group.

    Args:
        rows_df: Register rows.
        columns: Columns to group by.

    Returns:
        One row per group with the group columns and one count column per state.
    """
    groups = [rows_df[column] for column in columns]
    counts_df = pd.crosstab(groups, rows_df["state"])
    counts_df = counts_df.reindex(columns=list(STATE_LABELS), fill_value=0)
    return counts_df.reset_index()


def filter_rows(
    rows_df: pd.DataFrame,
    training: str,
    department: str,
    state: str,
    query: str,
) -> pd.DataFrame:
    """Keep the rows matching the filters of the people page.

    Args:
        rows_df: Register rows.
        training: Training code, "" for all.
        department: Department as shown on the page, "" for all.
        state: State (`not_valid`, `expiring`, `valid`), "" for all.
        query: Part of the employee's name or ID, any case, "" for all.

    Returns:
        The matching rows.
    """
    is_shown = pd.Series(True, index=rows_df.index)
    if training:
        is_shown &= rows_df["kod_skoleni"] == training
    if department:
        is_shown &= rows_df["department"] == department
    if state:
        is_shown &= rows_df["state"] == state
    if query:
        searched_text = rows_df["name"] + " " + rows_df["id_zamestnance"]
        is_shown &= searched_text.str.contains(query, case=False, regex=False)
    return rows_df[is_shown]


def build_people(rows_df: pd.DataFrame) -> list[dict]:
    """Group the to-dos by employee, the employee with the most urgent to-do first.

    Args:
        rows_df: Register rows, most urgent first.

    Returns:
        One dict per employee with a to-do: `id_zamestnance`, `name`, `department`,
        `notes` and `to_dos` (their rows).
    """
    to_do_df = rows_df[rows_df["is_to_do"]]
    people = []
    for employee_id, person_df in to_do_df.groupby("id_zamestnance", sort=False):
        first_row = person_df.iloc[0]
        person = {
            "id_zamestnance": employee_id,
            "name": first_row["name"],
            "department": first_row["department"],
            "notes": build_person_notes(first_row),
            "to_dos": person_df,
        }
        people.append(person)
    return people


def find_term(register: Register, term_id: str) -> dict | None:
    """Find a usable term with the employees to sign up for it.

    Args:
        register: Output of `build_register`.
        term_id: Term ID.

    Returns:
        The term's fields plus `bookings` (rows sorted by name), or None when the ID is not
        a usable term.
    """
    terms_df = register.terms_df
    matches_df = terms_df[terms_df["id_terminu"] == term_id]
    if matches_df.empty:
        return None
    rows_df = register.rows_df
    bookings_df = rows_df[rows_df["id_terminu"] == term_id]
    bookings_df = bookings_df.sort_values("name")
    term = matches_df.iloc[0].to_dict()
    return term | {"bookings": bookings_df}


def find_employee(register: Register, employee_id: str) -> pd.Series | None:
    """Find an employee in scope.

    Args:
        register: Output of `build_register`.
        employee_id: Employee ID.

    Returns:
        The employee's row, or None when the ID is unknown or the employee has left.
    """
    employees_df = register.employees_df
    is_match = employees_df["id_zamestnance"] == employee_id
    is_in_scope = employees_df["stav"] != ENDED_STATE
    matches_df = employees_df[is_match & is_in_scope]
    if matches_df.empty:
        return None
    return matches_df.iloc[0]
