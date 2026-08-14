from fastapi import HTTPException, status
from typing import Optional
from contextvars import ContextVar, Token
import os

_REQUEST_API_KEY: ContextVar[Optional[str]] = ContextVar("request_api_key", default=None)


def set_request_api_key(value: Optional[str]) -> Token:
    return _REQUEST_API_KEY.set(value)


def reset_request_api_key(token: Token) -> None:
    _REQUEST_API_KEY.reset(token)


def _is_auth_required() -> bool:
    env = os.getenv("NTS_ENV", "development").lower()
    return env in {"prod", "production"}


def verify_bearer_token(authorization: Optional[str] = None) -> str:
    """
    Verify Bearer token authentication.
    Returns the token if valid, raises 401 otherwise.
    """
    api_key = os.getenv("NTS_API_KEY", "")
    if not _is_auth_required():
        return ""

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured"
        )
    
    if not authorization:
        token = _REQUEST_API_KEY.get()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        parts = authorization.split()
        if len(parts) == 1:
            token = parts[0]
        elif len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )

    if token != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token
