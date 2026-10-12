import json
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import Depends, HTTPException, security
import httpx
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
from pwdlib import PasswordHash
from sqlalchemy import select
from DB.models import get_db, User
from datetime import datetime, timezone, timedelta
from DB._redis import redis_client
import os
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS"))
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")

password_hash = PasswordHash.recommended()

security = HTTPBearer()

def hash_token(token: str):
    return password_hash.hash(token)

def verify_token(token: str, hashed_token: str):
    return password_hash.verify(token, hashed_token)


async def save_user(db, github_id, username, email):
    result = await db.execute(
        select(User).where(User.github_id == github_id)
    )
    user = result.scalar_one_or_none()

    if user:
        user.username = username
        user.email = email
        user.updated_at = datetime.now(timezone.utc)
    else:
        db.add(User(
            github_id=github_id,
            username=username,
            email=email
        ))

    await db.commit()


def create_access_token(user_id: str):
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )


def create_refresh_token(user_id: str):
    expire = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    token = jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    redis_client.setex(
        f"refresh:{user_id}",
        60 * 60 * 24 * REFRESH_TOKEN_EXPIRE_DAYS,
        hash_token(token)
    )

    return token


def verify_access_token(token: str):
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

        if payload.get("type") != "access":
            raise HTTPException(401, "Invalid token type")

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(401, "Invalid token")

        return user_id

    except ExpiredSignatureError:
        raise HTTPException(401, "Access token expired")

    except InvalidTokenError:
        raise HTTPException(401, "Invalid access token")


def save_github_tokens(user_id: str, tokens: dict):
    redis_client.setex(
        f"github:{user_id}",
        60 * 60 * 24 * 180,
        json.dumps(tokens)
    )


def get_github_tokens(user_id: str):
    data = redis_client.get(f"github:{user_id}")
    return json.loads(data) if data else None


async def refresh_github_tokens(refresh_token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            }
        )

    data = response.json()

    if "access_token" not in data:
        raise HTTPException(401, "GitHub refresh token invalid")

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or refresh_token,
        "expires_in": data.get("expires_in"),
        "token_type": data.get("token_type", "bearer")
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return {
        "user_id": verify_access_token(credentials.credentials)
    }


async def get_github_token(user_id: str):
    tokens = get_github_tokens(user_id)

    if not tokens or not tokens.get("access_token"):
        raise HTTPException(
            401,
            "GitHub token not found. Please login again."
        )

    return tokens["access_token"]