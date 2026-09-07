from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import Settings


def send_password_reset_code(settings: Settings, *, recipient: str, code: str) -> None:
    if not settings.smtp_enabled:
        raise RuntimeError("Password reset email is not configured")

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

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(
                settings.smtp_username,
                settings.smtp_password.get_secret_value() if settings.smtp_password else "",
            )
        client.send_message(message)
