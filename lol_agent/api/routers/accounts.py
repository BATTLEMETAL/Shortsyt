"""
Shortsyt / Flikcut API — Router: Multi-Account Profiles & Content Guidelines
Obsługuje dodawanie kont (np. konta poboczne YT Sandbox, klienci, reklamy produktów, salony),
wytyczne kontentu oraz szybkie przełączanie aktywnego profilu.
"""
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import verify_token_flexible

router = APIRouter(tags=["Accounts"])


class AccountUpsertRequest(BaseModel):
    account_id: Optional[str] = None
    display_name: str
    handle: Optional[str] = ""
    content_mode: str = "PRODUCT_ECOMMERCE_AD"
    game_type: Optional[str] = None
    language: Optional[str] = "pl"
    peak_hours_cet: Optional[Union[List[str], str]] = None
    target_duration_range: Optional[List[float]] = None
    camera_mode: Optional[str] = None
    brand_voice: Optional[str] = ""
    value_proposition: Optional[str] = ""
    cta_text: Optional[str] = ""
    cta_url: Optional[str] = ""
    location: Optional[str] = ""
    phone: Optional[str] = ""
    mandatory_hashtags: Optional[Union[List[str], str]] = None
    forbidden_words: Optional[Union[List[str], str]] = None
    target_audience: Optional[str] = ""
    yt_category_id: Optional[str] = None
    yt_token_file: Optional[str] = None
    set_active: bool = True


def _clear_account_caches() -> None:
    try:
        from ..youtube_uploader import invalidate_publish_cache
        invalidate_publish_cache()
    except Exception:
        pass
    try:
        from ..youtube_analytics import invalidate_analytics_cache
        invalidate_analytics_cache()
    except Exception:
        pass


@router.get("/accounts")
def get_accounts_endpoint(payload: dict = Depends(verify_token_flexible)):
    """Pobiera listę kont, aktywny profil oraz presety wytycznych kontentu."""
    try:
        try:
            from lol_agent.account_manager import list_accounts
        except ImportError:
            from account_manager import list_accounts
        return list_accounts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu kont: {e}")


@router.post("/accounts")
def upsert_account_endpoint(req: AccountUpsertRequest, payload: dict = Depends(verify_token_flexible)):
    """Dodaje nowe konto z wytycznymi kontentu lub aktualizuje istniejące."""
    try:
        try:
            from lol_agent.account_manager import upsert_account
        except ImportError:
            from account_manager import upsert_account
        acc = upsert_account(req.model_dump())
        if req.set_active:
            _clear_account_caches()
        return {"ok": True, "account": acc}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Błąd zapisu konta: {e}")


@router.post("/accounts/select/{account_id}")
def select_account_endpoint(account_id: str, payload: dict = Depends(verify_token_flexible)):
    """Przełącza aktywne konto i czyści pamięć podręczną YouTube."""
    try:
        try:
            from lol_agent.account_manager import set_active_account
        except ImportError:
            from account_manager import set_active_account
        acc = set_active_account(account_id)
        _clear_account_caches()
        return {"ok": True, "active_account": acc}
    except KeyError as ke:
        raise HTTPException(status_code=404, detail=str(ke))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Błąd przełączania konta: {e}")


@router.delete("/accounts/{account_id}")
def delete_account_endpoint(account_id: str, payload: dict = Depends(verify_token_flexible)):
    """Usuwa niestandardowy profil konta."""
    try:
        try:
            from lol_agent.account_manager import delete_account
        except ImportError:
            from account_manager import delete_account
        ok = delete_account(account_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Konto '{account_id}' nie istnieje")
        _clear_account_caches()
        return {"ok": True, "deleted": account_id}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd usuwania konta: {e}")
