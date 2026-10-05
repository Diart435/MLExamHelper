import pytest
from httpx import AsyncClient


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_bad_request(
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

    assert response.status_code == 400, response.text


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_login_with_unknown_email_returns_bad_request(
    api_client: AsyncClient,
    settings,
):
    response = await api_client.post(
        "/api/auth/login",
        json={
            "email": "unknown.user@example.test",
            "password": settings.password,
        },
    )

    assert response.status_code == 400, response.text


@pytest.mark.regression
@pytest.mark.us01
@pytest.mark.asyncio
async def test_refresh_token_returns_new_auth_response(
    api_client: AsyncClient,
    registered_user: dict,
):
    registration_response = registered_user["response"]

    response = await api_client.post(
        "/api/auth/refresh",
        json={
            "refreshToken": registration_response["refreshToken"],
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["accessToken"]
    assert body["refreshToken"]