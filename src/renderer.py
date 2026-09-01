from __future__ import annotations

import base64
import html
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import re

from .gradients import gradient_css
from .languages import (
    ICON_BY_EXTENSION,
    ICON_BY_FILENAME,
    ICON_BY_LANGUAGE,
)
from .syntax_style import highlight_code, editor_theme
from .typing_timeline import build_timeline


BASE_DIR = Path(__file__).resolve().parents[1]
ICON_DIR = BASE_DIR / "static" / "icons"

@dataclass(frozen=True)
class RenderOptions:
    title: str = "code-typer-studio"
    language: str = "python"
    theme_name: str = "VS Code Dark+"
    font_family: str = "JetBrains Mono, Consolas, monospace"
    font_size: int = 18
    line_height: float = 1.55
    width: int = 1040
    height: int = 620
    radius: int = 10
    speed_ms: int = 24
    line_pause_ms: int = 160
    start_delay_ms: int = 350
    typing_mode: str = "character"
    show_line_numbers: bool = True
    show_diff_gutter: bool = False
    show_window_chrome: bool = True
    autoplay: bool = True
    loop: bool = False
    cursor: str = "bar"
    flush_frame: bool = False
    background_style: str = "none"
    gradient_name: str = "sunset"
    canvas_padding: int = 64


def make_render_options(**values: Any) -> RenderOptions:
    fields = RenderOptions.__dataclass_fields__
    clean = {key: value for key, value in values.items() if key in fields}
    return RenderOptions(**clean)


def build_typing_html(code: str, options: RenderOptions, standalone: bool = False) -> str:
    highlighted = highlight_code(code, options.language, options.theme_name, options.title)
    theme = editor_theme(highlighted)
    timeline = build_timeline(highlighted, options)
    gradient_enabled = _gradient_enabled(options)
    code_lines = _highlighted_code_lines(highlighted, options)
    data = json.dumps(
        {
            "speedMs": _clamp(options.speed_ms, 4, 250),
            "linePauseMs": _clamp(options.line_pause_ms, 0, 1200),
            "startDelayMs": _clamp(options.start_delay_ms, 0, 5000),
            "typingMode": _typing_mode(options.typing_mode),
            "autoplay": options.autoplay,
            "loop": options.loop,
            "cursor": options.cursor,
            "timeline": timeline,
            "language": highlighted["language"],
            "theme": highlighted["theme"],
            "width": options.width,
            "height": options.height,
        }
    )

    document = (BASE_DIR / "src" / "typing_frame.html").read_text(encoding="utf-8")
    replacements = {
        "__TITLE__": html.escape(options.title or "code-typer-studio"),
        "__FILE_ICON_SRC__": html.escape(_file_icon_src(options.title, options.language), quote=True),
        "__FILE_ICON_ALT__": html.escape(_file_icon_alt(options.title, options.language), quote=True),
        "__CODE_LINES__": code_lines,
        "__FONT_CSS__": _embedded_font_css(),
        "__FRAME_CSS__": (BASE_DIR / "static" / "typing_frame.css").read_text(encoding="utf-8"),
        "__FRAME_JS__": (BASE_DIR / "static" / "typing_frame.js").read_text(encoding="utf-8"),
        "__LANGUAGE__": html.escape(highlighted["language"]),
        "__THEME__": html.escape(options.theme_name),
        "__NUMBER_WIDTH__": "54px" if options.show_line_numbers else "18px",
        "__DIFF_WIDTH__": "24px" if options.show_diff_gutter else "0px",
        "__OPTIONS_JSON__": data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"),
        "__PAGE_BG__": theme["page_bg"],
        "__EDITOR_BG__": theme["editor_bg"],
        "__CHROME_BG__": theme["chrome_bg"],
        "__TEXT__": theme["text"],
        "__MUTED__": theme["muted"],
        "__ACTIVE__": theme["active"],
        "__ACCENT__": theme["accent"],
        "__BORDER__": theme["border"],
        "__PLUS__": theme["plus"],
        "__FONT_FAMILY__": html.escape(options.font_family),
        "__FONT_SIZE__": f"{_clamp(options.font_size, 10, 42)}px",
        "__LINE_HEIGHT__": str(_clamp_float(options.line_height, 1.0, 2.5)),
        "__WIDTH__": f"{_clamp(options.width, 420, 2200)}px",
        "__HEIGHT__": f"{_clamp(options.height, 260, 1400)}px",
        "__RADIUS__": f"{_clamp(options.radius, 0, 32)}px",
        "__CANVAS_FILL__": gradient_css(options.gradient_name) if gradient_enabled else theme["page_bg"],
        "__SHELL_PADDING__": f"{_canvas_padding(options)}px" if gradient_enabled else "0px",
        "__STAGE_CLASS__": "gradient-frame" if gradient_enabled else "plain-frame",
        "__CURSOR_CLASS__": f"cursor-{_cursor_class(options.cursor)}",
        "__CHROME_DISPLAY__": "flex" if options.show_window_chrome else "none",
    }

    # One substitution pass prevents source text from being interpreted as template markers.
    document = re.sub(r"__[A-Z_]+__", lambda match: replacements.get(match[0], match[0]), document)

    if standalone:
        if options.flush_frame:
            document = document.replace("<body>", '<body class="flush-frame">')
        return document

    return (
        document.replace('<html lang="en">', '<html lang="en" class="embedded-root">')
        .replace("<body>", '<body class="embedded">')
    )


