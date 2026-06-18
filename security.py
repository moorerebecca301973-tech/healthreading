"""
Security utilities: Argon2 password hashing, JWT token creation/verification.

Uses pwdlib with Argon2 (winner of the 2015 Password Hashing Competition).
Argon2 is memory-hard and resists brute-force, side-channel, and precomputation attacks.
Uses PyJWT for token handling (actively maintained, supports Python 3.14).
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

# pwdlib with Argon2 for password hashing
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib import PasswordHash

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-use-env-var")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Seeded admin credentials (set via environment variables in production)
SEEDED_USERNAME = os.getenv("SEEDED_USERNAME", "admin")
SEEDED_PASSWORD = os.getenv("SEEDED_PASSWORD", "admin123")

# ---------------------------------------------------------------------------
# Password Hashing (Argon2 via pwdlib)
# ---------------------------------------------------------------------------

# pwdlib PasswordHash with only Argon2 (no bcrypt fallback)
password_hash = PasswordHash((Argon2Hasher(),))


def hash_password(password: str) -> str:
    """Hash a plain-text password using Argon2. Returns the hash string."""
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against an Argon2 hash."""
    return password_hash.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT Token Management (PyJWT)
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class TokenPayload(BaseModel):
    """Decoded JWT payload."""
    sub: Optional[str] = None  # username
    exp: Optional[datetime] = None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = pyjwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_username(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dependency: extract and verify JWT token from Authorization header.
    Returns the username (sub claim) if valid.
    Raises 401 if token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        # PyJWT handles expiration automatically
    except pyjwt.ExpiredSignatureError:
        raise credentials_exception
    except pyjwt.PyJWTError:
        raise credentials_exception

    return username
