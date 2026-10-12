# AI Agent Backend | FastAPI & LangGraph

An AI agent backend built with FastAPI, LangGraph, PostgreSQL, and Pinecone. The project uses asynchronous database operations and `uv` for Python environment and dependency management.

## Overview

This project provides the backend infrastructure for an AI-powered application.

- **FastAPI** handles API requests and responses.
- **LangGraph** manages AI agent workflows and state.
- **Neon PostgreSQL** stores relational application data.
- **PostgreSQL Checkpointer** persists supported LangGraph workflow states.
- **Pinecone** provides vector storage and similarity search.
- **uv** manages Python dependencies and the virtual environment.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python | Core programming language |
| FastAPI | Backend API framework |
| LangGraph | AI agent workflow orchestration |
| PostgreSQL | Relational database |
| Neon | Serverless PostgreSQL hosting |
| SQLAlchemy Async | Asynchronous database operations |
| Psycopg Async | Asynchronous PostgreSQL connections |
| Pinecone | Vector database and similarity search |
| uv | Python package and environment management |
| Git & GitHub | Version control and code hosting |

## Key Features

- Asynchronous API development with FastAPI
- AI agent workflow orchestration using LangGraph
- Asynchronous PostgreSQL database access
- Persistent checkpoint storage for agent workflows
- Vector database integration with Pinecone
- Python dependency management using `uv`

*Available features depend on the functionality implemented in the application code.*

## Getting Started

### Prerequisites

Install the following tools:

- Python
- uv
- Git

You will also need access to the PostgreSQL database and Pinecone services used by the application.

### 1. Clone the Repository

Replace the URL with your actual GitHub repository URL.

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

### 2. Create a Virtual Environment

Create the virtual environment using `uv`:

```bash
uv venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

For Windows CMD:

```bat
.venv\Scripts\activate.bat
```

### 3. Install Dependencies
```bash
uv pip install -r requirements.txt
```

### 4. Run the Application

If your FastAPI instance is named `app` in `main.py`, start the server with:

```bash
uv run uvicorn main:app --reload
```

Run this command from the directory containing `main.py`. Adjust the module path if your entry point is different.

### 5. Access API Documentation

Once the server is running, open:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

## Database and Vector Storage

### PostgreSQL

PostgreSQL stores relational application data. Neon provides the hosted PostgreSQL database.

### LangGraph Checkpointer

The PostgreSQL checkpointer can save and restore agent workflow state, depending on the application's configuration.

### Pinecone

Pinecone stores vector embeddings and supports similarity searches for retrieving relevant information. The embedding model, index configuration, and retrieval pipeline depend on the application's implementation.

---

**Built with FastAPI, LangGraph, PostgreSQL, Pinecone, and uv.**