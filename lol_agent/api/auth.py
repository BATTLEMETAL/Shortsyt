"""
Shortsyt API — autentykacja JWT
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import API_PASSWORD, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_HOURS

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Wygeneruj JWT token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=JWT_EXPIRE_HOURS))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_password(password: str) -> bool:
    """Sprawdź hasło."""
    return password == API_PASSWORD


def _decode_token(raw_token: str) -> dict:
    """Zdekoduj i zweryfikuj JWT. Rzuca HTTPException przy błędzie."""
    try:
        return jwt.decode(raw_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token wygasł — zaloguj się ponownie",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy token",
        )


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Zweryfikuj JWT token z nagłówka Authorization: Bearer <token>."""
    return _decode_token(credentials.credentials)


def verify_token_flexible(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    token: Optional[str] = Query(None, description="JWT token (wymagane przez expo-av zamiast Bearer header)"),
) -> dict:
    """Zweryfikuj JWT z nagłówka Bearer LUB query param ?token=.

    expo-av nie obsługuje nagłówka Authorization przy streamowaniu video —
    używa query param: /outputs/file.mp4?token=<jwt>
    """
    raw_token = None
    if credentials:
        raw_token = credentials.credentials
    elif token:
        raw_token = token

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token wymagany (Bearer header lub ?token= query param)",
        )
    return _decode_token(raw_token)
