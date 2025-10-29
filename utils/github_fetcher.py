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
            # Store sha and content
            files[data["path"]] = {"sha": data.get("sha"), "content": content}
        return files

    # If a directory
    file_fetch_info = []  # Store info for files to fetch
    dir_tasks = []        # Separate list for directory tasks
    
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

            # Add file info to our list instead of creating the task
            file_fetch_info.append({
                "path": item["path"],
                "sha": item.get("sha"),
                "url": item["download_url"]
            })
            
        elif item.get("type") == "dir":
            # Add the recursive directory fetch task
            dir_tasks.append(
                fetch_dir(client, owner, repo, item["path"])
            )

    # Create file tasks from our info list
    file_tasks = [fetch_file(client, f["url"]) for f in file_fetch_info]
    
    # Wait for all file fetch tasks and subdirectory tasks to complete
    if file_tasks or dir_tasks:
        results = await asyncio.gather(*file_tasks, *dir_tasks)
        
        num_file_results = len(file_tasks)
        
        # Process file results
        for i, content in enumerate(results[:num_file_results]):
            if content: # Only add if fetch was successful
                info = file_fetch_info[i]
                files[info["path"]] = {"sha": info["sha"], "content": content}
        
        # Process directory results
        for res in results[num_file_results:]:
            if isinstance(res, dict):
                files.update(res)

    return files


def fetch_files(owner: str, repo: str) -> dict[str, dict[str, str]]:
    """
    Entry point to fetch all files from a GitHub repo.
    This function runs the async fetcher and blocks until it's done.
    It's intended to be run in a separate thread via `asyncio.to_thread`.
    Returns a dict mapping file path to {"sha": str, "content": str}
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
        return {
            path: data for path, data in files.items()
            if data and data.get("content") is not None
        }
    except Exception as e:
        print(f"[ERROR] Async runner failed: {e}")
        # Propagate exception to be handled by main.py
        raise e