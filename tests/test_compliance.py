import pandas as pd
import pytest

from app.compliance import (
    build_required_df,
    build_status_df,
    compute_valid_until,
    is_required,
)


@pytest.fixture
def catalog_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "kod": ["BOZP-Z", "PRV-POM", "LEAD", "ANGL"],
            "platnost_mesicu": pd.array([24, 36, 0, pd.NA], dtype="Int64"),
            "povinne_pro": ["VSICHNI", "UTVAR:Laboratoře;Knihovna", "POZICE:Vedoucí", "NEPOVINNE"],
        }
    )


def make_employees_df(**overrides) -> pd.DataFrame:
    employee = {
        "id_zamestnance": "E1",
        "utvar": "Knihovna",
        "pozice": "Referent",
        "stav": "aktivní",
        "datum_nastupu": pd.Timestamp("2020-01-01"),
        "datum_ukonceni": pd.NaT,
    }
    return pd.DataFrame([employee | overrides])


def make_completions_df(*records: dict) -> pd.DataFrame:
    default = {
        "id_zaznamu": "Z1",
        "id_zamestnance": "E1",
        "kod_skoleni": "BOZP-Z",
        "datum_absolvovani": pd.Timestamp("2025-06-01"),
        "platnost_do": pd.Timestamp("2027-06-01"),
        "is_future": False,
        "is_unknown_code": False,
        "is_name_mismatch": False,
    }
    rows = [default | record for record in records]
    completions_df = pd.DataFrame(rows, columns=list(default))
    for column in ["datum_absolvovani", "platnost_do"]:
        completions_df[column] = pd.to_datetime(completions_df[column])
    return completions_df


def status_of(status_df: pd.DataFrame, code: str) -> pd.Series:
    status_by_code_df = status_df.set_index("kod_skoleni")
    return status_by_code_df.loc[code]


def test_is_required_for_everyone():
    """VSICHNI applies to any employee, even one without a department."""
    assert is_required("VSICHNI", "", "Referent")


@pytest.mark.parametrize(
    ("department", "expected"),
    [("Knihovna", True), ("Vedení", False), ("", False)],
)
def test_is_required_by_department(department, expected):
    """UTVAR applies only to listed departments; an unknown department matches none."""
    assert is_required("UTVAR:Laboratoře;Knihovna", department, "Referent") is expected


@pytest.mark.parametrize(("position", "expected"), [("Vedoucí", True), ("Referent", False)])
def test_is_required_by_position(position, expected):
    """POZICE applies only to the listed position."""
    assert is_required("POZICE:Vedoucí", "Vedení", position) is expected


def test_is_required_optional_training():
    """NEPOVINNE never applies."""
    assert not is_required("NEPOVINNE", "Knihovna", "Referent")


def test_is_required_unknown_form_raises():
    """A requirement in an unknown form raises instead of being silently skipped."""
    with pytest.raises(ValueError):
        is_required("SKUPINA:x", "Knihovna", "Referent")


def test_build_required_df_lists_required_trainings(catalog_df):
    """A Knihovna employee needs the training for everyone and the Knihovna one."""
    required_df = build_required_df(make_employees_df(), catalog_df)
    assert sorted(required_df["kod_skoleni"]) == ["BOZP-Z", "PRV-POM"]


def test_build_required_df_excludes_ended_employees(catalog_df):
    """Employees who left have no required trainings."""
    required_df = build_required_df(make_employees_df(stav="ukončen"), catalog_df)
    assert required_df.empty


def test_build_required_df_includes_parental_leave(catalog_df):
    """People on parental leave stay in scope."""
    required_df = build_required_df(make_employees_df(stav="rodičovská"), catalog_df)
    assert len(required_df) == 2


def test_valid_until_record_wins_when_earlier(catalog_df):
    """A platnost_do before completion date + catalog validity is used."""
    records_df = compute_valid_until(
        make_completions_df({"platnost_do": pd.Timestamp("2026-01-01")}), catalog_df
    )
    assert records_df["valid_until"].iloc[0] == pd.Timestamp("2026-01-01")


