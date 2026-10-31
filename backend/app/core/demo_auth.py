"""Optional HTTP Basic gate for billable and mutating demo operations."""

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import get_settings

_basic_auth = HTTPBasic(auto_error=False)


def require_demo_auth(
    credentials: Optional[HTTPBasicCredentials] = Depends(_basic_auth),
) -> None:
    """Require configured demo credentials when the deployment enables the gate."""
    settings = get_settings()
    if not settings.demo_auth_enabled:
        return

    username_ok = credentials is not None and secrets.compare_digest(
        credentials.username, settings.demo_auth_username
    )
    password_ok = credentials is not None and secrets.compare_digest(
        credentials.password, settings.demo_auth_password
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Demo credentials are required",
            headers={"WWW-Authenticate": 'Basic realm="ParchaPay Demo"'},
        )
