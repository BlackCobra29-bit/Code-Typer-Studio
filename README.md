# Code Typer Studio FastAPI

FastAPI + HTMX + Jinja2 + Bootstrap 5 version of Code Typer Studio.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

## Features

- Server-rendered FastAPI/Jinja UI
- HTMX live preview refresh
- Bootstrap 5 responsive controls
- Reuses the original renderer, syntax themes, samples, and GIF exporter
- Downloads standalone HTML, project JSON, and animated GIF exports
