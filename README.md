# AI GitHub Analyzer

<p align="center">
  <img src="https://path-to-your-logo.png" alt="AI GitHub Analyzer Logo" width="200"/>
</p>

<p align="center">
  <strong>A FastAPI tool using Google Gemini to automatically analyze and summarize entire GitHub repositories.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11-blue.svg" alt="Python"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-v0.101-green.svg" alt="FastAPI"></a>
  <a href="https://developers.generativeai.google/"><img src="https://img.shields.io/badge/Google-Gemini-red.svg" alt="Gemini"></a>
  <a href="https://github.com/yourusername/ai-github-analyzer/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-lightgrey.svg" alt="License"></a>
</p>

---

**AI GitHub Analyzer** is a powerful tool designed to help developers, project managers, and security auditors quickly understand the contents and purpose of a GitHub repository. By leveraging the advanced reasoning capabilities of Google's Gemini models, it fetches all files, summarizes them individually, and then creates a high-level, cohesive summary of the entire project.

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Technology Stack](#technology-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [Usage](#usage)
  - [Running the Server](#running-the-server)
  - [Using the API](#using-the-api)
- [API Endpoint](#api-endpoint)
  - [Request](#request)
  - [Response](#response)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Features

-   **🔎 Comprehensive File Fetching**: Clones any public GitHub repository to access its full file structure.
-   **🤖 AI-Powered Summarization**: Uses Google Gemini to generate summaries for each individual file.
-   **✨ High-Level Project Overview**: Synthesizes all file summaries into a single, easy-to-read project summary.
-   **⚙️ Secure Configuration**: Manages API keys and model names securely using environment variables.
-   **📚 Interactive API Docs**: Comes with a pre-configured Swagger UI for easy endpoint testing and interaction.

---

## How It Works

1.  **Input**: The user provides a public GitHub repository URL to the API endpoint.
2.  **Fetch**: The application temporarily clones the repository into memory.
3.  **Analyze**: It iterates through every file in the repository (respecting `.gitignore` if configured).
4.  **Summarize Files**: The content of each file is sent to the Gemini API (`gemini-2.5-flash`) for a concise summary.
5.  **Summarize Project**: All individual file summaries are compiled and sent to a more powerful Gemini model (`gemini-pro-latest`) to generate a final, holistic project overview.
6.  **Output**: A JSON response containing the project summary, file count, and repository name is returned.

---

## Technology Stack

-   **Backend**: Python 3.11
-   **API Framework**: FastAPI
-   **AI Model**: Google Gemini API (`gemini-2.5-flash` & `gemini-pro-latest`)
-   **Server**: Uvicorn

---

## Getting Started

Follow these instructions to get the project up and running on your local machine.

### Prerequisites

-   Python 3.11 or newer
-   Git installed on your machine
-   A Google Gemini API Key. You can get one from [Google AI Studio](https://aistudio.google.com/app/apikey).

### Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/yourusername/ai-github-analyzer.git](https://github.com/yourusername/ai-github-analyzer.git)
    cd ai-github-analyzer
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # For macOS/Linux
    python3 -m venv venv
    source venv/bin/activate

    # For Windows
    python -m venv venv
    venv\Scripts\activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure your environment variables:**
    Create a file named `.env` in the root of the project and add your API key:
    ```ini
    # .env
    GEMINI_API_KEY="YOUR_GOOGLE_GEMINI_API_KEY"
    AI_MODEL_FILE="models/gemini-2.5-flash"
    AI_MODEL_PROJECT="models/gemini-pro-latest"
    ```

---

## Usage

### Running the Server

Launch the application using Uvicorn. The `--reload` flag will automatically restart the server when you make changes to the code.

```bash
uvicorn main:app --reload
```

The API will now be running at http://127.0.0.1:8000.

Using the API
You can interact with the API through its Swagger UI documentation. Open your web browser and navigate to:

http://127.0.0.1:8000/docs

API Endpoint
POST /analyze_repo
This is the main endpoint for analyzing a repository.

Request
The endpoint expects a JSON body with the URL of the public GitHub repository to analyze.

Content-Type: application/json

Body:

JSON

{
  "repo_url": "[https://github.com/ProprioVision/project](https://github.com/ProprioVision/project)"
}
Response
Success (200 OK): Returns a summary of the project.

JSON

{
  "repo": "ProprioVision/project",
  "file_count": 42,
  "project_summary": "This repository is a Python/React web application for managing AI-driven workflows. Key modules include an API backend, frontend React components, and utility scripts. It uses FastAPI for the backend, React for the frontend, and MySQL for database storage..."
}
Error (400 Bad Request): If the URL is invalid or the repository is not found.

JSON

{
  "detail": "Invalid or inaccessible GitHub repository URL."
}


## Project Structure

ai-github-analyzer/
├── main.py               # FastAPI app entrypoint and API routes
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (API key, model names)
├── utils/
│   ├── github_fetcher.py   # Logic for cloning and reading GitHub repos
│   └── summarizer.py     # Gemini integration for summarization
└── README.md             # This file
Contributing
Contributions are welcome! If you have suggestions for improvements or want to add new features, please follow these steps:

Fork the Project.

Create your Feature Branch (git checkout -b feature/AmazingFeature).

Commit your Changes (git commit -m 'Add some AmazingFeature').

Push to the Branch (git push origin feature/AmazingFeature).

Open a Pull Request.

Please make sure to update tests as appropriate.

License
This project is distributed under the MIT License. See LICENSE for more information.

MIT License © 2025 Rex

Acknowledgements
The team behind FastAPI for their excellent framework.

Google for providing access to the powerful Gemini models.

The open-source community.