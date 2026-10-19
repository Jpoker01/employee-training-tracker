"""Load the cleaned tables written by notebooks/01_cleaning_ntb.ipynb."""

from pathlib import Path

import pandas as pd

from app.constants import CLEAN_DIR, DATE_COLUMNS, INT_COLUMNS, TABLE_NAMES


def load_table(name: str, clean_dir: Path = CLEAN_DIR) -> pd.DataFrame:
    """Load one cleaned table with dates, numbers and flags typed.

    Empty text values stay "", empty dates become NaT and empty numbers NA.

    Args:
        name: Table name, one of TABLE_NAMES.
        clean_dir: Directory with the cleaned CSV files.

    Returns:
        The typed table.
    """
    table_df = pd.read_csv(clean_dir / f"{name}.csv", dtype=str, keep_default_na=False)
    for column in table_df.columns:
        values = table_df[column].replace("", None)
        if column in DATE_COLUMNS:
            table_df[column] = pd.to_datetime(values)
        elif column in INT_COLUMNS:
            numbers = pd.to_numeric(values)
            table_df[column] = numbers.astype("Int64")
        elif column.startswith("is_"):
            table_df[column] = table_df[column] == "True"
    return table_df


def load_clean_tables(clean_dir: Path = CLEAN_DIR) -> dict[str, pd.DataFrame]:
    """Load all cleaned tables.

    Args:
        clean_dir: Directory with the cleaned CSV files.

    Returns:
        The tables keyed by name.
    """
    return {name: load_table(name, clean_dir) for name in TABLE_NAMES}
