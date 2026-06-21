# Code Typer Studio

Code Typer Studio is a FastAPI web app for creating animated code typing previews. It lets you choose a programming language, theme, filename, animation speed, frame size, cursor style, and export format from a simple browser interface.

## GitHub Repository

```bash
git clone git@github.com:BlackCobra29-bit/Code-Typer-Studio.git
cd Code-Typer-Studio
```

## Features

- Live animated code preview
- Language and file icon support based on filename extension
- Multiple syntax highlighting themes
- Built-in sample code snippets
- Adjustable typing speed, delay, font size, and frame dimensions
- Optional line numbers, window bar, autoplay, and looping
- Export as standalone HTML
- Export project settings as JSON
- Export animated GIF
- macOS-style terminal simulator with word-by-word commands and instant output
- Fixed 700x300 terminal GIF export
- Responsive FastAPI, Jinja2, HTMX, and Tailwind CSS interface

## Tech Stack

- Python
- FastAPI
- Jinja2
- HTMX
- Tailwind CSS
- Pygments
- Pillow

## Run Locally

Create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Start the development server:

```powershell
uvicorn main:app --reload
```

Open the app:

```text
http://127.0.0.1:8000
```

## Project Structure

```text
.
├── main.py
├── requirements.txt
├── src/
│   ├── gif_exporter.py
│   ├── renderer.py
│   ├── samples.py
│   ├── syntax_style.py
│   └── themes.py
├── static/
│   ├── app.js
│   └── icons/
└── templates/
    ├── _preview.html
    └── index.html
```

## Author

Developed by [tesfahiwet truneh](https://www.linkedin.com/in/%F0%90%A9%A9%F0%90%A9%AA%F0%90%A9%B0%F0%90%A9%A2%F0%90%A9%BA%F0%90%A9%A5%F0%90%A9%A9-%F0%90%A9%A9%F0%90%A9%A7%F0%90%A9%A5%F0%90%A9%AC%F0%90%A9%A0-2a2139179/).
