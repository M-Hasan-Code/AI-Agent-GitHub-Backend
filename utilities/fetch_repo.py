import base64
from fastapi import HTTPException
from utilities.tokens import get_github_token
import httpx

async def fetch_repo_text(repo_name ,current_user):
    github_token = await get_github_token(
        current_user["user_id"]
    )

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            "https://api.github.com/user",
            headers=headers
        )

        if user_response.status_code != 200:
            raise HTTPException(
                user_response.status_code,
                user_response.text
            )

        username = user_response.json()["login"]

        repo_response = await client.get(
            f"https://api.github.com/repos/{username}/{repo_name}",
            headers=headers
        )

        if repo_response.status_code == 404:
            raise HTTPException(404, "Repository not found")

        if repo_response.status_code != 200:
            raise HTTPException(
                repo_response.status_code,
                repo_response.text
            )

        default_branch = repo_response.json()["default_branch"]

        tree_response = await client.get(
            f"https://api.github.com/repos/{username}/{repo_name}"
            f"/git/trees/{default_branch}?recursive=1",
            headers=headers
        )

        if tree_response.status_code != 200:
            raise HTTPException(
                tree_response.status_code,
                tree_response.text
            )

        items = []

        for item in tree_response.json().get("tree", []):
            if item["type"] == "tree":
                items.append({
                    "type": "folder",
                    "path": item["path"]
                })

            elif item["type"] == "blob":
                file_response = await client.get(
                    f"https://api.github.com/repos/{username}/{repo_name}"
                    f"/contents/{item['path']}",
                    headers=headers
                )

                if file_response.status_code != 200:
                    continue

                file_data = file_response.json()
                content = None

                if file_data.get("encoding") == "base64":
                    try:
                        content = base64.b64decode(
                            file_data["content"]
                        ).decode("utf-8")
                    except UnicodeDecodeError:
                        pass

                items.append({
                    "type": "file",
                    "path": item["path"],
                    "content": content
                })

    return items