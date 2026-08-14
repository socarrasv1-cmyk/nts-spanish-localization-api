from fastapi import HTTPException, status
from typing import Optional
import os


def _is_auth_required(api_key: str) -> bool:
    env = os.getenv("NTS_ENV", "development").lower()
    return env in {"prod", "production"} or bool(api_key)


def verify_bearer_token(authorization: Optional[str] = None) -> str:
    """
    Verify Bearer token authentication.
    Returns the token if valid, raises 401 otherwise.
    """
    api_key = os.getenv("NTS_API_KEY", "")
    if not _is_auth_required(api_key):
        return ""

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured"
        )
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = parts[1]
    if token != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token
