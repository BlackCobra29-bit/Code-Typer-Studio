"""Syntax-aware, deterministic code-change composition."""
from __future__ import annotations

import html
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re

from .gradients import gradient_css
from .renderer import _embedded_font_css
from .syntax_style import editor_theme, highlight_code, normalize_code


BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DiffOptions:
    language: str = "python"
    theme_name: str = "VS Code Dark+"
    font_family: str = "JetBrains Mono, Consolas, monospace"
    font_size: int = 20
    line_height: float = 1.55
    width: int = 1280
    height: int = 720
    radius: int = 14
    transition_ms: int = 650
    hold_ms: int = 1050
    start_delay_ms: int = 550
    show_line_numbers: bool = True
    show_window_chrome: bool = True
    autoplay: bool = True
    loop: bool = False
    flush_frame: bool = False
    background_style: str = "gradient"
    gradient_name: str = "midnight"
    canvas_padding: int = 92


def make_diff_options(**values) -> DiffOptions:
    fields = DiffOptions.__dataclass_fields__
    return DiffOptions(**{key: value for key, value in values.items() if key in fields})


def build_diff_model(original: str, revised: str, options: DiffOptions) -> dict:
    original = normalize_code(original)
    revised = normalize_code(revised)
    before = highlight_code(original, options.language, options.theme_name)
    after = highlight_code(revised, options.language, options.theme_name)
    before_text = [] if original == "" else ["".join(token["content"] for token in line) for line in before["lines"]]
    after_text = [] if revised == "" else ["".join(token["content"] for token in line) for line in after["lines"]]
    matcher = SequenceMatcher(None, before_text, after_text, autojunk=False)
    rows: list[dict] = []

    def append(kind: str, old_index: int | None, new_index: int | None, silent_delete: bool = False):
        source = before if kind == "delete" else after
        source_index = old_index if kind == "delete" else new_index
        rows.append({
            "index": len(rows),
            "kind": kind,
            "oldNumber": old_index + 1 if old_index is not None else None,
            "newNumber": new_index + 1 if new_index is not None else None,
            "originalOrder": old_index if old_index is not None else -1,
            "finalOrder": new_index if new_index is not None else -1,
            "silentDelete": bool(silent_delete),
            "tokens": source["lines"][source_index] if source_index is not None else [],
        })

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2-i1):
                append("equal", i1+offset, j1+offset)
        elif tag == "delete":
            for old_index in range(i1, i2):
                append("delete", old_index, None)
        elif tag == "insert":
            for new_index in range(j1, j2):
                append("insert", None, new_index)
        else:
            has_nonempty_insert = any(after_text[index].strip() for index in range(j1, j2))
            for old_index in range(i1, i2):
                append(
                    "delete",
                    old_index,
                    None,
                    silent_delete=has_nonempty_insert and not before_text[old_index].strip(),
                )
            for new_index in range(j1, j2):
                append("insert", None, new_index)

    changed = [row for row in rows if row["kind"] != "equal"]
    for order, row in enumerate(changed):
        row["changeOrder"] = order
    for row in rows:
        row.setdefault("changeOrder", -1)

    timeline = _timeline(rows, options)
    return {
        "original": original,
        "revised": revised,
        "rows": rows,
        "timeline": timeline,
        "theme": editor_theme(after),
        "highlight": after,
        "additions": sum(row["kind"] == "insert" for row in rows),
        "deletions": sum(row["kind"] == "delete" and not row["silentDelete"] for row in rows),
    }


