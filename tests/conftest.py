import os
import time
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio


BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT = float(os.getenv("API_REQUEST_TIMEOUT", "30"))
DEFAULT_PASSWORD = os.getenv("API_TEST_PASSWORD", "Strong123!")


@pytest.fixture(scope="session")
def settings() -> dict:
    return {
        "api_base_url": BASE_URL,
        "request_timeout": REQUEST_TIMEOUT,
        "password": DEFAULT_PASSWORD,
    }


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=REQUEST_TIMEOUT,
    ) as client:
        yield client


@pytest.fixture
def registration_payload(settings: dict) -> dict:
    timestamp = int(time.time() * 1000)

    return {
        "email": f"qa.user.{timestamp}@example.test",
        "password": settings["password"],
        "firstName": "Иван",
        "lastName": "Иванов",
    }


@pytest_asyncio.fixture
async def registered_user(
    api_client: httpx.AsyncClient,
    registration_payload: dict,
) -> dict:
    response = await api_client.post(
        "/api/auth/register",
        json=registration_payload,
    )

    assert response.status_code in (200, 201), (
        f"Registration failed: "
        f"status={response.status_code}; "
        f"body={response.text!r}"
    )

    body = response.json()

    assert_auth_response(body)

    return {
        "payload": registration_payload,
        "response": body,
    }


def assert_auth_response(body: dict) -> None:
    required_fields = {
        "userId",
        "email",
        "firstName",
        "lastName",
        "accessToken",
    }

    missing = required_fields - body.keys()

    assert not missing, (
        f"Missing AuthResponse fields: {missing}"
    )

    assert body["userId"]
    assert body["email"]
    assert body["accessToken"]

    assert isinstance(body["userId"], str)
    assert isinstance(body["email"], str)
    assert isinstance(body["accessToken"], str)

    assert "password" not in body
    assert "passwordHash" not in body
    assert "refreshToken" not in body