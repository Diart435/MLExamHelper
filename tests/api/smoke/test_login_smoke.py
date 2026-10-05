import pytest
from httpx import AsyncClient


@pytest.mark.smoke
@pytest.mark.us01
@pytest.mark.asyncio
async def test_user_can_login(
    api_client: AsyncClient,
    registered_user: dict,
):
    payload = registered_user["payload"]

    response = await api_client.post(
        "/api/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )

    assert response.status_code == 200, (
        f"status={response.status_code}; "
        f"headers={dict(response.headers)}; "
        f"body={response.text!r}"
    )

    body = response.json()

    assert body["userId"]
    assert body["email"] == payload["email"]
    assert body["firstName"] == payload["firstName"]
    assert body["lastName"] == payload["lastName"]

    assert body["accessToken"]
    assert body["refreshToken"]