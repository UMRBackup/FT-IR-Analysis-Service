from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from .config import settings
from .state import AuthKeyRecord, UserRecord, store


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class TokenClaims:
    user_id: int
    username: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(*, user: UserRecord) -> str:
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expires_delta
    key_record = store.get_auth_keys()
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": expire_at,
    }
    return jwt.encode(
        payload,
        key_record.current_secret_key,
        algorithm=settings.jwt_algorithm,
        headers={"kid": key_record.current_kid},
    )


def get_auth_key_info() -> AuthKeyRecord:
    return store.get_auth_keys()


def rotate_auth_key(*, new_secret_key: str, new_kid: str | None = None) -> AuthKeyRecord:
    return store.rotate_auth_keys(new_secret_key=new_secret_key, new_kid=new_kid)


def decode_access_token(token: str) -> TokenClaims:
    key_record = store.get_auth_keys()

    header_kid = ""
    try:
        unverified_header = jwt.get_unverified_header(token)
        header_kid = str(unverified_header.get("kid", ""))
    except jwt.PyJWTError:
        header_kid = ""

    candidates: list[str] = []
    if header_kid and header_kid == key_record.current_kid:
        candidates.append(key_record.current_secret_key)
        if key_record.previous_secret_key:
            candidates.append(key_record.previous_secret_key)
    elif header_kid and key_record.previous_kid and header_kid == key_record.previous_kid:
        if key_record.previous_secret_key:
            candidates.append(key_record.previous_secret_key)
        candidates.append(key_record.current_secret_key)
    else:
        candidates.append(key_record.current_secret_key)
        if key_record.previous_secret_key:
            candidates.append(key_record.previous_secret_key)

    seen: set[str] = set()
    unique_candidates: list[str] = []
    for secret in candidates:
        if secret and secret not in seen:
            unique_candidates.append(secret)
            seen.add(secret)

    last_error: Exception | None = None
    try:
        for secret in unique_candidates:
            try:
                payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
                sub = payload.get("sub")
                username = payload.get("username")
                if sub is None or username is None:
                    raise ValueError("Invalid token payload")
                return TokenClaims(user_id=int(sub), username=str(username))
            except (ValueError, jwt.PyJWTError) as exc:
                last_error = exc
                continue
    except Exception as exc:
        last_error = exc

    if last_error is None:
        last_error = ValueError("Token decode failed")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    ) from last_error


def get_user_from_token(token: str) -> UserRecord:
    claims = decode_access_token(token)
    user = store.get_user_by_id(claims.user_id)
    if not user or user.username != claims.username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user in token",
        )
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserRecord:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return get_user_from_token(credentials.credentials)