def build_diff_html(original: str, revised: str, options: DiffOptions, standalone: bool = False) -> str:
    model = build_diff_model(original, revised, options)
    theme = model["theme"]
    gradient = options.background_style == "gradient" and not options.flush_frame
    rows = "".join(_row_html(row, options) for row in model["rows"])
    payload = json.dumps({
        "timeline": model["timeline"],
        "rows": [{key: row[key] for key in ("index", "kind", "originalOrder", "finalOrder", "changeOrder", "silentDelete")} for row in model["rows"]],
        "width": options.width,
        "height": options.height,
        "fontSize": options.font_size,
        "lineHeight": options.line_height,
        "autoplay": options.autoplay,
        "loop": options.loop,
        "theme": model["highlight"]["theme"],
        "language": model["highlight"]["language"],
        "stats": {"additions": model["additions"], "deletions": model["deletions"]},
    }).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    document = (BASE_DIR / "src" / "diff_frame.html").read_text(encoding="utf-8")
    replacements = {
        "__ROWS__": rows,
        "__PAYLOAD__": payload,
        "__FONT_CSS__": _embedded_font_css(),
        "__FRAME_CSS__": (BASE_DIR / "static" / "diff_frame.css").read_text(encoding="utf-8"),
        "__FRAME_JS__": (BASE_DIR / "static" / "diff_frame.js").read_text(encoding="utf-8"),
        "__PAGE_BG__": theme["page_bg"],
        "__EDITOR_BG__": theme["editor_bg"],
        "__CHROME_BG__": theme["chrome_bg"],
        "__TEXT__": theme["text"],
        "__MUTED__": theme["muted"],
        "__ACCENT__": theme["accent"],
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
    body_class = "flush-frame" if options.flush_frame else ""
    if not standalone:
        body_class = f"embedded {body_class}".strip()
    return document.replace("<body>", f'<body class="{body_class}">')


def export_diff_project(original: str, revised: str, options: DiffOptions) -> str:
    return json.dumps({"app": "Code Typer Studio", "type": "code-diff", "version": 1,
                       "original": normalize_code(original), "revised": normalize_code(revised),
                       "options": asdict(options)}, indent=2)


def _timeline(rows: list[dict], options: DiffOptions) -> dict:
    transition = _clamp(options.transition_ms, 240, 1400)
    hold = _clamp(options.hold_ms, 200, 2400)
    start = _clamp(options.start_delay_ms, 100, 2500)
    original_count = max((row["originalOrder"] for row in rows), default=-1) + 1
    stagger = max(24, min(70, 620 / max(1, original_count)))
    reveal_end = start + max(280, (original_count-1)*stagger + 260)
    change_start = reveal_end + hold*.55
    delete_end = change_start + transition
    insert_start = change_start + transition*.38
    insert_end = insert_start + transition
    resolve_start = max(delete_end, insert_end) + hold
    resolve_end = resolve_start + transition
    duration = resolve_end + hold + 650
    return {key: round(value, 3) for key, value in {
        "startDelay": start, "lineStagger": stagger, "revealEnd": reveal_end,
        "changeStart": change_start, "deleteEnd": delete_end, "insertStart": insert_start,
        "insertEnd": insert_end, "resolveStart": resolve_start, "resolveEnd": resolve_end,
        "duration": duration,
        "transition": transition,
    }.items()}


def _row_html(row: dict, options: DiffOptions) -> str:
    tokens = []
    for token in row["tokens"]:
        style = f'color:{token["color"]};'
        flags = token["fontStyle"]
        if flags & 1: style += "font-style:italic;"
        if flags & 2: style += "font-weight:700;"
        if flags & 4: style += "text-decoration:underline;"
        tokens.append(f'<span class="syntax-token" style="{style}">{html.escape(token["content"])}</span>')
    old_number = row["oldNumber"] if options.show_line_numbers and row["oldNumber"] else ""
    new_number = row["newNumber"] if options.show_line_numbers and row["newNumber"] else ""
    silent_delete = row["silentDelete"]
    marker = "" if silent_delete else {"delete": "−", "insert": "+"}.get(row["kind"], "")
    row_class = f'diff-row row-{row["kind"]}' + (" row-silent-delete" if silent_delete else "")
    return (
        f'<div class="{row_class}" data-index="{row["index"]}" data-kind="{row["kind"]}">'
        f'<span class="change-rail"></span><span class="diff-marker">{marker}</span>'
        f'<span class="line-number old-number">{old_number}</span><span class="line-number new-number">{new_number}</span>'
        f'<span class="code-text">{"".join(tokens)}</span><span class="delete-strike"></span></div>'
    )


def _canvas_padding(options: DiffOptions) -> int:
    high = max(18, int(min(options.width, options.height)*.18))
    return _clamp(options.canvas_padding, 18, high)


def _clamp(value, low, high):
    return max(low, min(high, int(value)))


def _clamp_float(value, low, high):
    return max(low, min(high, float(value)))
