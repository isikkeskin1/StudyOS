from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.services.email import send_email_verification_code, send_password_reset_code


class FakeResponse:
    is_error = False
    status_code = 201

    def raise_for_status(self) -> None:
        pass


class FakeClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse()


def settings() -> Settings:
    return Settings(
        brevo_api_key="placeholder",
        smtp_from_email="support@studyos.courses",
    )


def test_verification_email_uses_brevo_https(monkeypatch) -> None:
    FakeClient.calls.clear()
    monkeypatch.setattr("app.services.email.httpx.Client", FakeClient)

    send_email_verification_code(
        settings(),
        recipient="student@example.com",
        code="123456",
    )

    call = FakeClient.calls[0]
    assert call["url"].endswith("/v3/smtp/email")
    assert call["json"]["sender"]["email"] == "support@studyos.courses"
    assert call["json"]["to"] == [{"email": "student@example.com"}]
    assert "123456" in call["json"]["subject"]
    assert "123456" in call["json"]["textContent"]


def test_password_reset_email_uses_brevo_https(monkeypatch) -> None:
    FakeClient.calls.clear()
    monkeypatch.setattr("app.services.email.httpx.Client", FakeClient)

    send_password_reset_code(
        settings(),
        recipient="student@example.com",
        code="654321",
    )

    call = FakeClient.calls[0]
    assert "password reset" in call["json"]["subject"].lower()
    assert "654321" in call["json"]["textContent"]
