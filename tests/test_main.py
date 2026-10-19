import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.mark.parametrize("url", ["/", "/terms", "/terms/T001", "/employees/E1"])
def test_page_renders(client: TestClient, url: str):
    """Every page renders."""
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.parametrize("employee_id", ["E9", "E3"])
def test_employee_unknown_or_left_not_found(client: TestClient, employee_id: str):
    """Unknown employees and employees who left have no page."""
    response = client.get(f"/employees/{employee_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_people_lists_only_employees_with_a_to_do(client: TestClient):
    """The employee with a missing training is listed; the one with all trainings valid is not."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert "/employees/E2" in response.text
    assert "/employees/E1" not in response.text
    assert "BOZP-Z: neplatné" in response.text
    assert 'přihlásit na <a href="/terms/T001">T001</a> (1. 11. 2026, 09:00-12:00)' in response.text


def test_people_filters_by_department(client: TestClient):
    """The department filter matches the unknown-department label too."""
    response = client.get("/", params={"department": "Knihovna"})
    assert response.status_code == status.HTTP_200_OK
    assert "/employees/E2" not in response.text
    assert "Nikdo neodpovídá filtrům." in response.text


def test_people_search_by_name(client: TestClient):
    """The name search finds the employee regardless of case."""
    response = client.get("/", params={"q": "malý"})
    assert response.status_code == status.HTTP_200_OK
    assert "/employees/E2" in response.text
    assert "Zobrazeno: 1," in response.text


def test_terms_list_links_to_term(client: TestClient):
    """The term list links each term to its detail page."""
    response = client.get("/terms")
    assert response.status_code == status.HTTP_200_OK
    assert 'href="/terms/T001"' in response.text


def test_term_lists_employees_to_sign_up(client: TestClient):
    """The term page lists the employee with a missing training."""
    response = client.get("/terms/T001")
    assert response.status_code == status.HTTP_200_OK
    assert "/employees/E2" in response.text
    assert "/employees/E1" not in response.text


def test_no_late_tile_when_no_training_expires_before_its_term(client: TestClient):
    """Without bookings after expiry the people page has no tile about them."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert "před svým termínem bez platného školení" not in response.text


def test_terms_say_when_everyone_fits_the_first_term(client: TestClient):
    """One person needing BOZP fits the first term, so nothing needs solving."""
    response = client.get("/terms")
    assert response.status_code == status.HTTP_200_OK
    assert "Co je potřeba řešit" not in response.text
    assert "1 člověk se vejde" in response.text


def test_term_unknown_not_found(client: TestClient):
    """An unknown term has no page."""
    response = client.get("/terms/T999")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_employee_links_booked_term(client: TestClient):
    """The person page links the proposed term to its detail page."""
    response = client.get("/employees/E2")
    assert response.status_code == status.HTTP_200_OK
    assert '<a href="/terms/T001">T001</a>' in response.text


def test_names_are_escaped(client: TestClient):
    """Names are rendered as text, not as HTML."""
    response = client.get("/employees/E1")
    assert "&lt;b&gt;Eva&lt;/b&gt;" in response.text
    assert "<b>Eva</b>" not in response.text


@pytest.mark.parametrize("url", ["/", "/terms", "/terms/T001", "/employees/E1"])
def test_pages_hide_emails_and_notes(client: TestClient, url: str):
    """No page shows emails or the free-text employee notes."""
    response = client.get(url)
    assert "eva.nova@example.test" not in response.text
    assert "HYPERLINK" not in response.text
