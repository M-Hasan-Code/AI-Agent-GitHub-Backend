import os
import httpx
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from DB.models import get_db
from DB._redis import redis_client
import os

from utilities.tokens import (get_github_tokens, refresh_github_tokens, verify_token,
save_user, save_github_tokens, create_access_token,create_refresh_token)
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"

router = APIRouter(
    prefix="/auth/github",
    tags=["GitHub Authentication"]
)

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI",
    "http://127.0.0.1:8000/auth/github/callback"
)


@router.get("/login")
async def github_login():

    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        "&scope=repo read:user user:email"
    )

    return RedirectResponse(url)


@router.get("/callback")
async def github_callback(
    code: str,
    db: AsyncSession = Depends(get_db)
):

    async with httpx.AsyncClient() as client:

        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={
                "Accept": "application/json"
            },
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI
            }
        )

        token_data = token_response.json()

        if "access_token" not in token_data:
            raise HTTPException(
                status_code=400,
                detail="Failed to get GitHub token"
            )

        github_access = token_data["access_token"]


        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {github_access}"
            }
        )

        if user_response.status_code != 200:
            raise HTTPException(
                status_code=401,
                detail="Failed to get GitHub user"
            )

        user = user_response.json()

        user_id = str(user["id"])
        username = user["login"]


        email_response = await client.get(
            "https://api.github.com/user/emails",
            headers={
                "Authorization": f"Bearer {github_access}"
            }
        )

        emails = email_response.json()

        email = next(
            (
                item["email"]
                for item in emails
                if item.get("primary")
                and item.get("verified")
            ),
            None
        )

    await save_user(
        db,
        user_id,
        username,
        email
    )

    save_github_tokens(
        user_id,
        {
            "access_token": github_access,
            "refresh_token": token_data.get("refresh_token")
        }
    )


    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    response = JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user_id,
            "username": username,
            "email": email
        }
    })

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * REFRESH_TOKEN_EXPIRE_DAYS,
        path="/"
    )

    return response


@router.post("/auth/refresh")
async def refresh_token(request: Request):
    token = request.cookies.get("refresh_token")

    if not token:
        raise HTTPException(401, "Refresh token missing")

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(401, "Invalid refresh token")

        stored_hash = redis_client.get(f"refresh:{user_id}")

        if not stored_hash or not verify_token(token, stored_hash):
            raise HTTPException(
                401,
                "Invalid or expired refresh token"
            )

    except ExpiredSignatureError:
        raise HTTPException(401, "Refresh token has expired")

    except InvalidTokenError:
        raise HTTPException(401, "Invalid refresh token")

    redis_client.delete(f"refresh:{user_id}")

    github_tokens = get_github_tokens(user_id)

    if github_tokens and github_tokens.get("refresh_token"):
        try:
            github_tokens = await refresh_github_tokens(
                github_tokens["refresh_token"]
            )
            save_github_tokens(user_id, github_tokens)
        except Exception:
            pass

    new_refresh = create_refresh_token(user_id)

    response = JSONResponse({
        "access_token": create_access_token(user_id),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    })

    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * REFRESH_TOKEN_EXPIRE_DAYS,
        path="/"
    )

    return response


@router.post("/auth/logout")
async def logout(request: Request):
    token = request.cookies.get("refresh_token")

    if token:
        try:
            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALGORITHM]
            )

            user_id = payload.get("sub")

            if user_id:
                redis_client.delete(f"refresh:{user_id}")

        except InvalidTokenError:
            pass

    response = JSONResponse({
        "message": "Logged out successfully"
    })

    response.delete_cookie("refresh_token", path="/")

    return response