import pytest
from httpx import AsyncClient


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_duplicate_email_returns_bad_request(
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

    assert second_response.status_code == 400, second_response.text

    body = second_response.json()

    assert body["message"] == "Email already registered"


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("email", ""),
        ("email", "invalid-email"),
        ("password", ""),
        ("password", "1234567"),
        ("firstName", ""),
        ("lastName", ""),
    ],
)
async def test_registration_validation(
    api_client: AsyncClient,
    registration_payload: dict,
    field: str,
    value: str,
):
    payload = {
        **registration_payload,
        field: value,
    }

    response = await api_client.post(
        "/api/auth/register",
        json=payload,
    )

    assert response.status_code in (400, 422), (
        f"Validation failed: "
        f"field={field}; value={value!r}; "
        f"status={response.status_code}; "
        f"body={response.text!r}"
    )