def export_project_json(code: str, options: RenderOptions) -> str:
    return json.dumps(
        {
            "app": "Code Typer Studio",
            "version": 1,
            "code": code,
            "options": options.__dict__,
        },
        indent=2,
    )


def _highlighted_code_lines(highlighted: dict, options: RenderOptions) -> str:
    rendered, index = [], 0
    for line_no, tokens in enumerate(highlighted["lines"]):
        content = []
        for token in tokens:
            style = f'color:{token["color"]};'
            flags = token["fontStyle"]
            if flags & 1:
                style += 'font-style:italic;'
            if flags & 2:
                style += 'font-weight:700;'
            if flags & 4:
                style += 'text-decoration:underline;'
            glyphs = []
            for char in token["content"]:
                glyphs.append(f'<span class="glyph" data-index="{index}">{html.escape(char)}</span>')
                index += 1
            content.append(f'<span class="syntax-token" style="{style}">{"".join(glyphs)}</span>')
        number = str(line_no + 1) if options.show_line_numbers else ''
        diff = '+' if options.show_diff_gutter else ''
        rendered.append(f'<div class="code-line" data-line="{line_no}"><span class="diff-mark">{diff}</span>'
                        f'<span class="line-number">{number}</span><span class="line-content">{"".join(content)}</span></div>')
        index += 1  # newline exists in the timeline, not as a visible DOM glyph
    return ''.join(rendered)


def _cursor_class(cursor: str) -> str:
    if cursor in {"block", "underline"}:
        return cursor
    return "bar"


def _typing_mode(mode: str) -> str:
    if mode in {"word", "line", "token"}:
        return mode
    return "character"


def _gradient_enabled(options: RenderOptions) -> bool:
    return str(options.background_style).lower() == "gradient" and not options.flush_frame


def _canvas_padding(options: RenderOptions) -> int:
    size_bound = min(_clamp(options.width, 420, 2200), _clamp(options.height, 260, 1400))
    high = max(18, int(size_bound * 0.18))
    return _clamp(options.canvas_padding, 18, high)


def _file_icon_alt(title: str, language: str) -> str:
    filename = Path(title or "").name
    if filename.lower() in ICON_BY_FILENAME:
        return f"{filename} file icon"

    extension = Path(title or "").suffix.lower().lstrip(".")
    if extension:
        return f"{extension} file icon"
    return f"{(language or 'code').strip()} file icon"


def _file_icon_src(title: str, language: str) -> str:
    icon_name = _file_icon_name(title, language)
    return _svg_data_uri(icon_name)


def _file_icon_name(title: str, language: str) -> str:
    filename = Path(title or "").name.lower()
    if filename in ICON_BY_FILENAME:
        return ICON_BY_FILENAME[filename]

    extension = Path(title or "").suffix.lower()
    if extension in ICON_BY_EXTENSION:
        return ICON_BY_EXTENSION[extension]

    return ICON_BY_LANGUAGE.get((language or "").strip().lower(), "json.svg")


@lru_cache(maxsize=None)
def _svg_data_uri(icon_name: str) -> str:
    icon_path = ICON_DIR / icon_name
    if not icon_path.is_file():
        icon_path = ICON_DIR / "json.svg"
    encoded = base64.b64encode(icon_path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))




@lru_cache(maxsize=1)
def _embedded_font_css() -> str:
    license_path = BASE_DIR / "static" / "fonts" / "OFL.txt"
    license_text = license_path.read_text(encoding="utf-8").replace('*/', '* /')
    rules = [f'/* Bundled JetBrains Mono font license:\n{license_text}\n*/']
    for suffix, weight, style in [("Regular", 400, "normal"), ("Bold", 700, "normal"), ("Italic", 400, "italic"), ("BoldItalic", 700, "italic")]:
        path = BASE_DIR / "static" / "fonts" / f"JetBrainsMono-{suffix}.ttf"
        if path.exists():
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            rules.append(f"@font-face{{font-family:'JetBrains Mono';font-weight:{weight};font-style:{style};src:url(data:font/ttf;base64,{data}) format('truetype');}}")
    return "\n".join(rules)
