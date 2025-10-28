import os
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import textwrap
from openai import AsyncOpenAI  # Use AsyncOpenAI
import asyncio
import aiofiles  # For async file operations

load_dotenv()

# --- NEW: Temp directory for individual summaries ---
TEMP_SUMMARY_DIR = "temp_summaries"
# --- END NEW ---

# --- Concurrency Control ---
GEMINI_CONCURRENCY_LIMIT = 15
GEMINI_SEMAPHORE = asyncio.Semaphore(GEMINI_CONCURRENCY_LIMIT)

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("[WARN] GEMINI_API_KEY not set. Summarizer will not function.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

MODEL_FILE_NAME = "models/gemini-2.5-flash-preview-09-2025"
MODEL_PROJECT_NAME = "models/gemini-2.5-flash-preview-09-2025"

# Generation configs
gen_config_file = genai.GenerationConfig(
    temperature=0.1, top_p=0.9, top_k=20, max_output_tokens=2048
)
gen_config_project = genai.GenerationConfig(
    temperature=0.2, top_p=0.9, top_k=30, max_output_tokens=4096
)

# Safety settings
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

try:
    model_file = genai.GenerativeModel(
        MODEL_FILE_NAME, generation_config=gen_config_file, safety_settings=safety_settings
    )
    model_project = genai.GenerativeModel(
        MODEL_PROJECT_NAME, generation_config=gen_config_project, safety_settings=safety_settings
    )
except Exception as e:
    print(f"[ERROR] Could not initialize Gemini models: {e}")
    model_file = None
    model_project = None

# OpenAI fallback configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    aclient = AsyncOpenAI(api_key=OPENAI_API_KEY)
    OPENAI_MODEL = "gpt-3.5-turbo"
    print("[INFO] OpenAI fallback is configured.")
else:
    aclient = None
    print("[WARN] OPENAI_API_KEY not set. OpenAI fallback is disabled.")

CHUNK_SIZE = 4000  # Characters per chunk
BATCH_SIZE = 5     # File summaries per project batch

def chunk_content(content: str, chunk_size: int = CHUNK_SIZE):
    """Chunks content into smaller pieces for the API."""
    return textwrap.wrap(content, width=chunk_size, break_long_words=False, replace_whitespace=False)

async def summarize_with_openai_async(prompt: str) -> str:
    """Fallback to OpenAI API using async client."""
    if not aclient:
        return "[OpenAI Fallback Error] OpenAI API key not configured."
    try:
        response = await aclient.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[OpenAI Fallback Error] {e}"

async def summarize_file_chunk_async(
    prompt: str,
    model: genai.GenerativeModel,
    max_retries: int = 3,
    initial_delay: int = 5
) -> str:
    """Helper to call Gemini API for a chunk with async retry and semaphore."""
    delay = initial_delay
    
    async with GEMINI_SEMAPHORE:
        for attempt in range(max_retries):
            try:
                response = await model.generate_content_async(prompt)
                return response.text.strip()
            
            except ResourceExhausted as e: 
                print(f"[WARN] Gemini quota/rate limit hit. Attempt {attempt + 1}/{max_retries}.")
                if attempt + 1 == max_retries:
                    print("[ERROR] Max retries hit. Falling back to OpenAI.")
                    return await summarize_with_openai_async(prompt)
                
                wait_time = delay + (attempt * 2)
                print(f"Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                delay *= 2
            
            except Exception as e:
                print(f"[ERROR] Gemini API error: {e}. Attempt {attempt + 1}/{max_retries}.")
                if attempt + 1 == max_retries:
                    print("[ERROR] Max retries hit. Falling back to OpenAI.")
                    return await summarize_with_openai_async(prompt)
                await asyncio.sleep(delay)
                delay *= 2
        
        return await summarize_with_openai_async(prompt)

async def summarize_file(path: str, content: str) -> str:
    """
    Summarizes a single file, saves it to a temp file, 
    and returns the path to that temp file.
    """
    if not model_file:
        return "[ERROR] Gemini file model not initialized."
        
    print(f"[INFO] Starting summary for: {path}")
    chunks = chunk_content(content)
    tasks = []
    
    for i, chunk in enumerate(chunks, start=1):
        prompt = f"""
You are an expert software engineer. Analyze this code chunk.

File: {path} (chunk {i}/{len(chunks)})

Instructions:
- **Purpose**: What is the primary role of this code?
- **Main Components**: List main classes, functions, or variables.
- **Key Logic**: Describe any notable algorithms or business logic.
- **Dependencies**: What frameworks or libraries are used?

Content:
```
{chunk}
```
"""
        tasks.append(summarize_file_chunk_async(prompt, model_file))

    # Run all chunk summaries concurrently
    chunk_summaries = await asyncio.gather(*tasks)
    full_summary_content = "\n\n---\n\n".join(chunk_summaries)
    
    # --- NEW: Save summary to a temp file ---
    # Ensure temp directory exists (should be created by main.py, but good to double-check)
    os.makedirs(TEMP_SUMMARY_DIR, exist_ok=True)
    
    # Create a safe filename (e.g., "api_utils_test.js.md")
    safe_filename = path.replace('/', '_').replace('\\', '_')
    temp_filepath = os.path.join(TEMP_SUMMARY_DIR, f"{safe_filename}.md")

    try:
        async with aiofiles.open(temp_filepath, "w", encoding="utf-8") as f:
            await f.write(full_summary_content)
        print(f"[INFO] Saved temp summary to: {temp_filepath}")
        # Return the path to the temp file
        return temp_filepath
    except Exception as e:
        print(f"[ERROR] Failed to write temp summary file {temp_filepath}: {e}")
        return None # Return None on failure
    # --- END NEW ---

async def summarize_project_batch_async(
    prompt: str,
    model: genai.GenerativeModel
) -> str:
    """Helper to call Gemini API for a project batch with semaphore."""
    async with GEMINI_SEMAPHORE:
        try:
            response = await model.generate_content_async(prompt)
            return response.text.strip()
        except ResourceExhausted as e:
            print(f"[WARN] Project batch quota hit. Falling back to OpenAI.")
            return await summarize_with_openai_async(prompt)
        except Exception as e:
            print(f"[ERROR] Project batch error: {e}")
            return f"Error summarizing project batch: {e}"

async def summarize_project(summary_paths: list[str], project_name: str = "Project") -> str:
    """
    Summarizes the entire project from a list of temp summary file paths.
    Deletes the temp files after successful completion.
    """
    if not model_project:
        return "[ERROR] Gemini project model not initialized."

    print(f"[INFO] Starting project-level summary for {project_name} from {len(summary_paths)} files...")
    
    # Sanitize project name for filename
    safe_project_name = "".join(c for c in project_name if c.isalnum() or c in ('-', '_')).rstrip()
    if not safe_project_name:
        safe_project_name = "AI_Project_Summary"
        
    report_filename = f"{safe_project_name}_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    markdown_content = f"# {project_name} - AI Code Analysis\n\n"
    markdown_content += f"**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    markdown_content += "## 1. Project Overview\n\n"

    # --- Generate a high-level overview first ---
    try:
        # Read content from the first few summary files for the overview
        overview_summaries = []
        for path in summary_paths[:3]: # Use first 3 files for a quick overview
            try:
                async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                    # Get file name from path
                    orig_filename = os.path.basename(path).replace('_', '/').replace('.md', '')
                    content = await f.read(1000) # Read first 1000 chars
                    overview_summaries.append(f"**File: {orig_filename}**\n{content}...")
            except Exception as e:
                print(f"[WARN] Could not read temp overview file {path}: {e}")
        
        overview_prompt = f"""
You are a 10x Staff Software Architect.
Analyze the following file summary snippets from a codebase named '{project_name}' and provide a high-level executive summary.

Focus on:
1.  **Primary Purpose**: What does this application do?
2.  **Core Technologies**: What are the main frameworks and libraries?
3.  **Architecture**: What is the high-level architecture?

**File Summary Snippets:**
{"\n\n".join(overview_summaries)}
(and {len(summary_paths) - len(overview_summaries)} more files)
"""
        overview = await summarize_project_batch_async(overview_prompt, model_project)
        markdown_content += f"{overview}\n\n## 2. Detailed File Analysis\n\n"
    except Exception as e:
        print(f"[WARN] Could not generate project overview: {e}")
        markdown_content += "Could not generate project overview.\n\n## 2. Detailed File Analysis\n\n"

    # --- Generate detailed analysis in batches by reading from temp files ---
    tasks = []
    for i in range(0, len(summary_paths), BATCH_SIZE):
        batch_paths = summary_paths[i:i + BATCH_SIZE]
        
        # Helper to read files for the batch
        async def read_batch_files(paths):
            batch_summaries = []
            for path in paths:
                try:
                    async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                        # Get original file name from temp path
                        orig_filename = os.path.basename(path).replace('_', '/').replace('.md', '')
                        content = await f.read()
                        batch_summaries.append(f"--- File: {orig_filename} ---\n{content}")
                except Exception as e:
                    print(f"[WARN] Failed to read temp file {path} for batch: {e}")
                    batch_summaries.append(f"--- File: {path} (Error reading) ---")
            return "\n\n".join(batch_summaries)

        # Read file contents for the current batch
        joined_summaries = await read_batch_files(batch_paths)

        prompt = f"""
You are an expert software architect.
Here are {len(batch_paths)} file summaries from the project:

{joined_summaries}

Produce a detailed, structured analysis of **these files only**.
Focus on:
1.  **Module/Folder Purpose**: What is the purpose of this group of files?
2.  **Key Relationships**: How do these files interact?
3.  **Design Patterns**: Any obvious patterns?
4.  **Key Logic/Dependencies**: Any complex logic or important external dependencies?

Format the output in clean Markdown.
"""
        tasks.append(summarize_project_batch_async(prompt, model_project))

    # Run all batch-summary tasks concurrently
    batch_results = await asyncio.gather(*tasks)
    markdown_content += "\n\n---\n\n".join(batch_results)

    # --- Write the final report asynchronously ---
    try:
        async with aiofiles.open(report_filename, "w", encoding="utf-8") as f:
            await f.write(markdown_content)
        print(f"[INFO] Successfully generated project summary: {report_filename}")
        
        # --- NEW: Cleanup temp files ---
        print(f"[INFO] Cleaning up {len(summary_paths)} temp summary files...")
        cleanup_count = 0
        for temp_path in summary_paths:
            try:
                os.remove(temp_path)
                cleanup_count += 1
            except Exception as e:
                print(f"[WARN] Failed to delete temp file {temp_path}: {e}")
        print(f"[INFO] Cleaned up {cleanup_count} files.")
        # --- END NEW ---
        
        return report_filename
        
    except Exception as e:
        print(f"[ERROR] Failed to write final summary file: {e}")
        return f"[ERROR] Failed to write final summary file: {e}"

