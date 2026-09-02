"""Syntax-aware, deterministic code-scroll composition."""
from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .gradients import gradient_css
from .renderer import _embedded_font_css
from .syntax_style import editor_theme, highlight_code, normalize_code


BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ScrollOptions:
    language: str = "javascript"
    theme_name: str = "VS Code Dark+"
    font_family: str = "JetBrains Mono, Consolas, monospace"
    font_size: int = 20
    line_height: float = 1.55
    width: int = 1280
    height: int = 720
    radius: int = 14
    target_start: int = 12
    target_end: int = 12
    scroll_ms: int = 1700
    hold_ms: int = 1500
    start_delay_ms: int = 900
    show_line_numbers: bool = True
    show_window_chrome: bool = True
    autoplay: bool = True
    loop: bool = False
    background_style: str = "gradient"
    gradient_name: str = "midnight"
    canvas_padding: int = 92


def make_scroll_options(**values) -> ScrollOptions:
    fields = ScrollOptions.__dataclass_fields__
    return ScrollOptions(**{key: value for key, value in values.items() if key in fields})


def build_scroll_model(code: str, options: ScrollOptions) -> dict:
    code = normalize_code(code)
    highlighted = highlight_code(code, options.language, options.theme_name)
    line_count = max(1, len(highlighted["lines"]))
    start = _clamp(options.target_start, 1, line_count)
    end = _clamp(options.target_end, 1, line_count)
    start, end = min(start, end), max(start, end)
    theme = editor_theme(highlighted)
    return {
        "code": code,
        "highlight": highlighted,
        "theme": theme,
        "focusColor": highlighted["colors"].get(
            "editor.selectionBackground",
            highlighted["colors"].get("editor.selectionHighlightBackground", theme["accent"]),
        ),
        "lineCount": line_count,
        "targetStart": start,
        "targetEnd": end,
        "timeline": _timeline(options),
    }


def build_scroll_html(code: str, options: ScrollOptions, standalone: bool = False) -> str:
    model = build_scroll_model(code, options)
    theme = model["theme"]
    lines = "".join(_line_html(tokens, index + 1, model, options) for index, tokens in enumerate(model["highlight"]["lines"]))
    if not lines:
        lines = _line_html([], 1, model, options)
    payload = json.dumps({
        "timeline": model["timeline"],
        "targetStart": model["targetStart"],
        "targetEnd": model["targetEnd"],
        "lineCount": model["lineCount"],
        "width": options.width,
        "height": options.height,
        "fontSize": options.font_size,
        "lineHeight": options.line_height,
        "autoplay": options.autoplay,
        "loop": options.loop,
        "language": model["highlight"]["language"],
        "theme": model["highlight"]["theme"],
    }).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    gradient = options.background_style == "gradient"
    document = (BASE_DIR / "src" / "scroll_frame.html").read_text(encoding="utf-8")
    replacements = {
        "__CODE_LINES__": lines,
        "__PAYLOAD__": payload,
        "__FONT_CSS__": _embedded_font_css(),
        "__FRAME_CSS__": (BASE_DIR / "static" / "scroll_frame.css").read_text(encoding="utf-8"),
        "__FRAME_JS__": (BASE_DIR / "static" / "scroll_frame.js").read_text(encoding="utf-8"),
        "__PAGE_BG__": theme["page_bg"],
        "__EDITOR_BG__": theme["editor_bg"],
        "__CHROME_BG__": theme["chrome_bg"],
        "__TEXT__": theme["text"],
        "__MUTED__": theme["muted"],
        "__ACCENT__": theme["accent"],
        "__FOCUS__": model["focusColor"],
        "__FONT_FAMILY__": html.escape(options.font_family),
        "__FONT_SIZE__": f"{_clamp(options.font_size, 10, 42)}px",
        "__LINE_HEIGHT__": str(_clamp_float(options.line_height, 1.1, 2.3)),
        "__NUMBER_WIDTH__": "54px" if options.show_line_numbers else "18px",
        "__WIDTH__": f"{_clamp(options.width, 420, 2200)}px",
        "__HEIGHT__": f"{_clamp(options.height, 260, 1400)}px",
        "__RADIUS__": f"{_clamp(options.radius, 0, 32)}px",
        "__CANVAS_FILL__": gradient_css(options.gradient_name) if gradient else theme["page_bg"],
        "__CANVAS_PADDING__": f"{_canvas_padding(options)}px" if gradient else "0px",
        "__STAGE_CLASS__": "gradient-frame" if gradient else "plain-frame",
        "__CHROME_DISPLAY__": "flex" if options.show_window_chrome else "none",
    }
    document = re.sub(r"__[A-Z_]+__", lambda match: replacements.get(match[0], match[0]), document)
    if not standalone:
        document = document.replace("<body>", '<body class="embedded">')
    return document


def export_scroll_project(code: str, options: ScrollOptions) -> str:
    model = build_scroll_model(code, options)
    values = asdict(options)
    values["target_start"], values["target_end"] = model["targetStart"], model["targetEnd"]
    return json.dumps({
        "app": "Coduxum", "type": "code-scroll", "version": 1,
        "code": model["code"], "options": values,
    }, indent=2)


def _timeline(options: ScrollOptions) -> dict:
    start = _clamp(options.start_delay_ms, 250, 3000)
    scroll = _clamp(options.scroll_ms, 450, 3200)
    hold = _clamp(options.hold_ms, 300, 3000)
    scroll_end = start + scroll
    focus_start = scroll_end - min(380, scroll * .24)
    focus_end = focus_start + min(500, max(280, scroll * .32))
    duration = max(scroll_end, focus_end) + hold + 650
    return {key: round(value, 3) for key, value in {
        "startDelay": start, "scrollStart": start, "scrollEnd": scroll_end,
        "focusStart": focus_start, "focusEnd": focus_end, "duration": duration,
    }.items()}


def _line_html(tokens: list[dict], number: int, model: dict, options: ScrollOptions) -> str:
    content = []
    for token in tokens:
        style = f'color:{token["color"]};'
        flags = token["fontStyle"]
        if flags & 1: style += "font-style:italic;"
        if flags & 2: style += "font-weight:700;"
        if flags & 4: style += "text-decoration:underline;"
        content.append(f'<span class="syntax-token" style="{style}">{html.escape(token["content"])}</span>')
    selected = model["targetStart"] <= number <= model["targetEnd"]
    visible_number = number if options.show_line_numbers else ""
    return (
        f'<div class="scroll-line{" target-line" if selected else ""}" data-line="{number}">'
        f'<span class="line-number">{visible_number}</span>'
        f'<span class="line-content">{"".join(content)}</span></div>'
    )


def _canvas_padding(options: ScrollOptions) -> int:
    high = max(18, int(min(options.width, options.height) * .18))
    return _clamp(options.canvas_padding, 18, high)


def _clamp(value, low, high):
    return max(low, min(high, int(value)))


def _clamp_float(value, low, high):
    return max(low, min(high, float(value)))
