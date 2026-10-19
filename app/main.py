"""Web app: who needs to do which training, and who to book into which term."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_404_NOT_FOUND

from app.constants import (
    CLEAN_DIR,
    EXPIRING_DAYS,
    EXPORT_DATE,
    STATE_LABELS,
    STATIC_DIR,
    TEMPLATES_DIR,
)
from app.data import load_clean_tables
from app.pages import (
    build_people,
    build_register,
    build_summary,
    count_by_state,
    filter_rows,
    find_employee,
    find_term,
    format_date,
    pick_plural,
)

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


templates.env.filters["date"] = format_date
templates.env.filters["plural"] = pick_plural
templates.env.globals["export_date"] = EXPORT_DATE
templates.env.globals["expiring_limit"] = EXPORT_DATE + pd.Timedelta(days=EXPIRING_DAYS)
templates.env.globals["state_labels"] = STATE_LABELS


@router.get("/", response_class=HTMLResponse)
def show_people(
    request: Request,
    training: str = "",
    department: str = "",
    state: str = "",
    q: str = "",
) -> HTMLResponse:
    """Show who needs to do what, the most urgent employee first."""
    register = request.app.state.register
    rows_df = register.rows_df
    shown_rows_df = filter_rows(
        rows_df,
        training=training,
        department=department,
        state=state,
        query=q.strip(),
    )
    context = {
        "summary": build_summary(register),
        "people": build_people(shown_rows_df),
        "training": training,
        "department": department,
        "state": state,
        "q": q,
        "is_filtered": bool(training or department or state or q),
        "trainings": sorted(rows_df["kod_skoleni"].unique()),
        "departments": sorted(rows_df["department"].unique()),
        "by_training": count_by_state(rows_df, ["kod_skoleni", "nazev"]),
        "by_department": count_by_state(rows_df, ["department"]),
    }
    return templates.TemplateResponse(request, "people.html", context)


@router.get("/employees/{employee_id}", response_class=HTMLResponse)
def show_employee(request: Request, employee_id: str) -> HTMLResponse:
    """Show all required trainings of one employee."""
    register = request.app.state.register
    employee = find_employee(register, employee_id)
    if employee is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Employee not found")
    is_employee = register.rows_df["id_zamestnance"] == employee_id
    context = {"employee": employee, "rows": register.rows_df[is_employee]}
    return templates.TemplateResponse(request, "employee.html", context)


@router.get("/terms", response_class=HTMLResponse)
def show_terms(request: Request) -> HTMLResponse:
    """List the upcoming terms with free seats."""
    register = request.app.state.register
    rows_df = register.rows_df
    capacity_df = register.capacity_df
    context = {
        "terms": register.terms_df.to_dict("records"),
        "late_trainings": capacity_df[~capacity_df["fits_first_term"]],
        "fitting_trainings": capacity_df[capacity_df["fits_first_term"]],
        "without_seat": rows_df[rows_df["unassigned_reason"] != ""],
    }
    return templates.TemplateResponse(request, "terms.html", context)


@router.get("/terms/{term_id}", response_class=HTMLResponse)
def show_term(request: Request, term_id: str) -> HTMLResponse:
    """Show one term and the employees to sign up for it."""
    term = find_term(request.app.state.register, term_id)
    if term is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Term not found")
    return templates.TemplateResponse(request, "term.html", {"term": term})


def create_app(clean_dir: Path = CLEAN_DIR) -> FastAPI:
    """Build the app; the data is loaded and computed once at startup.

    Args:
        clean_dir: Directory with the cleaned CSV files.

    Returns:
        The app.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tables = load_clean_tables(clean_dir)
        app.state.register = build_register(tables)
        yield

    app = FastAPI(
        title="Evidence školení",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    return app


app = create_app()
