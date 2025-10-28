import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"


async def fetch_file(client, url):
    """Fetch individual file content asynchronously"""
    try:
        resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[WARN] Failed to fetch {url}: {e}")
        return None


async def fetch_dir(client, owner: str, repo: str, path=""):
    """Recursively fetch all files in a directory"""
    url = GITHUB_API_URL.format(owner=owner, repo=repo, path=path)
    try:
        resp = await client.get(url, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        # Handle common errors like 404 Not Found or 403 Forbidden
        print(f"[ERROR] Failed to fetch directory {path}: {e}")
        return {} # Return empty dict on error
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred for {path}: {e}")
        return {}

    files = {}

    # If a single file (e.g., user linked to a file, not a dir)
    if isinstance(data, dict) and data.get("type") == "file":
        if not data.get("download_url"):
            print(f"[WARN] No download_url for file: {data.get('path')}")
            return {}
        content = await fetch_file(client, data["download_url"])
        if content:
            files[data["path"]] = content
        return files

    # If a directory
    tasks = []
    # We need a separate list to map file content results back to paths
    file_paths_in_this_dir = [] 
    
    if not isinstance(data, list):
        print(f"[WARN] Expected list for directory contents at {path}, but got {type(data)}. Skipping.")
        return {}

    for item in data:
        if item.get("type") == "file":
            # Skip large/binary files, and common non-text files
            if item["name"].lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".ico", ".exe", ".dll", ".zip", ".tar",
                 ".gz", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".doc", ".docx",
                 ".xls", ".xlsx", ".ppt", ".pptx", ".DS_Store", ".lock", ".log")
            ):
                print(f"[SKIP] Skipping binary/unsupported file {item['path']}")
                continue
            
            if not item.get("download_url"):
                print(f"[WARN] No download_url for file: {item.get('path')}")
                continue

            # Add the file fetch task
            tasks.append(
                fetch_file(client, item["download_url"])
            )
            # Store its path in order
            file_paths_in_this_dir.append(item["path"])
            
        elif item.get("type") == "dir":
            # Add the recursive directory fetch task
            tasks.append(
                fetch_dir(client, owner, repo, item["path"])
            )

    # Wait for all file fetch tasks and subdirectory tasks to complete
    if tasks:
        results = await asyncio.gather(*tasks)
        
        file_content_index = 0
        for res in results:
            if isinstance(res, dict):
                # This is a dict of files from a subdirectory
                files.update(res)
            elif isinstance(res, str):
                # This is file content.
                # Assign it to the correct path from our ordered list.
                if file_content_index < len(file_paths_in_this_dir):
                    path = file_paths_in_this_dir[file_content_index]
                    files[path] = res # res is guaranteed not None (it's a string)
                    file_content_index += 1
                else:
                    # This should not happen if logic is correct
                    print(f"[WARN] Mismatched file content. Discarding.")
            # We explicitly ignore None results from failed fetch_file calls

    return files


def fetch_files(owner: str, repo: str) -> dict[str, str]:
    """
    Entry point to fetch all files from a GitHub repo.
    This function runs the async fetcher and blocks until it's done.
    It's intended to be run in a separate thread via `asyncio.to_thread`.
    """
    async def runner():
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            return await fetch_dir(client, owner, repo)

    print(f"[INFO] Starting async file fetcher for {owner}/{repo}...")
    try:
        # We run a new async event loop here.
        # This is why the whole function must be run in `asyncio.to_thread`
        files = asyncio.run(runner())
        print(f"[INFO] Fetched {len(files)} files.")
        # Filter out any files that had None content
        return {path: content for path, content in files.items() if content is not None}
    except Exception as e:
        print(f"[ERROR] Async runner failed: {e}")
        # Propagate exception to be handled by main.py
        raise e

