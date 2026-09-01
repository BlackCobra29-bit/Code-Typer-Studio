from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.gif_exporter import build_typing_gif, build_typing_mp4, ExportLimitError
from src.diff_exporter import build_diff_gif, build_diff_mp4
from src.diff_renderer import build_diff_html, export_diff_project, make_diff_options
from src.gradients import gradient_catalog
from src.languages import LANGUAGE_CATALOG, LANGUAGES
from src.renderer import build_typing_html, export_project_json, make_render_options
from src.samples import SAMPLES
from src.terminal_renderer import (
    DEFAULT_TERMINAL_COMMAND,
    DEFAULT_TERMINAL_OUTPUT,
    TerminalOptions,
    build_terminal_gif,
    build_terminal_html,
    build_terminal_mp4,
)
from src.syntax_style import THEME_NAMES, HighlightingUnavailable, highlight_code, normalize_code


FONTS = [
    "JetBrains Mono, Consolas, monospace",
    "Cascadia Code, Fira Code, Consolas, monospace",
    "Fira Code, Cascadia Code, Consolas, monospace",
    "Consolas, Monaco, monospace",
    "Menlo, Monaco, Consolas, monospace",
]

CODE_ASPECT_RATIOS = [
    {"value": "16_9", "label": "16:9 - 1280x720 px", "width": 1280, "height": 720},
    {"value": "1_1", "label": "1:1 - 1080x1080 px", "width": 1080, "height": 1080},
]
CODE_ASPECT_RATIO_DIMENSIONS = {
    item["value"]: (item["width"], item["height"])
    for item in CODE_ASPECT_RATIOS
}
TERMINAL_ASPECT_RATIOS = [
    {"value": "display", "label": "Display - 700x300", "width": 700, "height": 300},
    {"value": "16_9", "label": "16:9 - 1280x720", "width": 1280, "height": 720},
    {"value": "9_16", "label": "9:16 - 720x1280", "width": 720, "height": 1280},
    {"value": "1_1", "label": "1:1 - 1080x1080", "width": 1080, "height": 1080},
    {"value": "4_5", "label": "4:5 - 1080x1350", "width": 1080, "height": 1350},
    {"value": "4_3", "label": "4:3 - 1024x768", "width": 1024, "height": 768},
]
TERMINAL_ASPECT_RATIO_DIMENSIONS = {
    item["value"]: (item["width"], item["height"])
    for item in TERMINAL_ASPECT_RATIOS
}
TYPING_MODES = [
    {"value": "character", "label": "Character"},
    {"value": "token", "label": "Syntax token"},
    {"value": "word", "label": "Word"},
    {"value": "line", "label": "Line"},
]

DEFAULT_SAMPLE = "Python API"
DEFAULT_ASPECT_RATIO = "16_9"
GIF_FRAME_STEP = 3

DEFAULT_DIFF_ORIGINAL = '''from django.shortcuts import render
from .models import Post


def post_list(request):
    posts = Post.objects.all()

    for post in posts:
        print(post.author.name)

    return render(
        request, "blog/post_list.html", {"posts": posts},
    )'''
DEFAULT_DIFF_REVISED = DEFAULT_DIFF_ORIGINAL.replace(
    "posts = Post.objects.all()", 'posts = Post.objects.select_related("author")'
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Code Typer Studio")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.exception_handler(ExportLimitError)
async def export_limit(request: Request, exc: ExportLimitError):
    return Response(str(exc), status_code=422, media_type="text/plain")


@app.exception_handler(HighlightingUnavailable)
async def highlighting_unavailable(request: Request, exc: HighlightingUnavailable):
    return Response(str(exc), status_code=503, media_type="text/plain")


@app.post("/highlight")
async def highlight_source(request: Request):
    values = await _payload_from_request(request)
    return await run_in_threadpool(highlight_code, values["code"], values["language"], values["theme_name"])


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"current_year": date.today().year},
    )


