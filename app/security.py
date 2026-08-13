from fastapi import HTTPException, Header, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
import os
import hmac


bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="bearerAuth",
    description="Socarrasv1 Blueprint V3 bearer token.",
)


def _verify_token(token: Optional[str]) -> str:
    api_key = os.getenv("NTS_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured",
        )
    if not token or not hmac.compare_digest(token, api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token" if token else "Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def verify_v3_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> str:
    """Verify V3 bearer credentials and expose the contract in OpenAPI."""
    if credentials is None:
        return _verify_token(None)
    if credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _verify_token(credentials.credentials)


def verify_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    """
    Verify Bearer token authentication.
    Returns the token if valid, raises 401 otherwise.
    """
    if not authorization:
        return _verify_token(None)
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return _verify_token(parts[1])
