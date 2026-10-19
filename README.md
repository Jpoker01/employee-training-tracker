# Employee Training Register

A web app for HR that shows which employees miss a mandatory training, whose training expires soon, and whom to sign up for which upcoming term.
It reads an HR data export (employees, training catalog, completed trainings, planned terms), cleans it once in a notebook and serves the results as a few read-only pages in Czech.

**Built as a technical assignment**

## Tech Stack

- **Language:** Python 3.11+ (developed on 3.14)
- **Web:** FastAPI with server-rendered Jinja2 templates, no JavaScript framework
- **Data:** pandas; the cleaned tables are plain CSV files, no database
- **Analysis and cleaning:** Jupyter notebooks
- **Tests and linting:** pytest, ruff

## How it works

1. **Cleaning (`notebooks/01_cleaning_ntb.ipynb`):** reads the four raw exports, fixes what can be fixed safely (date formats, code variants, department spellings, duplicate people and records) and flags what cannot. It saves only the columns the app needs to `data/clean/`. Personal identification numbers and free-text notes never leave the notebook.
2. **Compliance (`app/compliance.py`):** works out which trainings each employee needs (for everyone, by department or by position) and whether each one is valid, expiring within 90 days, expired or missing.
3. **Scheduling (`app/scheduling.py`):** gives each employee who needs a training a seat in the earliest usable term. The most urgent go first: missing, then the oldest expiry. Trainings that cannot get a seat are reported as a capacity shortfall.
4. **App (`app/main.py`):** computes everything once at startup and serves it.
    * **Zaměstnanci (`/`)** - employees with something to do, most urgent first, filterable by training, department, state and name.
    * **Detail of an employee (`/employees/<id>`)** - all required trainings, the proposed term, the employee's and manager's email.
    * **Termíny (`/terms`)** - upcoming terms with free and proposed seats, plus warnings about overbooked terms and trainings without enough seats.
    * **Detail of a term (`/terms/<id>`)** - whom to sign up, most urgent first, with their emails.

## Decisions and assumptions

The data had many inconsistencies. Each one is listed with how it was handled in the insights table at the top of the cleaning notebook. The main rules:

- **Snapshot of the export:** all statuses are computed for the export date, 1. 10. 2026, not for today. With a new export, change `EXPORT_DATE` in `app/constants.py`.
- **Safe over sorry:** when the data is unclear, a training counts as not done. Records with an unknown training code, a name that does not match the employee, a placeholder date or a date after the export never count.
- **Expiry:** the earlier of the record's `platnost_do` and completion date + catalog validity. LEAD (validity `0`) is a one-off training that never expires.
- **Scope:** employees who left are excluded. People on parental leave are shown but not scheduled. Employees leaving soon are scheduled only into terms before their last day.
- **Usable term:** after the export date, not cancelled, with a known code and at least one free seat. Overbooked terms are reported, never booked into.
- **Contacts:** the app shows employee and manager emails so HR can contact people. Malformed emails and the placeholder manager email are removed. The app has no login, so it must only be deployed where access is restricted.

## Quickstart guide

### Prerequisites
- Python 3.11 or newer
- Git

### Setup

```bash
git clone https://github.com/Jpoker01/employee-training-tracker.git
cd employee-training-tracker
pip install -e ".[dev]"
```

### Data preparation

**The data is not included in this repository, as it contains personal data.**
Place the four raw exports into `data/raw/` (`absolvovana_skoleni.csv`, `katalog_skoleni.csv`, `terminy_skoleni.csv`, `zamestnanci.csv`) and run the cleaning notebook, which writes `data/clean/`:

```bash
cd notebooks
jupyter nbconvert --to notebook --execute --inplace 01_cleaning_ntb.ipynb
cd ..
```

### Running the application

```bash
uvicorn app.main:app --reload
```

Navigate to `http://localhost:8000`. To read the cleaned tables from another directory (e.g. secret files on a hosting service), set the `CLEAN_DIR` environment variable.

### Running tests

The tests run on small synthetic tables and do not need the real data:

```bash
pytest
```

## Project structure

* **pyproject.toml** - Dependencies and package configuration for `pip install -e .`
* **/data** - Raw exports and cleaned tables - **not included in git**
* **/notebooks** - Jupyter notebooks
  * **00_exploratory_ntb.ipynb** - Exploratory analysis of the raw exports
  * **01_cleaning_ntb.ipynb** - Insights, cleaning and saving the cleaned tables
* **/app** - The web application
  * **main.py** - FastAPI app and page routes
  * **constants.py** - Paths, export date and shared constants
  * **data.py** - Loading the cleaned tables
  * **compliance.py** - Required trainings and their status
  * **scheduling.py** - Usable terms and assigning seats
  * **pages.py** - Shaping the results for the pages
  * **/templates**, **/static** - Jinja2 templates and the stylesheet
* **/tests** - pytest tests for compliance, scheduling, page logic and routes