@app.get("/code-typer", response_class=HTMLResponse)
async def code_typer(request: Request) -> HTMLResponse:
    sample = SAMPLES[DEFAULT_SAMPLE]
    initial = _default_payload(sample)
    preview_html = await run_in_threadpool(_build_preview, initial)
    return templates.TemplateResponse(
        request,
        "code_typer.html",
        {
            "languages": LANGUAGES,
            "language_catalog": LANGUAGE_CATALOG,
            "themes": list(THEME_NAMES),
            "gradients": gradient_catalog(),
            "fonts": FONTS,
            "aspect_ratios": CODE_ASPECT_RATIOS,
            "typing_modes": TYPING_MODES,
            "samples": SAMPLES,
            "samples_json": json.dumps(SAMPLES),
            "default_sample": DEFAULT_SAMPLE,
            "values": initial,
            "preview_html": preview_html,
            "current_year": date.today().year,
        },
    )


@app.get("/terminal", response_class=HTMLResponse)
async def terminal(request: Request) -> HTMLResponse:
    values = _default_terminal_payload()
    return templates.TemplateResponse(
        request,
        "terminal.html",
        {
            "values": values,
            "gradients": gradient_catalog(),
            "aspect_ratios": TERMINAL_ASPECT_RATIOS,
            "preview_html": build_terminal_html(_terminal_options(values)),
            "current_year": date.today().year,
        },
    )


@app.get("/code-diff", response_class=HTMLResponse)
async def code_diff(request: Request) -> HTMLResponse:
    values = _default_diff_payload()
    preview_html = await run_in_threadpool(
        build_diff_html, values["original_code"], values["revised_code"], _diff_options_from_payload(values)
    )
    return templates.TemplateResponse(request, "code_diff.html", {
        "values": values, "languages": LANGUAGES, "language_catalog": LANGUAGE_CATALOG,
        "themes": list(THEME_NAMES), "fonts": FONTS, "gradients": gradient_catalog(),
        "aspect_ratios": CODE_ASPECT_RATIOS, "preview_html": preview_html,
        "current_year": date.today().year,
    })


@app.post("/code-diff/preview", response_class=HTMLResponse)
async def code_diff_preview(request: Request) -> HTMLResponse:
    values = await _diff_payload_from_request(request)
    preview_html = await run_in_threadpool(
        build_diff_html, values["original_code"], values["revised_code"], _diff_options_from_payload(values)
    )
    return templates.TemplateResponse(request, "_diff_preview.html", {"preview_html": preview_html})


@app.post("/code-diff/download/html")
async def download_diff_html(request: Request) -> Response:
    values = await _diff_payload_from_request(request)
    document = await run_in_threadpool(
        build_diff_html, values["original_code"], values["revised_code"], _diff_options_from_payload(values), True
    )
    return Response(document, media_type="text/html",
                    headers={"Content-Disposition": 'attachment; filename="code-diff-animation.html"'})


