from fastapi import Depends, HTTPException, APIRouter
import httpx
from utilities.tokens import get_current_user, get_github_token

router = APIRouter(
    prefix="/auth/github",
    tags=["Protected"]
)

@router.get("/repos")
async def get_repos(
    current_user: dict = Depends(get_current_user)
):
    github_token = await get_github_token(
        current_user["user_id"]
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json"
            },
            params={
                "per_page": 100,
                "sort": "updated"
            }
        )

    if response.status_code == 401:
        raise HTTPException(
            401,
            "GitHub token expired. Call /auth/refresh"
        )

    if response.status_code != 200:
        raise HTTPException(
            response.status_code,
            response.text
        )

    return [
        {
            "name": repo["name"],
            "url": repo["html_url"],
            "language": repo["language"]
        }
        for repo in response.json()
    ]