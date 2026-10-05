import os
import time
from dataclasses import dataclass

import pytest
from dotenv import load_dotenv
from httpx import AsyncClient, Timeout


load_dotenv("tests/.env.test")


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    request_timeout: int
    password: str


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        api_base_url=os.getenv(
            "QA_API_BASE_URL",
            "http://localhost:8000",
        ),
        request_timeout=int(
            os.getenv("QA_REQUEST_TIMEOUT", "30")
        ),
        password=os.getenv(
            "QA_TEST_PASSWORD",
            "Strong123!",
        ),
    )


@pytest.fixture
async def api_client(settings: Settings):
    async with AsyncClient(
        base_url=settings.api_base_url,
        timeout=Timeout(settings.request_timeout),
    ) as client:
        yield client


@pytest.fixture
def unique_email() -> str:
    timestamp = int(time.time() * 1000)
    return f"qa.user.{timestamp}@example.test"


@pytest.fixture
def registration_payload(
    unique_email: str,
    settings: Settings,
) -> dict:
    return {
        "email": unique_email,
        "password": settings.password,
        "firstName": "Иван",
        "lastName": "Иванов",
    }


def assert_auth_response(body: dict) -> None:
    required_fields = {
        "userId",
        "email",
        "firstName",
        "lastName",
        "accessToken",
        "refreshToken",
    }

    missing = required_fields - body.keys()

    assert not missing, (
        f"Missing AuthResponse fields: {missing}"
    )

    assert body["userId"]
    assert body["email"]
    assert body["firstName"]
    assert body["lastName"]
    assert body["accessToken"]
    assert body["refreshToken"]

    assert "password" not in body
    assert "passwordHash" not in body


@pytest.fixture
async def registered_user(
    api_client: AsyncClient,
    registration_payload: dict,
):
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


@pytest.fixture
async def logged_in_user(
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
        f"Login failed: "
        f"status={response.status_code}; "
        f"body={response.text!r}"
    )

    body = response.json()
    assert_auth_response(body)

    return body


@pytest.fixture
def auth_headers(logged_in_user: dict) -> dict:
    return {
        "Authorization": (
            f"Bearer {logged_in_user['accessToken']}"
        )
    }