@app.post("/code-diff/download/project")
async def download_diff_project(request: Request) -> Response:
    values = await _diff_payload_from_request(request)
    document = export_diff_project(values["original_code"], values["revised_code"], _diff_options_from_payload(values))
    return Response(document, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="code-diff-project.json"'})


@app.post("/code-diff/download/gif")
async def download_diff_gif(request: Request) -> Response:
    values = await _diff_payload_from_request(request)
    data = await run_in_threadpool(
        build_diff_gif, values["original_code"], values["revised_code"], _diff_options_from_payload(values)
    )
    return Response(data, media_type="image/gif",
                    headers={"Content-Disposition": 'attachment; filename="code-diff-animation.gif"'})


@app.post("/code-diff/download/mp4")
async def download_diff_mp4(request: Request) -> Response:
    values = await _diff_payload_from_request(request)
    data = await run_in_threadpool(
        build_diff_mp4, values["original_code"], values["revised_code"], _diff_options_from_payload(values)
    )
    return Response(data, media_type="video/mp4",
                    headers={"Content-Disposition": 'attachment; filename="code-diff-animation.mp4"'})


@app.post("/terminal/preview", response_class=HTMLResponse)
async def terminal_preview(request: Request) -> HTMLResponse:
    values = await _terminal_payload_from_request(request)
    return templates.TemplateResponse(
        request,
        "_terminal_preview.html",
        {"preview_html": build_terminal_html(_terminal_options(values))},
    )


@app.post("/terminal/download/html")
async def download_terminal_html(request: Request) -> Response:
    values = await _terminal_payload_from_request(request)
    document = build_terminal_html(_terminal_options(values), standalone=True)
    return Response(
        document,
        media_type="text/html",
        headers={"Content-Disposition": 'attachment; filename="terminal-animation.html"'},
    )


@app.post("/terminal/download/gif")
async def download_terminal_gif(request: Request) -> Response:
    values = await _terminal_payload_from_request(request)
    gif_bytes = build_terminal_gif(_terminal_options(values))
    return Response(
        gif_bytes,
        media_type="image/gif",
        headers={"Content-Disposition": 'attachment; filename="terminal-animation.gif"'},
    )


@app.post("/terminal/download/mp4")
async def download_terminal_mp4(request: Request) -> Response:
    values = await _terminal_payload_from_request(request)
    mp4_bytes = build_terminal_mp4(_terminal_options(values))
    return Response(
        mp4_bytes,
        media_type="video/mp4",
        headers={"Content-Disposition": 'attachment; filename="terminal-animation.mp4"'},
    )


@app.post("/preview", response_class=HTMLResponse)
async def preview(request: Request) -> HTMLResponse:
    values = await _payload_from_request(request)
    return templates.TemplateResponse(
        request,
        "_preview.html",
        {
            "preview_html": await run_in_threadpool(_build_preview, values),
            "height": _int(values.get("height"), 620, 320, 1400),
        },
    )


@app.post("/download/html")
async def download_html(request: Request) -> Response:
    values = await _payload_from_request(request)
    options = _options_from_payload(values)
    html = await run_in_threadpool(build_typing_html, values.get("code", ""), options, standalone=True)
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
    gif_bytes = await run_in_threadpool(build_typing_gif,
        values.get("code", ""),
        options,
        frame_step=GIF_FRAME_STEP,
    )
    return Response(
        gif_bytes,
        media_type="image/gif",
        headers={"Content-Disposition": 'attachment; filename="code-typing-animation.gif"'},
    )


@app.post("/download/mp4")
async def download_mp4(request: Request) -> Response:
    values = await _payload_from_request(request)
    options = _options_from_payload(values)
    mp4_bytes = await run_in_threadpool(build_typing_mp4,
        values.get("code", ""),
        options,
        frame_step=GIF_FRAME_STEP,
    )
    return Response(
        mp4_bytes,
        media_type="video/mp4",
        headers={"Content-Disposition": 'attachment; filename="code-typing-animation.mp4"'},
    )


def _default_payload(sample: dict[str, str]) -> dict[str, Any]:
    language = sample["language"]
    return {
        "language": language,
        "code": sample["code"],
        "theme_name": "VS Code Dark+",
        "font_family": FONTS[0],
        "font_size": 22,
        "line_height": 1.6,
        "aspect_ratio": DEFAULT_ASPECT_RATIO,
        "width": 1280,
        "height": 720,
        "radius": 14,
        "speed_ms": 24,
        "line_pause_ms": 160,
        "start_delay_ms": 550,
        "typing_mode": "character",
        "background_style": "gradient",
        "gradient_name": "midnight",
        "canvas_padding": 92,
        "show_line_numbers": True,
        "show_diff_gutter": False,
        "show_window_chrome": True,
        "autoplay": True,
        "loop": False,
        "cursor": "bar",
        "gif_step": GIF_FRAME_STEP,
    }


def _default_terminal_payload() -> dict[str, Any]:
    return {
        "title": "eminem - zsh",
        "prompt": "eminem@macbook ~ %",
        "command": DEFAULT_TERMINAL_COMMAND,
        "output": DEFAULT_TERMINAL_OUTPUT,
        "word_speed_ms": 320,
        "output_delay_ms": 1000,
        "aspect_ratio": "16_9",
        "width": 1280,
        "height": 720,
        "background_style": "none",
        "gradient_name": "sunset",
        "canvas_padding": 52,
        "loop": True,
    }


def _default_diff_payload() -> dict[str, Any]:
    return {
        "language": "python", "theme_name": "VS Code Dark+",
        "original_code": DEFAULT_DIFF_ORIGINAL, "revised_code": DEFAULT_DIFF_REVISED,
        "font_family": FONTS[0], "font_size": 20, "line_height": 1.55,
        "aspect_ratio": "16_9", "width": 1280, "height": 720, "radius": 14,
        "transition_ms": 650, "hold_ms": 1050, "start_delay_ms": 550,
        "background_style": "gradient", "gradient_name": "midnight", "canvas_padding": 92,
        "show_line_numbers": True, "show_window_chrome": True, "autoplay": True,
        "loop": False,
    }


async def _diff_payload_from_request(request: Request) -> dict[str, Any]:
    form = await request.form()
    original = normalize_code(str(form.get("original_code", "")))
    revised = normalize_code(str(form.get("revised_code", "")))
    for source in (original, revised):
        if len(source) > 20000 or source.count("\n") > 1000 or any(len(line) > 2000 for line in source.split("\n")):
            raise HTTPException(422, "Use up to 20,000 characters, 1,000 lines, and 2,000 characters per line in each version.")
    aspect_ratio = str(form.get("aspect_ratio", DEFAULT_ASPECT_RATIO))
    width, height, aspect_ratio = _apply_code_aspect_ratio(aspect_ratio)
    return {
        "language": str(form.get("language","python")),
        "theme_name": str(form.get("theme_name","VS Code Dark+")), "original_code": original,
        "revised_code": revised, "font_family": str(form.get("font_family")) if form.get("font_family") in FONTS else FONTS[0],
        "font_size": _int(form.get("font_size"),20,12,32), "line_height": _float(form.get("line_height"),1.55,1.1,2.2),
        "aspect_ratio": aspect_ratio, "width": width, "height": height, "radius": _int(form.get("radius"),14,0,28),
        "transition_ms": _int(form.get("transition_ms"),650,240,1400), "hold_ms": _int(form.get("hold_ms"),1050,200,2400),
        "start_delay_ms": _int(form.get("start_delay_ms"),550,100,2500), "background_style": _background_style(form.get("background_style")),
        "gradient_name": str(form.get("gradient_name","midnight")), "canvas_padding": _int(form.get("canvas_padding"),92,18,180),
        "show_line_numbers": _bool(form.get("show_line_numbers")), "show_window_chrome": _bool(form.get("show_window_chrome")),
        "autoplay": _bool(form.get("autoplay")), "loop": _bool(form.get("loop")),
    }


def _diff_options_from_payload(values: dict[str, Any]):
    return make_diff_options(
        **{key: values[key] for key in (
            "language","theme_name","font_family","font_size","line_height","width","height","radius",
            "transition_ms","hold_ms","start_delay_ms","background_style","gradient_name","canvas_padding",
            "show_line_numbers","show_window_chrome","autoplay","loop"
        )}
    )


async def _terminal_payload_from_request(request: Request) -> dict[str, Any]:
    form = await request.form()
    aspect_ratio = str(form.get("aspect_ratio", "display"))
    width, height, aspect_ratio = _apply_terminal_aspect_ratio(aspect_ratio)
    return {
        "title": str(form.get("title", "Terminal"))[:80],
        "prompt": str(form.get("prompt", "%"))[:120],
        "command": str(form.get("command", ""))[:1000],
        "output": str(form.get("output", ""))[:6000],
        "word_speed_ms": _int(form.get("word_speed_ms"), 320, 80, 1200),
        "output_delay_ms": 1000,
        "aspect_ratio": aspect_ratio,
        "width": width,
        "height": height,
        "background_style": _background_style(form.get("background_style")),
        "gradient_name": str(form.get("gradient_name", "sunset")),
        "canvas_padding": _int(form.get("canvas_padding"), 52, 18, 180),
        "loop": _bool(form.get("loop")),
    }


def _terminal_options(values: dict[str, Any]) -> TerminalOptions:
    return TerminalOptions(**values)


async def _payload_from_request(request: Request) -> dict[str, Any]:
    form = await request.form()
    source = normalize_code(str(form.get("code", "")))
    if len(source) > 20000 or source.count("\n") > 1000 or any(len(line) > 2000 for line in source.split("\n")):
        raise HTTPException(422, "Use up to 20,000 characters, 1,000 lines, and 2,000 characters per line.")
    aspect_ratio = str(form.get("aspect_ratio", DEFAULT_ASPECT_RATIO))
    width, height, aspect_ratio = _apply_code_aspect_ratio(aspect_ratio)

    return {
        "language": str(form.get("language", "python")),
        "code": source,
        "theme_name": str(form.get("theme_name", "Light Studio")),
        "font_family": str(form.get("font_family")) if form.get("font_family") in FONTS else FONTS[0],
        "font_size": _int(form.get("font_size"), 18, 12, 32),
        "line_height": _float(form.get("line_height"), 1.55, 1.1, 2.2),
        "aspect_ratio": aspect_ratio,
        "width": width,
        "height": height,
        "radius": _int(form.get("radius"), 12, 0, 28),
        "speed_ms": _int(form.get("speed_ms"), 24, 4, 120),
        "line_pause_ms": _int(form.get("line_pause_ms"), 160, 0, 800),
        "start_delay_ms": _int(form.get("start_delay_ms"), 350, 0, 2500),
        "typing_mode": _typing_mode(form.get("typing_mode")),
        "background_style": _background_style(form.get("background_style")),
        "gradient_name": str(form.get("gradient_name", "sunset")),
        "canvas_padding": _int(form.get("canvas_padding"), 64, 18, 180),
        "show_line_numbers": _bool(form.get("show_line_numbers")),
        "show_diff_gutter": False,
        "show_window_chrome": _bool(form.get("show_window_chrome")),
        "autoplay": _bool(form.get("autoplay")),
        "loop": _bool(form.get("loop")),
        "cursor": str(form.get("cursor", "bar")),
        "gif_step": GIF_FRAME_STEP,
    }


def _options_from_payload(values: dict[str, Any]):
    return make_render_options(
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
        typing_mode=values["typing_mode"],
        background_style=values["background_style"],
        gradient_name=values["gradient_name"],
        canvas_padding=values["canvas_padding"],
        show_line_numbers=values["show_line_numbers"],
        show_diff_gutter=values["show_diff_gutter"],
        show_window_chrome=values["show_window_chrome"],
        autoplay=values["autoplay"],
        loop=values["loop"],
        cursor=values["cursor"],
    )


def _build_preview(values: dict[str, Any]) -> str:
    return build_typing_html(values.get("code", ""), _options_from_payload(values), standalone=False)


def _bool(value: Any) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def _typing_mode(value: Any) -> str:
    mode = str(value or "character").strip().lower()
    if mode in {item["value"] for item in TYPING_MODES}:
        return mode
    return "character"


def _background_style(value: Any) -> str:
    style = str(value or "none").strip().lower()
    if style in {"none", "gradient"}:
        return style
    return "none"


def _apply_code_aspect_ratio(aspect_ratio: str) -> tuple[int, int, str]:
    dimensions = CODE_ASPECT_RATIO_DIMENSIONS.get(aspect_ratio)
    if dimensions is None:
        fallback = CODE_ASPECT_RATIO_DIMENSIONS[DEFAULT_ASPECT_RATIO]
        return fallback[0], fallback[1], DEFAULT_ASPECT_RATIO
    return dimensions[0], dimensions[1], aspect_ratio


def _apply_terminal_aspect_ratio(aspect_ratio: str) -> tuple[int, int, str]:
    dimensions = TERMINAL_ASPECT_RATIO_DIMENSIONS.get(aspect_ratio)
    if dimensions is None:
        fallback = TERMINAL_ASPECT_RATIO_DIMENSIONS[DEFAULT_ASPECT_RATIO]
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
