from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, new_session_token, token_digest, verify_password
from app.models.auth import AuthSession, EmailVerificationCode, PasswordResetCode, User
from app.schemas.auth import (
    AuthRead,
    DeleteAccountRequest,
    EmailVerificationConfirmRequest,
    EmailVerificationRequest,
    LoginRequest,
    MessageRead,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    SessionRead,
    UserRead,
)
from app.services.account_data import (
    MigrationBundleError,
    delete_user_data,
    export_migration_bundle,
    export_user_data,
    import_migration_bundle,
)
from app.services.email import send_email_verification_code, send_password_reset_code

router = APIRouter(prefix="/auth", tags=["auth"])
SESSION_DAYS = 30
_DUMMY_PASSWORD_HASH = hash_password("studyos-dummy-auth-check")


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
    )


def _current_user(request: Request, db: Session) -> User:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found",
        )
    return user


def _issue_session(
    db: Session,
    user: User,
    request: Request,
    response: Response,
) -> AuthRead:
    token = new_session_token()
    expires_at = datetime.now(UTC) + timedelta(days=SESSION_DAYS)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_digest(token),
        expires_at=expires_at,
    )
    db.add(auth_session)
    db.commit()
    response.set_cookie(
        "studyos_session",
        token,
        httponly=True,
        secure=request.app.state.settings.environment == "production",
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )
    return AuthRead(user=_user_read(user), expires_at=expires_at)


def _create_email_verification_code(
    db: Session,
    user: User,
    request: Request,
) -> str:
    settings = request.app.state.settings
    now = datetime.now(UTC)
    active_codes = db.scalars(
        select(EmailVerificationCode).where(
            EmailVerificationCode.user_id == user.id,
            EmailVerificationCode.consumed_at.is_(None),
        )
    ).all()
    for existing in active_codes:
        existing.consumed_at = now

    code = f"{secrets.randbelow(1_000_000):06d}"
    verification = EmailVerificationCode(
        user_id=user.id,
        code_hash=token_digest(f"{user.id}:{code}"),
        expires_at=now + timedelta(minutes=settings.email_verification_code_minutes),
    )
    db.add(verification)
    db.commit()
    try:
        send_email_verification_code(settings, recipient=user.email, code=code)
    except Exception as exc:
        verification.consumed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification email could not be sent",
        ) from exc
    return code


