import pytest
from httpx import AsyncClient


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_unauthorized(
    api_client: AsyncClient,
    registered_user: dict,
):
    payload = registered_user["payload"]

    response = await api_client.post(
        "/api/auth/login",
        json={
            "email": payload["email"],
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401, response.text

    body = response.json()

    assert body["status"] == 401
    assert body["error"] == "Unauthorized"


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_login_with_unknown_email_returns_unauthorized(
    api_client: AsyncClient,
    settings,
):
    response = await api_client.post(
        "/api/auth/login",
        json={
            "email": "unknown.user@example.test",
            "password": settings["password"],
        },
    )

    assert response.status_code == 401, response.text

    body = response.json()

    assert body["status"] == 401
    assert body["error"] == "Unauthorized"


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_refresh_token_returns_new_access_token(
    api_client: AsyncClient,
    registered_user: dict,
):
    payload = registered_user["payload"]

    login_response = await api_client.post(
        "/api/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )

    assert login_response.status_code == 200, login_response.text

    refresh_token = api_client.cookies.get("refresh_token")

    assert refresh_token, "refresh_token cookie was not set after login"

    refresh_response = await api_client.post(
        "/api/auth/refresh",
        headers={
            "Cookie": f"refresh_token={refresh_token}",
        },
    )

    assert refresh_response.status_code == 200, refresh_response.text

    body = refresh_response.json()

    assert body["accessToken"]
    assert isinstance(body["accessToken"], str)


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_refresh_with_invalid_token_returns_error(
    api_client: AsyncClient,
):
    response = await api_client.post(
        "/api/auth/refresh",
        headers={
            "Cookie": "refresh_token=invalid-refresh-token",
        },
    )

    assert response.status_code in (400, 401), response.text


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_refresh_without_token_returns_error(
    api_client: AsyncClient,
):
    api_client.cookies.clear()

    response = await api_client.post("/api/auth/refresh")

    assert response.status_code in (400, 401), response.text


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "password", "case_name"),
    [
        ("", "Strong123!", "empty-email"),
        ("invalid-email", "Strong123!", "invalid-email"),
        ("qa.user@example.test", "", "empty-password"),
    ],
)
async def test_login_validation(
    api_client: AsyncClient,
    email: str,
    password: str,
    case_name: str,
):
    response = await api_client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code in (400, 422), response.text