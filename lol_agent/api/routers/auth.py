"""
Shortsyt API — Router: Authentication
"""
from fastapi import APIRouter, Depends, HTTPException, status
from ..auth import create_access_token, verify_password, verify_token
from ..models import LoginRequest, LoginResponse

router = APIRouter(tags=["Auth"])


@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Zaloguj się hasłem i otrzymaj JWT token."""
    if not verify_password(req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowe hasło",
        )
    token = create_access_token({"sub": "user"})
    return LoginResponse(access_token=token)


@router.get("/auth/me")
def me(payload: dict = Depends(verify_token)):
    """Sprawdź czy token jest ważny."""
    return {"status": "ok", "user": payload.get("sub")}
