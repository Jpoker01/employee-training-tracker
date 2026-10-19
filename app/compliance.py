"""Required trainings per employee and their status at the export date."""

import numpy as np
import pandas as pd

from app.constants import (
    EMPLOYEE_COLUMNS,
    ENDED_STATE,
    EXPIRING_DAYS,
    EXPORT_DATE,
    PAIR_KEY,
    RECORD_COLUMNS,
)


def is_required(requirement: str, department: str, position: str) -> bool:
    """Tell whether a catalog requirement (`povinne_pro`) applies to an employee.

    Args:
        requirement: `VSICHNI`, `UTVAR:a;b`, `POZICE:x` or `NEPOVINNE`.
        department: The employee's department, "" when unknown.
        position: The employee's position.

    Returns:
        True when the training is required. An unknown department matches no `UTVAR` rule.

    Raises:
        ValueError: When the requirement has none of the known forms.
    """
    kind, _, values = requirement.partition(":")
    if kind == "VSICHNI":
        return True
    if kind == "NEPOVINNE":
        return False
    if kind == "UTVAR":
        return department in values.split(";")
    if kind == "POZICE":
        return position in values.split(";")
    raise ValueError(f"Unknown requirement: {requirement!r}")


def build_required_df(employees_df: pd.DataFrame, catalog_df: pd.DataFrame) -> pd.DataFrame:
    """List every required training of every employee in scope.

    Employees who left (`ukončen`) are out of scope; people on parental leave are in.

    Args:
        employees_df: Cleaned employees.
        catalog_df: Cleaned training catalog.

    Returns:
        One row per employee and required training: `id_zamestnance`, `kod_skoleni`.
    """
    is_in_scope = employees_df["stav"] != ENDED_STATE
    in_scope_df = employees_df[is_in_scope]
    requirements_df = catalog_df[["kod", "povinne_pro"]]
    pairs_df = in_scope_df.merge(requirements_df, how="cross")
    is_pair_required = [
        is_required(requirement, department, position)
        for requirement, department, position in zip(
            pairs_df["povinne_pro"], pairs_df["utvar"], pairs_df["pozice"]
        )
    ]
    required_df = pairs_df.loc[is_pair_required, ["id_zamestnance", "kod"]]
    required_df = required_df.rename(columns={"kod": "kod_skoleni"})
    return required_df.reset_index(drop=True)


def compute_valid_until(completions_df: pd.DataFrame, catalog_df: pd.DataFrame) -> pd.DataFrame:
    """Keep the completions that count and compute until when each one is valid.

    A record does not count when it is dated after the export, has an unknown code, a name
    that does not match the employee, or no date. It is valid until the earlier of
    `platnost_do` and completion date + catalog validity; an empty `platnost_do` leaves the
    catalog date. Trainings with validity 0 (LEAD) are one-off and never expire.

    Args:
        completions_df: Cleaned completions.
        catalog_df: Cleaned training catalog.

    Returns:
        The counted records with `valid_until` and `is_one_off`.
    """
    flag_columns = ["is_future", "is_unknown_code", "is_name_mismatch"]
    is_flagged = completions_df[flag_columns].any(axis=1)
    has_date = completions_df["datum_absolvovani"].notna()
    is_counted = ~is_flagged & has_date
    records_df = completions_df.loc[is_counted, RECORD_COLUMNS]
    records_df = records_df.copy()

    months_by_code = catalog_df.set_index("kod")["platnost_mesicu"]
    months = records_df["kod_skoleni"].map(months_by_code)
    months = months.fillna(0)
    catalog_until = [
        completed + pd.DateOffset(months=int(validity)) if validity > 0 else pd.NaT
        for completed, validity in zip(records_df["datum_absolvovani"], months)
    ]
    records_df["catalog_until"] = pd.Series(
        catalog_until,
        index=records_df.index,
        dtype="datetime64[ns]",
    )
    records_df["valid_until"] = records_df[["platnost_do", "catalog_until"]].min(axis=1)

    is_one_off_code = catalog_df["platnost_mesicu"] == 0
    one_off_codes = catalog_df.loc[is_one_off_code, "kod"]
    records_df["is_one_off"] = records_df["kod_skoleni"].isin(one_off_codes)
    return records_df


def find_advance_dates(completions_df: pd.DataFrame) -> pd.DataFrame:
    """Find the earliest record entered in advance (dated after the export) per training.

    Args:
        completions_df: Cleaned completions.

    Returns:
        One row per employee and training with `advance_record_date`.
    """
    future_df = completions_df[completions_df["is_future"]]
    advance_df = future_df.groupby(PAIR_KEY, as_index=False)["datum_absolvovani"].min()
    return advance_df.rename(columns={"datum_absolvovani": "advance_record_date"})


def compute_status(
    status_df: pd.DataFrame,
    export_date: pd.Timestamp,
    expiring_days: int,
) -> pd.Series:
    """Classify each required training as missing, expired, expiring or valid.

    Args:
        status_df: Required trainings merged with their latest counted record.
        export_date: Date the status is computed for.
        expiring_days: How many days before expiry a training counts as expiring.

    Returns:
        The status per row. One-off trainings are valid once completed.
    """
    valid_until = status_df["valid_until"]
    expiring_limit = export_date + pd.Timedelta(days=expiring_days)

    is_missing = status_df["id_zaznamu"].isna()
    is_one_off = status_df["is_one_off"]
    has_no_expiry_date = valid_until.isna()
    is_past_expiry = valid_until < export_date
    is_expired = has_no_expiry_date | is_past_expiry
    is_expiring = valid_until <= expiring_limit

    status = np.select(
        [is_missing, is_one_off, is_expired, is_expiring],
        ["missing", "valid", "expired", "expiring"],
        default="valid",
    )
    return pd.Series(status, index=status_df.index)


def build_status_df(
    employees_df: pd.DataFrame,
    catalog_df: pd.DataFrame,
    completions_df: pd.DataFrame,
    export_date: pd.Timestamp = EXPORT_DATE,
    expiring_days: int = EXPIRING_DAYS,
) -> pd.DataFrame:
    """Compute the status of every required training of every employee in scope.

    The latest counted completion decides the status.

    Args:
        employees_df: Cleaned employees.
        catalog_df: Cleaned training catalog.
        completions_df: Cleaned completions.
        export_date: Date the status is computed for.
        expiring_days: How many days before expiry a training counts as expiring.

    Returns:
        One row per employee and required training with the latest counted record,
        `advance_record_date`, the employee's `stav`, `utvar` and `datum_ukonceni`,
        and `status`.
    """
    records_df = compute_valid_until(completions_df, catalog_df)
    records_df = records_df.sort_values("datum_absolvovani")
    latest_df = records_df.drop_duplicates(PAIR_KEY, keep="last")

    required_df = build_required_df(employees_df, catalog_df)
    advance_df = find_advance_dates(completions_df)
    employee_facts_df = employees_df[EMPLOYEE_COLUMNS]

    status_df = required_df.merge(latest_df, on=PAIR_KEY, how="left")
    status_df = status_df.merge(advance_df, on=PAIR_KEY, how="left")
    status_df = status_df.merge(employee_facts_df, on="id_zamestnance", how="left")

    # Rows without a record get NaN from the left merge; they are not one-off.
    status_df["is_one_off"] = status_df["is_one_off"].eq(True)
    status_df["status"] = compute_status(status_df, export_date, expiring_days)
    return status_df
