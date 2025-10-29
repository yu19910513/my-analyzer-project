import re
import os
import json
import asyncio
import aiofiles
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

# Import your helpers
from utils.github_fetcher import fetch_files
from utils.summarizer import summarize_file, summarize_project, TEMP_SUMMARY_DIR

load_dotenv()

app = FastAPI(title="AI GitHub Analyzer (Async Streaming & Caching)")

# Regex for GitHub repo URLs (with optional .git or trailing slash)
GITHUB_REGEX = r"^https:\/\/github\.com\/([\w\-]+)\/([\w\-]+)(?:\.git)?\/?$"


# Text file extensions to process
TEXT_EXTENSIONS = [
    ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".md", ".yaml", ".yml",
    ".html", ".css", ".scss", ".go", ".java", ".cs", ".php", ".rb", ".rs", ".swift",
    "dockerfile", ".env.example", ".gitignore", ".toml", ".ini", ".xml", ".sh",
    ".sql", ".properties", ".gradle", "requirements.txt", "package.json", "composer.json"
]

@app.on_event("startup")
async def startup_event():
    """Create the temporary summary directory on startup."""
    os.makedirs(TEMP_SUMMARY_DIR, exist_ok=True)
    print(f"Temporary summary directory created at: ./{TEMP_SUMMARY_DIR}")

@app.get("/")
async def home():
    return {"message": "Welcome to the AI GitHub Analyzer. Use /docs to see endpoints."}


# ----------------------------
# Classic endpoint (JSON)
# ----------------------------
@app.get("/analyze_repo")
async def analyze_repo(url: str):
    """
    Analyzes a GitHub repo and returns a single JSON response
    after all processing is complete. Uses caching.
    """
    # Validate GitHub URL
    match = re.match(GITHUB_REGEX, url)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub URL. Must be of the form https://github.com/username/projectname"
        )

    owner, repo = match.group(1), match.group(2)
    print(f"[INFO] Starting classic analysis for: {owner}/{repo}")

    # Fetch all files
    try:
        # files is now dict[path, {"sha": str, "content": str}]
        files = await asyncio.to_thread(fetch_files, owner, repo)
    except Exception as e:
        print(f"[ERROR] Error fetching files: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching files: {e}")

    if not files:
        raise HTTPException(status_code=404, detail="No readable files found.")

    # Filter files
    files_to_process = {
        p: data for p, data in files.items()
        if any(p.endswith(ext) for ext in TEXT_EXTENSIONS) and data.get("content", "").strip()
    }
    
    if not files_to_process:
         raise HTTPException(status_code=404, detail="No text files found to analyze.")

    print(f"[INFO] Fetched {len(files)} files, processing {len(files_to_process)}.")

    # Summarize files asynchronously
    async def summarize_path(path, file_data):
        """Helper to run summarize_file and return its path."""
        try:
            # Pass path, content, and sha
            return await summarize_file(path, file_data["content"], file_data["sha"])
        except Exception as e:
            print(f"[ERROR] Failed to summarize {path}: {e}")
            return None

    tasks = [summarize_path(p, data) for p, data in files_to_process.items()]
    
    # summary_paths will be a list of file paths to the temp summaries
    summary_paths = await asyncio.gather(*tasks)
    
    # Filter out any 'None' results from failed summaries
    valid_summary_paths = [path for path in summary_paths if path]
    
    if not valid_summary_paths:
        raise HTTPException(status_code=500, detail="All file summaries failed.")

    # Summarize the whole project from the temp summary files
    try:
        project_summary_file = await summarize_project(valid_summary_paths, repo)
    except Exception as e:
        print(f"[ERROR] Error generating project summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating project summary: {e}")

    return {
        "repo": f"{owner}/{repo}",
        "total_files_fetched": len(files),
        "files_analyzed": len(valid_summary_paths),
        "project_summary_file": project_summary_file
    }


