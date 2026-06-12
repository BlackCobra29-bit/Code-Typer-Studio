from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.gif_exporter import build_typing_gif
from src.renderer import build_typing_html, export_project_json, make_render_options
from src.samples import SAMPLES
from src.themes import THEMES


LANGUAGES = [
    "python",
    "javascript",
    "typescript",
    "tsx",
    "jsx",
    "rust",
    "go",
    "java",
    "csharp",
    "cpp",
    "php",
    "ruby",
    "swift",
    "kotlin",
    "html",
    "css",
    "sql",
    "bash",
    "json",
    "yaml",
]

FONTS = [
    "Cascadia Code, Fira Code, Consolas, monospace",
    "Fira Code, Cascadia Code, Consolas, monospace",
    "JetBrains Mono, Fira Code, Consolas, monospace",
    "Consolas, Monaco, monospace",
    "Menlo, Monaco, Consolas, monospace",
]

ASPECT_RATIOS = [
    {"value": "16_9", "label": "16:9 - 1280x720", "width": 1280, "height": 720},
    {"value": "9_16", "label": "9:16 - 720x1280", "width": 720, "height": 1280},
    {"value": "1_1", "label": "1:1 - 1080x1080", "width": 1080, "height": 1080},
    {"value": "4_5", "label": "4:5 - 1080x1350", "width": 1080, "height": 1350},
    {"value": "4_3", "label": "4:3 - 1024x768", "width": 1024, "height": 768},
]
ASPECT_RATIO_DIMENSIONS = {
    item["value"]: (item["width"], item["height"])
    for item in ASPECT_RATIOS
    if item["width"] is not None and item["height"] is not None
}

DEFAULT_SAMPLE = "Python API"
DEFAULT_ASPECT_RATIO = "16_9"
PREVIEW_LINE_HEIGHT = 1.28

LANGUAGE_EXTENSIONS = {
    "bash": "sh",
    "cpp": "cpp",
    "csharp": "cs",
    "css": "css",
    "go": "go",
    "html": "html",
    "java": "java",
    "javascript": "js",
    "json": "json",
    "jsx": "jsx",
    "kotlin": "kt",
    "php": "php",
    "python": "py",
    "ruby": "rb",
    "rust": "rs",
    "sql": "sql",
    "swift": "swift",
    "tsx": "tsx",
    "typescript": "ts",
    "yaml": "yaml",
}


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Code Typer Studio")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    sample = SAMPLES[DEFAULT_SAMPLE]
    initial = _default_payload(sample)
    preview_html = _build_preview(initial)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "languages": LANGUAGES,
            "themes": list(THEMES.keys()),
            "fonts": FONTS,
            "aspect_ratios": ASPECT_RATIOS,
            "samples": SAMPLES,
            "samples_json": json.dumps(SAMPLES),
            "default_sample": DEFAULT_SAMPLE,
            "values": initial,
            "preview_html": preview_html,
            "current_year": date.today().year,
        },
    )


@app.post("/preview", response_class=HTMLResponse)
async def preview(request: Request) -> HTMLResponse:
    values = await _payload_from_request(request)
    return templates.TemplateResponse(
        request,
        "_preview.html",
        {
            "preview_html": _build_preview(values),
            "height": _int(values.get("height"), 620, 320, 1400),
        },
    )


@app.post("/download/html")
async def download_html(request: Request) -> Response:
    values = await _payload_from_request(request)
    options = _options_from_payload(values)
    html = build_typing_html(values.get("code", ""), options, standalone=True)
    return Response(
        html,
        media_type="text/html",
        headers={"Content-Disposition": 'attachment; filename="code-typing-animation.html"'},
    )


@app.post("/download/project")
async def download_project(request: Request) -> Response:
    values = await _payload_from_request(request)
    options = _options_from_payload(values)
    project_json = export_project_json(values.get("code", ""), options)
    return Response(
        project_json,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="code-typer-project.json"'},
    )


@app.post("/download/gif")
async def download_gif(request: Request) -> Response:
    values = await _payload_from_request(request)
    options = _options_from_payload(values)
    gif_bytes = build_typing_gif(
        values.get("code", ""),
        options,
        frame_step=_int(values.get("gif_step"), 3, 1, 10),
    )
    return Response(
        gif_bytes,
        media_type="image/gif",
        headers={"Content-Disposition": 'attachment; filename="code-typing-animation.gif"'},
    )


