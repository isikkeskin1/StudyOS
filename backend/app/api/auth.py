from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, new_session_token, token_digest, verify_password
from app.models.auth import AuthSession, User
from app.schemas.auth import (
    AuthRead,
    DeleteAccountRequest,
    LoginRequest,
    RegisterRequest,
    UserRead,
)
from app.services.account_data import delete_user_data, export_user_data

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
