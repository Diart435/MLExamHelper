import pytest
from httpx import AsyncClient


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_duplicate_email_returns_conflict(
    api_client: AsyncClient,
    registration_payload: dict,
):
    first_response = await api_client.post(
        "/api/auth/register",
        json=registration_payload,
    )

    assert first_response.status_code in (200, 201), (
        f"First registration failed: "
        f"status={first_response.status_code}; "
        f"body={first_response.text!r}"
    )

    second_response = await api_client.post(
        "/api/auth/register",
        json=registration_payload,
    )

    assert second_response.status_code == 409, second_response.text

    body = second_response.json()

    assert body["status"] == 409
    assert body["error"] == "Conflict"


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "password", "first_name", "last_name", "case_name"),
    [
        ("", "Strong123!", "Иван", "Иванов", "empty-email"),
        ("invalid-email", "Strong123!", "Иван", "Иванов", "invalid-email"),
        (
            "qa.user@example.test",
            "",
            "Иван",
            "Иванов",
            "empty-password",
        ),
        (
            "qa.user@example.test",
            "123",
            "Иван",
            "Иванов",
            "short-password",
        ),
        (
            "qa.user@example.test",
            "Strong123!",
            "",
            "Иванов",
            "empty-first-name",
        ),
        (
            "qa.user@example.test",
            "Strong123!",
            "Иван",
            "",
            "empty-last-name",
        ),
    ],
)
async def test_registration_validation(
    api_client: AsyncClient,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    case_name: str,
):
    response = await api_client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "firstName": first_name,
            "lastName": last_name,
        },
    )

    assert response.status_code in (400, 422), response.text

@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "case_name"),
    [
        ("qa.userexample.test", "email-without-at-symbol"),
        ("qa.user@", "email-without-domain"),
        ("@example.test", "email-without-local-part"),
    ],
)
async def test_registration_rejects_invalid_email_formats(
    api_client: AsyncClient,
    email: str,
    case_name: str,
):
    response = await api_client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Strong123!",
            "firstName": "Иван",
            "lastName": "Иванов",
        },
    )

    assert response.status_code in (400, 422), response.text


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_registration_does_not_return_password(
    api_client: AsyncClient,
    registration_payload: dict,
):
    response = await api_client.post(
        "/api/auth/register",
        json=registration_payload,
    )

    assert response.status_code in (200, 201), response.text

    body = response.json()

    assert "password" not in body
    assert "passwordHash" not in body