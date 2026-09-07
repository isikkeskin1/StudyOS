from __future__ import annotations

import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import Settings

_BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def _send_via_brevo_api(settings: Settings, message: EmailMessage) -> None:
    if not settings.brevo_api_enabled or settings.brevo_api_key is None:
        raise RuntimeError("Brevo API email is not configured")

    recipient = message["To"]
    subject = message["Subject"]
    sender = settings.smtp_from_email
    if not recipient or not subject or not sender:
        raise RuntimeError("Email message is missing sender, recipient, or subject")

    text_content = message.get_body(preferencelist=("plain",))
    payload = {
        "sender": {"name": "StudyOS", "email": sender},
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": text_content.get_content() if text_content is not None else "",
    }
    headers = {
        "accept": "application/json",
        "api-key": settings.brevo_api_key.get_secret_value(),
        "content-type": "application/json",
    }

    with httpx.Client(timeout=10.0) as client:
        response = client.post(_BREVO_SEND_URL, headers=headers, json=payload)
        response.raise_for_status()


def _send_via_smtp(settings: Settings, message: EmailMessage) -> None:
    if not settings.smtp_enabled:
        raise RuntimeError("SMTP email is not configured")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(
                settings.smtp_username,
                settings.smtp_password.get_secret_value() if settings.smtp_password else "",
            )
        client.send_message(message)


def _send_message(settings: Settings, message: EmailMessage) -> None:
    if settings.brevo_api_enabled:
        _send_via_brevo_api(settings, message)
        return
    if settings.smtp_enabled:
        _send_via_smtp(settings, message)
        return
    raise RuntimeError("StudyOS email is not configured")


def send_email_verification_code(settings: Settings, *, recipient: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"{code} is your StudyOS verification code"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        "Verify your StudyOS account\n\n"
        f"Your verification code is: {code}\n\n"
        f"This code expires in {settings.email_verification_code_minutes} minutes. "
        "If you did not create a StudyOS account, you can ignore this email."
    )
    _send_message(settings, message)


def send_password_reset_code(settings: Settings, *, recipient: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"{code} is your StudyOS password reset code"
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message.set_content(
        "Reset your StudyOS password\n\n"
        f"Your verification code is: {code}\n\n"
        f"This code expires in {settings.password_reset_code_minutes} minutes. "
        "If you did not request a password reset, you can ignore this email."
    )
    _send_message(settings, message)