def _default_payload(sample: dict[str, str]) -> dict[str, Any]:
    language = sample["language"]
    extension = LANGUAGE_EXTENSIONS.get(language, language)
    return {
        "title": f"{DEFAULT_SAMPLE.lower().replace(' ', '-')}.{extension}",
        "language": language,
        "code": sample["code"],
        "theme_name": "VS Code Dark+",
        "font_family": FONTS[0],
        "font_size": 18,
        "line_height": 1.55,
        "aspect_ratio": DEFAULT_ASPECT_RATIO,
        "width": 1280,
        "height": 720,
        "radius": 12,
        "speed_ms": 24,
        "line_pause_ms": 160,
        "start_delay_ms": 350,
        "show_line_numbers": True,
        "show_diff_gutter": False,
        "show_window_chrome": True,
        "autoplay": True,
        "loop": False,
        "cursor": "bar",
        "gif_step": 3,
    }


async def _payload_from_request(request: Request) -> dict[str, Any]:
    form = await request.form()
    aspect_ratio = str(form.get("aspect_ratio", DEFAULT_ASPECT_RATIO))
    width = _int(form.get("width"), 1280, 520, 1600)
    height = _int(form.get("height"), 720, 320, 1400)
    width, height, aspect_ratio = _apply_aspect_ratio(aspect_ratio, width, height)

    return {
        "title": str(form.get("title", "code-typer-studio")),
        "language": str(form.get("language", "python")),
        "code": str(form.get("code", "")),
        "theme_name": str(form.get("theme_name", "Light Studio")),
        "font_family": str(form.get("font_family", FONTS[0])),
        "font_size": _int(form.get("font_size"), 18, 12, 32),
        "line_height": _float(form.get("line_height"), 1.55, 1.1, 2.2),
        "aspect_ratio": aspect_ratio,
        "width": width,
        "height": height,
        "radius": _int(form.get("radius"), 12, 0, 28),
        "speed_ms": _int(form.get("speed_ms"), 24, 4, 120),
        "line_pause_ms": _int(form.get("line_pause_ms"), 160, 0, 800),
        "start_delay_ms": _int(form.get("start_delay_ms"), 350, 0, 2500),
        "show_line_numbers": _bool(form.get("show_line_numbers")),
        "show_diff_gutter": False,
        "show_window_chrome": _bool(form.get("show_window_chrome")),
        "autoplay": _bool(form.get("autoplay")),
        "loop": _bool(form.get("loop")),
        "cursor": str(form.get("cursor", "bar")),
        "gif_step": _int(form.get("gif_step"), 3, 1, 10),
    }


def _options_from_payload(values: dict[str, Any]):
    return make_render_options(
        title=values["title"],
        language=values["language"],
        theme_name=values["theme_name"],
        font_family=values["font_family"],
        font_size=values["font_size"],
        line_height=values["line_height"],
        width=values["width"],
        height=values["height"],
        radius=values["radius"],
        speed_ms=values["speed_ms"],
        line_pause_ms=values["line_pause_ms"],
        start_delay_ms=values["start_delay_ms"],
        show_line_numbers=values["show_line_numbers"],
        show_diff_gutter=values["show_diff_gutter"],
        show_window_chrome=values["show_window_chrome"],
        autoplay=values["autoplay"],
        loop=values["loop"],
        cursor=values["cursor"],
    )


def _build_preview(values: dict[str, Any]) -> str:
    preview_values = {**values, "line_height": PREVIEW_LINE_HEIGHT}
    return build_typing_html(values.get("code", ""), _options_from_payload(preview_values), standalone=False)


def _bool(value: Any) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def _apply_aspect_ratio(aspect_ratio: str, width: int, height: int) -> tuple[int, int, str]:
    dimensions = ASPECT_RATIO_DIMENSIONS.get(aspect_ratio)
    if dimensions is None:
        fallback = ASPECT_RATIO_DIMENSIONS[DEFAULT_ASPECT_RATIO]
        return fallback[0], fallback[1], DEFAULT_ASPECT_RATIO
    return dimensions[0], dimensions[1], aspect_ratio


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _float(value: Any, default: float, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))
