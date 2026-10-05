import re

import pytest
from httpx import AsyncClient


UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-"
    r"[0-9a-fA-F]{12}$"
)


@pytest.mark.smoke
@pytest.mark.us01
@pytest.mark.asyncio
async def test_user_can_register(
    api_client: AsyncClient,
    registration_payload: dict,
):
    response = await api_client.post(
        "/api/auth/register",
        json=registration_payload,
    )

    assert response.status_code in (200, 201), response.text

    body = response.json()

    assert UUID_PATTERN.match(body["userId"])
    assert body["email"] == registration_payload["email"]
    assert body["firstName"] == registration_payload["firstName"]
    assert body["lastName"] == registration_payload["lastName"]

    assert body["accessToken"]
    assert body["refreshToken"]

    assert "password" not in body
    assert "passwordHash" not in body