# ----------------------------
# Streaming endpoint (SSE)
# ----------------------------
async def summarize_files_stream(url: str, request: Request):
    """
    Asynchronously fetches, summarizes, and streams results
    using Server-Sent Events (SSE). Uses caching.
    """
    # Validate GitHub URL
    match = re.match(GITHUB_REGEX, url)
    if not match:
        yield f"data: {json.dumps({'error': 'Invalid GitHub URL'})}\n\n"
        return

    owner, repo = match.group(1), match.group(2)
    print(f"[STREAM] Starting stream for: {owner}/{repo}")

    # Fetch files
    try:
        yield f"data: {json.dumps({'status': 'Fetching repository structure...', 'repo': f'{owner}/{repo}'})}\n\n"
        # files is now dict[path, {"sha": str, "content": str}]
        files = await asyncio.to_thread(fetch_files, owner, repo)
    except Exception as e:
        print(f"[STREAM] Error fetching files: {e}")
        yield f"data: {json.dumps({'error': f'Error fetching files: {e}'})}\n\n"
        return

    if not files:
        yield f"data: {json.dumps({'error': 'No readable files found.'})}\n\n"
        return
        
    # Filter files to process
    files_to_process = {
        p: data for p, data in files.items()
        if any(p.endswith(ext) for ext in TEXT_EXTENSIONS) and data.get("content", "").strip()
    }
    
    if not files_to_process:
        yield f"data: {json.dumps({'error': 'No text files found to analyze.'})}\n\n"
        return

    total_files = len(files_to_process)
    yield f"data: {json.dumps({'status': f'Fetched {len(files)} files, analyzing {total_files}...'})}\n\n"
    
    # This list will hold the file paths to the temporary summaries
    file_summary_paths = []

    for idx, (path, file_data) in enumerate(files_to_process.items(), start=1):
        if await request.is_disconnected():
            print("[STREAM] Client disconnected. Stopping stream.")
            return

        try:
            yield f"data: {json.dumps({'status': f'Summarizing {path} ({idx}/{total_files})...'})}\n\n"
            
            # 1. Pass path, content, and sha (includes caching logic)
            summary_path = await summarize_file(path, file_data["content"], file_data["sha"])
            
            if summary_path is None:
                print(f"[STREAM] Skipping failed summary for {path}")
                yield f"data: {json.dumps({'error': f'Skipping failed summary for {path}'})}\n\n"
                continue

            file_summary_paths.append(summary_path)

            # 2. We read that temp JSON file's content to stream it back to the user
            async with aiofiles.open(summary_path, 'r', encoding='utf-8') as f:
                cache_data = json.loads(await f.read())
                summary_content = cache_data.get("summary", "[ERROR] Summary not found in cache")

            # 3. Stream the file summary content
            yield f"data: {json.dumps({'file_summary': {'path': path, 'summary': summary_content}})}\n\n"
        
        except Exception as e:
            print(f"[STREAM] Error summarizing {path}: {e}")
            yield f"data: {json.dumps({'error': f'Error summarizing {path}: {e}'})}\n\n"

    # Project-level summary
    if not file_summary_paths:
        yield f"data: {json.dumps({'error': 'No files were successfully summarized.'})}\n\n"
        return

    try:
        yield f"data: {json.dumps({'status': 'Generating final project summary...'})}\n\n"
        await asyncio.sleep(0.1)

        # 4. summarize_project reads from the temp files and deletes them after
        report_file = await summarize_project(file_summary_paths, repo)
        yield f"data: {json.dumps({'project_summary_file': report_file})}\n\n"
    
    except Exception as e:
        print(f"[STREAM] Error generating project summary: {e}")
        yield f"data: {json.dumps({'error': f'Error generating project summary: {e}'})}\n\n"

    yield f"data: {json.dumps({'status': 'Completed'})}\n\n"


@app.get("/analyze_repo_stream")
async def stream_endpoint(url: str, request: Request):
    """
    Endpoint to stream GitHub repo analysis progress 
    using Server-Sent Events (SSE).
    """
    return StreamingResponse(summarize_files_stream(url, request), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    # Make sure GITHUB_TOKEN and GOOGLE_API_KEY are in your .env file
    print("Starting server... Access docs at http://127.0.0.1:8000/docs")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)