"""Minimal JWT login for the demo users in app/rbac.py.

The token carries only the username. Role and department are looked up on every request,
so changing a user's role takes effect immediately rather than when their token expires.
"""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.rbac import DEMO_USERS, User

DEMO_PASSWORD = "demo"
_bearer = HTTPBearer(auto_error=False)


def authenticate(username: str, password: str) -> User | None:
    user = DEMO_USERS.get(username.lower().strip())
    return user if user and password == DEMO_PASSWORD else None


def create_token(user: User) -> str:
    s = get_settings()
    payload = {"sub": user.username, "exp": datetime.now(UTC) + timedelta(minutes=s.jwt_ttl_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from e
    user = DEMO_USERS.get(payload.get("sub", ""))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
