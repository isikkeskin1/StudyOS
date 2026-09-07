from __future__ import annotations

from datetime import UTC, datetime, timedelta
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, new_session_token, token_digest, verify_password
from app.models.auth import AuthSession, PasswordResetCode, User
from app.schemas.auth import (
    AuthRead,
    DeleteAccountRequest,
    LoginRequest,
    MessageRead,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    UserRead,
)
from app.services.account_data import delete_user_data, export_user_data
from app.services.email import send_password_reset_code

router = APIRouter(prefix="/auth", tags=["auth"])
SESSION_DAYS = 30
_DUMMY_PASSWORD_HASH = hash_password("studyos-dummy-auth-check")


def _user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        is_admin=user.is_admin,
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


@router.post("/register", response_model=AuthRead, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthRead:
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_admin=payload.email in request.app.state.settings.admin_emails,
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
    should_be_admin = user.email in request.app.state.settings.admin_emails
    if should_be_admin != user.is_admin:
        user.is_admin = should_be_admin
        db.commit()
        db.refresh(user)
    return _issue_session(db, user, request, response)


@router.post("/password-reset/request", response_model=MessageRead, status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> MessageRead:
    settings = request.app.state.settings
    if not settings.smtp_enabled:
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
        or reset.expires_at <= now
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


@router.get("/me", response_model=UserRead)
def me(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> UserRead:
    return _user_read(_current_user(request, db))


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