def test_valid_until_catalog_wins_when_earlier(catalog_df):
    """A platnost_do beyond the catalog validity is cut to the catalog date."""
    records_df = compute_valid_until(
        make_completions_df({"platnost_do": pd.Timestamp("2028-01-01")}), catalog_df
    )
    assert records_df["valid_until"].iloc[0] == pd.Timestamp("2027-06-01")


def test_valid_until_empty_record_uses_catalog(catalog_df):
    """An empty platnost_do falls back to completion date + catalog validity."""
    records_df = compute_valid_until(make_completions_df({"platnost_do": pd.NaT}), catalog_df)
    assert records_df["valid_until"].iloc[0] == pd.Timestamp("2027-06-01")


@pytest.mark.parametrize("flag", ["is_future", "is_unknown_code", "is_name_mismatch"])
def test_valid_until_skips_flagged_records(catalog_df, flag):
    """Future, unknown-code and name-mismatch records never count."""
    records_df = compute_valid_until(make_completions_df({flag: True}), catalog_df)
    assert records_df.empty


def test_valid_until_skips_records_without_date(catalog_df):
    """A record whose date was emptied (placeholder 1900-01-01) never counts."""
    records_df = compute_valid_until(make_completions_df({"datum_absolvovani": pd.NaT}), catalog_df)
    assert records_df.empty


def test_valid_until_marks_validity_zero_as_one_off(catalog_df):
    """A training with catalog validity 0 is one-off."""
    records_df = compute_valid_until(
        make_completions_df({"kod_skoleni": "LEAD", "platnost_do": pd.NaT}), catalog_df
    )
    assert records_df["is_one_off"].iloc[0]


def test_status_missing_without_record(catalog_df):
    """A required training with no counted record is missing."""
    status_df = build_status_df(make_employees_df(), catalog_df, make_completions_df({}))
    assert status_of(status_df, "PRV-POM")["status"] == "missing"


@pytest.mark.parametrize(
    ("valid_until", "expected"),
    [
        ("2026-09-30", "expired"),
        ("2026-10-01", "expiring"),
        ("2026-12-30", "expiring"),
        ("2026-12-31", "valid"),
    ],
)
def test_status_boundaries(catalog_df, valid_until, expected):
    """Expired before the export date, expiring up to 90 days after it, valid later."""
    completions_df = make_completions_df({"platnost_do": pd.Timestamp(valid_until)})
    status_df = build_status_df(make_employees_df(), catalog_df, completions_df)
    assert status_of(status_df, "BOZP-Z")["status"] == expected


def test_status_uses_latest_record(catalog_df):
    """The latest completion decides, not an older one."""
    completions_df = make_completions_df(
        {
            "id_zaznamu": "Z1",
            "datum_absolvovani": pd.Timestamp("2022-01-01"),
            "platnost_do": pd.NaT,
        },
        {"id_zaznamu": "Z2"},
    )
    status_df = build_status_df(make_employees_df(), catalog_df, completions_df)
    assert status_of(status_df, "BOZP-Z")["id_zaznamu"] == "Z2"
    assert status_of(status_df, "BOZP-Z")["status"] == "valid"


def test_status_one_off_stays_valid(catalog_df):
    """A one-off training completed years ago is still valid."""
    completions_df = make_completions_df(
        {
            "kod_skoleni": "LEAD",
            "datum_absolvovani": pd.Timestamp("2019-02-22"),
            "platnost_do": pd.NaT,
        }
    )
    status_df = build_status_df(make_employees_df(pozice="Vedoucí"), catalog_df, completions_df)
    assert status_of(status_df, "LEAD")["status"] == "valid"


def test_status_future_record_reported_not_counted(catalog_df):
    """A record entered in advance leaves the training missing but shows its date."""
    completions_df = make_completions_df(
        {"datum_absolvovani": pd.Timestamp("2026-11-25"), "is_future": True}
    )
    status_df = build_status_df(make_employees_df(), catalog_df, completions_df)
    assert status_of(status_df, "BOZP-Z")["status"] == "missing"
    assert status_of(status_df, "BOZP-Z")["advance_record_date"] == pd.Timestamp("2026-11-25")