@router.post(
    "/register",
    response_model=AuthRead | MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthRead | MessageRead:
    settings = request.app.state.settings
    if settings.require_email_verification and not settings.email_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account verification email is not configured",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_admin=payload.email in settings.admin_emails,
        email_verified_at=None if settings.require_email_verification else datetime.now(UTC),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc

    if settings.require_email_verification:
        _create_email_verification_code(db, user, request)
        return MessageRead(
            message="Account created. Enter the 6-digit code sent to your email."
        )

    return _issue_session(db, user, request, response)


@router.post("/email-verification/request", response_model=MessageRead)
def request_email_verification(
    payload: EmailVerificationRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> MessageRead:
    settings = request.app.state.settings
    if not settings.email_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account verification email is not configured",
        )

    user = db.scalar(select(User).where(User.email == payload.email))
    if user is not None and user.email_verified_at is None:
        _create_email_verification_code(db, user, request)

    return MessageRead(
        message="If that account still needs verification, a new code has been sent."
    )


@router.post("/email-verification/confirm", response_model=AuthRead)
def confirm_email_verification(
    payload: EmailVerificationConfirmRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthRead:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    now = datetime.now(UTC)
    verification = db.scalar(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.user_id == user.id,
            EmailVerificationCode.consumed_at.is_(None),
        )
        .order_by(EmailVerificationCode.created_at.desc())
    )
    if (
        verification is None
        or _utc(verification.expires_at) <= now
        or verification.attempts
        >= request.app.state.settings.email_verification_max_attempts
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    expected = token_digest(f"{user.id}:{payload.code}")
    if not secrets.compare_digest(verification.code_hash, expected):
        verification.attempts += 1
        if (
            verification.attempts
            >= request.app.state.settings.email_verification_max_attempts
        ):
            verification.consumed_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    verification.consumed_at = now
    user.email_verified_at = now
    db.commit()
    return _issue_session(db, user, request, response)


@router.post("/login", response_model=AuthRead)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthRead:
    user = db.scalar(select(User).where(User.email == payload.email))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, password_hash)
    if user is None or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if (
        request.app.state.settings.require_email_verification
        and user.email_verified_at is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    should_be_admin = user.email in request.app.state.settings.admin_emails
    if should_be_admin != user.is_admin:
        user.is_admin = should_be_admin
        db.commit()
        db.refresh(user)
    return _issue_session(db, user, request, response)


@router.post(
    "/password-reset/request",
    response_model=MessageRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> MessageRead:
    settings = request.app.state.settings
    if not settings.email_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset email is not configured",
        )

    user = db.scalar(select(User).where(User.email == payload.email))
    if user is not None:
        now = datetime.now(UTC)
        active_codes = db.scalars(
            select(PasswordResetCode).where(
                PasswordResetCode.user_id == user.id,
                PasswordResetCode.consumed_at.is_(None),
            )
        ).all()
        for existing in active_codes:
            existing.consumed_at = now

        code = f"{secrets.randbelow(1_000_000):06d}"
        reset = PasswordResetCode(
            user_id=user.id,
            code_hash=token_digest(f"{user.id}:{code}"),
            expires_at=now + timedelta(minutes=settings.password_reset_code_minutes),
        )
        db.add(reset)
        db.commit()
        try:
            send_password_reset_code(settings, recipient=user.email, code=code)
        except Exception as exc:
            reset.consumed_at = datetime.now(UTC)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password reset email could not be sent",
            ) from exc

    return MessageRead(
        message="If an account exists for that email, a verification code has been sent."
    )


@router.post("/password-reset/confirm", response_model=MessageRead)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> MessageRead:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    now = datetime.now(UTC)
    reset = db.scalar(
        select(PasswordResetCode)
        .where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.consumed_at.is_(None),
        )
        .order_by(PasswordResetCode.created_at.desc())
    )
    if (
        reset is None
        or _utc(reset.expires_at) <= now
        or reset.attempts >= request.app.state.settings.password_reset_max_attempts
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    expected = token_digest(f"{user.id}:{payload.code}")
    if not secrets.compare_digest(reset.code_hash, expected):
        reset.attempts += 1
        if reset.attempts >= request.app.state.settings.password_reset_max_attempts:
            reset.consumed_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user.password_hash = hash_password(payload.password)
    reset.consumed_at = now
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
    db.commit()
    return MessageRead(message="Password updated. You can now sign in with your new password.")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    token = request.cookies.get("studyos_session")
    if token:
        auth_session = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest(token))
        )
        if auth_session is not None:
            db.delete(auth_session)
            db.commit()
    response.delete_cookie("studyos_session", path="/")


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    user = _current_user(request, db)
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
    db.commit()
    response.delete_cookie("studyos_session", path="/")


@router.get("/sessions", response_model=list[SessionRead])
def sessions(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[SessionRead]:
    user = _current_user(request, db)
    current_session_id = getattr(request.state, "session_id", None)
    now = datetime.now(UTC)
    active = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.expires_at > now)
        .order_by(AuthSession.created_at.desc())
    ).all()
    return [
        SessionRead(
            id=item.id,
            created_at=item.created_at,
            expires_at=item.expires_at,
            current=item.id == current_session_id,
        )
        for item in active
    ]


@router.get("/me", response_model=UserRead)
def me(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> UserRead:
    return _user_read(_current_user(request, db))


@router.get("/migration-bundle")
def migration_bundle(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    user = _current_user(request, db)
    archive = export_migration_bundle(db, user)
    filename = f"studyos-migration-{datetime.now(UTC).date().isoformat()}.zip"
    return StreamingResponse(
        BytesIO(archive),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/migration-bundle/import")
def import_account_migration_bundle(
    request: Request,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    user = _current_user(request, db)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a StudyOS migration ZIP",
        )
    try:
        return import_migration_bundle(
            db,
            user,
            file.file,
            data_dir=Path(request.app.state.settings.data_dir),
        )
    except MigrationBundleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get("/export")
def export_account(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    user = _current_user(request, db)
    return export_user_data(db, user)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    user = _current_user(request, db)
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password confirmation failed",
        )
    delete_user_data(db, user)
    response.delete_cookie("studyos_session", path="/")
