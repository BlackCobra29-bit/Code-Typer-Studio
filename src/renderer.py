from __future__ import annotations

import base64
import html
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from .syntax_style import syntax_css
from .themes import THEMES


BASE_DIR = Path(__file__).resolve().parents[1]
ICON_DIR = BASE_DIR / "static" / "icons"

ICON_BY_EXTENSION = {
    ".bash": "bash.svg",
    ".c": "cplusplus.svg",
    ".cc": "cplusplus.svg",
    ".cpp": "cplusplus.svg",
    ".cs": "csharp.svg",
    ".css": "css.svg",
    ".go": "go.svg",
    ".h": "cplusplus.svg",
    ".hpp": "cplusplus.svg",
    ".html": "html.svg",
    ".java": "java.svg",
    ".javascript": "javascript.svg",
    ".js": "javascript.svg",
    ".json": "json.svg",
    ".jsx": "react.svg",
    ".kt": "kotlin.svg",
    ".kts": "kotlin.svg",
    ".php": "php.svg",
    ".python": "python.svg",
    ".py": "python.svg",
    ".rb": "ruby.svg",
    ".rs": "rust.svg",
    ".rust": "rust.svg",
    ".sh": "bash.svg",
    ".sql": "postgresql.svg",
    ".swift": "swift.svg",
    ".ts": "typescript.svg",
    ".typescript": "typescript.svg",
    ".tsx": "react.svg",
    ".yaml": "yaml.svg",
    ".yml": "yaml.svg",
}

ICON_BY_LANGUAGE = {
    "bash": "bash.svg",
    "cpp": "cplusplus.svg",
    "csharp": "csharp.svg",
    "css": "css.svg",
    "go": "go.svg",
    "html": "html.svg",
    "java": "java.svg",
    "javascript": "javascript.svg",
    "json": "json.svg",
    "jsx": "react.svg",
    "kotlin": "kotlin.svg",
    "php": "php.svg",
    "python": "python.svg",
    "ruby": "ruby.svg",
    "rust": "rust.svg",
    "sql": "postgresql.svg",
    "swift": "swift.svg",
    "tsx": "react.svg",
    "typescript": "typescript.svg",
    "yaml": "yaml.svg",
}


@dataclass(frozen=True)
class RenderOptions:
    title: str = "code-typer-studio"
    language: str = "python"
    theme_name: str = "VS Code Dark+"
    font_family: str = "Cascadia Code, Fira Code, Consolas, monospace"
    font_size: int = 18
    line_height: float = 1.55
    width: int = 1040
    height: int = 620
    radius: int = 10
    speed_ms: int = 24
    line_pause_ms: int = 160
    start_delay_ms: int = 350
    show_line_numbers: bool = True
    show_diff_gutter: bool = True
    show_window_chrome: bool = True
    autoplay: bool = True
    loop: bool = False
    cursor: str = "bar"


def make_render_options(**values: Any) -> RenderOptions:
    fields = RenderOptions.__dataclass_fields__
    clean = {key: value for key, value in values.items() if key in fields}
    return RenderOptions(**clean)


def build_typing_html(code: str, options: RenderOptions, standalone: bool = False) -> str:
    theme = THEMES.get(options.theme_name, THEMES["VS Code Dark+"])
    code_lines = _highlighted_code_lines(
        code=code,
        language=options.language,
        show_line_numbers=options.show_line_numbers,
        show_diff_gutter=options.show_diff_gutter,
    )
    data = json.dumps(
        {
            "speedMs": _clamp(options.speed_ms, 4, 250),
            "linePauseMs": _clamp(options.line_pause_ms, 0, 1200),
            "startDelayMs": _clamp(options.start_delay_ms, 0, 5000),
            "autoplay": options.autoplay,
            "loop": options.loop,
        }
    )

    document = HTML_TEMPLATE
    replacements = {
        "__TITLE__": html.escape(options.title or "code-typer-studio"),
        "__FILE_ICON_SRC__": html.escape(_file_icon_src(options.title, options.language), quote=True),
        "__FILE_ICON_ALT__": html.escape(_file_icon_alt(options.title, options.language), quote=True),
        "__CODE_LINES__": code_lines,
        "__PYGMENTS_CSS__": syntax_css(options.theme_name),
        "__OPTIONS_JSON__": html.escape(data, quote=False),
        "__PAGE_BG__": theme["page_bg"],
        "__EDITOR_BG__": theme["editor_bg"],
        "__CHROME_BG__": theme["chrome_bg"],
        "__GUTTER_BG__": theme["gutter_bg"],
        "__TEXT__": theme["text"],
        "__MUTED__": theme["muted"],
        "__ACTIVE__": theme["active"],
        "__ACCENT__": theme["accent"],
        "__BORDER__": theme["border"],
        "__SHADOW__": theme["shadow"],
        "__PLUS__": theme["plus"],
        "__FONT_FAMILY__": html.escape(options.font_family),
        "__FONT_SIZE__": f"{_clamp(options.font_size, 10, 42)}px",
        "__LINE_HEIGHT__": str(_clamp_float(options.line_height, 1.0, 2.5)),
        "__WIDTH__": f"{_clamp(options.width, 420, 2200)}px",
        "__HEIGHT__": f"{_clamp(options.height, 260, 1400)}px",
        "__RADIUS__": f"{_clamp(options.radius, 0, 32)}px",
        "__CURSOR_CLASS__": f"cursor-{_cursor_class(options.cursor)}",
        "__CHROME_DISPLAY__": "flex" if options.show_window_chrome else "none",
        "__VIEWPORT_HEIGHT__": "calc(100% - 42px)" if options.show_window_chrome else "100%",
    }

    for token, value in replacements.items():
        document = document.replace(token, value)

    if standalone:
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


def _highlighted_code_lines(
    code: str,
    language: str,
    show_line_numbers: bool,
    show_diff_gutter: bool,
) -> str:
    lexer = _lexer(language)
    highlighted = highlight(code or " ", lexer, HtmlFormatter(nowrap=True))
    lines = highlighted.split("\n")
    raw_count = max(1, len((code or " ").split("\n")))
    if len(lines) > raw_count and lines[-1] == "":
        lines = lines[:-1]
    while len(lines) < raw_count:
        lines.append("")

    rendered = []
    for index, line in enumerate(lines[:raw_count], start=1):
        if line == "":
            line = "&nbsp;"
        line_number = str(index) if show_line_numbers else ""
        diff_mark = "+" if show_diff_gutter else ""
        rendered.append(
            '<div class="code-line" data-line="{line_no}">'
            '<span class="diff-mark">{diff}</span>'
            '<span class="line-number">{number}</span>'
            '<span class="line-content">{content}</span>'
            "</div>".format(
                line_no=index,
                diff=html.escape(diff_mark),
                number=html.escape(line_number),
                content=line,
            )
        )
    return "\n".join(rendered)


def _lexer(language: str):
    try:
        return get_lexer_by_name(language.strip() or "text")
    except ClassNotFound:
        return TextLexer()


def _cursor_class(cursor: str) -> str:
    if cursor in {"block", "underline"}:
        return cursor
    return "bar"


def _file_icon_alt(title: str, language: str) -> str:
    extension = Path(title or "").suffix.lower().lstrip(".")
    if extension:
        return f"{extension} file icon"
    return f"{(language or 'code').strip()} file icon"


def _file_icon_src(title: str, language: str) -> str:
    icon_name = _file_icon_name(title, language)
    return _svg_data_uri(icon_name)


def _file_icon_name(title: str, language: str) -> str:
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


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
__PYGMENTS_CSS__

:root {
  --page-bg: __PAGE_BG__;
  --editor-bg: __EDITOR_BG__;
  --chrome-bg: __CHROME_BG__;
  --gutter-bg: __GUTTER_BG__;
  --text: __TEXT__;
  --muted: __MUTED__;
  --active: __ACTIVE__;
  --accent: __ACCENT__;
  --border: __BORDER__;
  --shadow: __SHADOW__;
  --plus: __PLUS__;
  --font-family: __FONT_FAMILY__;
  --font-size: __FONT_SIZE__;
  --line-height: __LINE_HEIGHT__;
  --stage-width: __WIDTH__;
  --stage-height: __HEIGHT__;
  --radius: __RADIUS__;
}

* {
  box-sizing: border-box;
}

.embedded-root {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--page-bg);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body.embedded {
  display: block;
  width: 100vw;
  height: 100vh;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  background: transparent;
}

.stage-shell {
  width: min(100%, var(--stage-width));
  padding: 18px;
}

body.embedded .stage-shell {
  width: 100%;
  height: 100%;
  padding: 0;
}

.editor-window {
  width: 100%;
  height: var(--stage-height);
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--editor-bg);
  box-shadow: 0 28px 80px var(--shadow);
}

body.embedded .editor-window {
  height: 100%;
  border: 0;
  box-shadow: none;
}

.window-chrome {
  display: __CHROME_DISPLAY__;
  align-items: center;
  gap: 10px;
  height: 42px;
  padding: 0 14px;
  background: var(--chrome-bg);
  border-bottom: 1px solid var(--border);
}

.window-dots {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.dot {
  width: 11px;
  height: 11px;
  border-radius: 999px;
}

.dot.red { background: #ff5f56; }
.dot.yellow { background: #ffbd2e; }
.dot.green { background: #27c93f; }

.file-title {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
  margin-left: 10px;
  color: #d8d7df;
  font-size: 18px;
  font-weight: 600;
  line-height: 1;
}

.file-icon {
  width: 19px;
  height: 19px;
  flex: 0 0 auto;
  object-fit: contain;
}

.file-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.code-viewport {
  height: __VIEWPORT_HEIGHT__;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--editor-bg);
  scrollbar-width: thin;
  scrollbar-color: color-mix(in srgb, var(--muted) 70%, transparent) transparent;
}

.code-viewport::-webkit-scrollbar {
  width: 8px;
  height: 0;
}

.code-viewport::-webkit-scrollbar-track {
  background: transparent;
}

.code-viewport::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 62%, transparent);
}

.code-content {
  min-width: max-content;
  padding: 18px 0 24px;
  color: var(--text);
  font-family: var(--font-family);
  font-size: var(--font-size);
  line-height: var(--line-height);
  white-space: pre;
}

.code-line {
  display: grid;
  grid-template-columns: 28px 54px minmax(0, 1fr);
  min-height: calc(var(--font-size) * var(--line-height));
  transition: background-color 120ms ease;
}

.code-line.active {
  background: var(--active);
}

.diff-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--plus);
  background: var(--gutter-bg);
  opacity: 0;
  transition: opacity 120ms ease;
  user-select: none;
}

.line-number {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 18px;
  color: var(--muted);
  background: var(--gutter-bg);
  opacity: 0;
  transition: opacity 120ms ease;
  user-select: none;
}

.code-line.line-started .diff-mark,
.code-line.line-started .line-number {
  opacity: 1;
}

.line-content {
  padding-left: 18px;
  padding-right: 32px;
}

.typing-char {
  opacity: 0;
}

.typing-char.visible {
  opacity: 1;
}

.typing-cursor {
  display: inline-block;
  vertical-align: -0.12em;
  background: var(--accent);
  animation: blink 0.9s steps(2, start) infinite;
}

.cursor-bar .typing-cursor {
  width: 2px;
  height: 1.18em;
  margin-left: 1px;
}

.cursor-block .typing-cursor {
  width: 0.62em;
  height: 1.08em;
  margin-left: 1px;
}

.cursor-underline .typing-cursor {
  width: 0.68em;
  height: 0.14em;
  margin-left: 1px;
}

.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--chrome-bg) 92%, transparent);
  border-top: 1px solid var(--border);
}

.controls button {
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 7px 10px;
  background: var(--editor-bg);
  color: var(--text);
  cursor: pointer;
}

.controls button:hover {
  border-color: var(--accent);
}

.progress {
  flex: 1;
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--border);
}

.progress-fill {
  width: 0%;
  height: 100%;
  background: var(--accent);
  transition: width 80ms linear;
}

@keyframes blink {
  50% { opacity: 0; }
}
</style>
</head>
<body>
<main class="stage-shell">
  <section class="editor-window __CURSOR_CLASS__" aria-label="Animated code preview">
    <div class="window-chrome">
      <span class="window-dots">
        <span class="dot red"></span>
        <span class="dot yellow"></span>
        <span class="dot green"></span>
      </span>
      <span class="file-title">
        <img class="file-icon" src="__FILE_ICON_SRC__" alt="__FILE_ICON_ALT__">
        <span class="file-name">__TITLE__</span>
      </span>
    </div>
    <div class="code-viewport" id="viewport">
      <pre class="code-content" id="codeContent">__CODE_LINES__</pre>
    </div>
    <div class="controls">
      <button type="button" id="playPause">Pause</button>
      <button type="button" id="restart">Restart</button>
      <div class="progress" aria-hidden="true"><div class="progress-fill" id="progressFill"></div></div>
    </div>
  </section>
</main>
<script type="application/json" id="typingOptions">__OPTIONS_JSON__</script>
<script>
(() => {
  const options = JSON.parse(document.getElementById("typingOptions").textContent);
  const root = document.getElementById("codeContent");
  const viewport = document.getElementById("viewport");
  const playPause = document.getElementById("playPause");
  const restart = document.getElementById("restart");
  const progressFill = document.getElementById("progressFill");
  const cursor = document.createElement("span");

  cursor.className = "typing-cursor";

  function wrapTextNodes(node) {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.TEXT_NODE) {
        const text = child.nodeValue || "";
        const fragment = document.createDocumentFragment();
        for (const char of text) {
          const span = document.createElement("span");
          span.className = "typing-char";
          span.textContent = char;
          fragment.appendChild(span);
        }
        child.replaceWith(fragment);
      } else if (child.nodeType === Node.ELEMENT_NODE && !child.classList.contains("typing-cursor")) {
        wrapTextNodes(child);
      }
    }
  }

  root.querySelectorAll(".line-content").forEach(wrapTextNodes);

  const chars = Array.from(root.querySelectorAll(".line-content .typing-char"));
  let index = 0;
  let timer = null;
  let playing = false;

  function setActiveLine(line) {
    root.querySelectorAll(".code-line.active").forEach((item) => item.classList.remove("active"));
    if (line) {
      line.classList.add("active");
      line.classList.add("line-started");
    }
  }

  function keepCursorInView(line) {
    const top = line ? line.offsetTop - viewport.clientHeight * 0.45 : viewport.scrollTop;
    const left = cursor.offsetLeft - viewport.clientWidth * 0.72;
    viewport.scrollTo({
      top: Math.max(0, top),
      left: Math.max(0, left),
      behavior: "smooth",
    });
  }

  function placeCursor() {
    let activeLine = null;
    if (chars.length === 0) {
      root.appendChild(cursor);
      keepCursorInView(null);
      return;
    }

    if (index <= 0) {
      chars[0].before(cursor);
      activeLine = chars[0].closest(".code-line");
    } else {
      const previous = chars[Math.min(index - 1, chars.length - 1)];
      previous.after(cursor);
      activeLine = previous.closest(".code-line");
    }
    setActiveLine(activeLine);
    keepCursorInView(activeLine);
  }

  function updateProgress() {
    const pct = chars.length === 0 ? 100 : Math.round((index / chars.length) * 100);
    progressFill.style.width = `${pct}%`;
  }

  function nextDelay() {
    const current = chars[index - 1];
    const next = chars[index];
    if (!current || !next) {
      return options.speedMs;
    }
    return current.closest(".code-line") === next.closest(".code-line")
      ? options.speedMs
      : options.speedMs + options.linePauseMs;
  }

  function tick() {
    if (!playing) {
      return;
    }

    if (index >= chars.length) {
      updateProgress();
      if (options.loop) {
        timer = window.setTimeout(resetAndPlay, 900);
      } else {
        playing = false;
        playPause.textContent = "Play";
      }
      return;
    }

    chars[index].classList.add("visible");
    index += 1;
    placeCursor();
    updateProgress();
    timer = window.setTimeout(tick, nextDelay());
  }

  function play() {
    if (playing) {
      return;
    }
    playing = true;
    playPause.textContent = "Pause";
    timer = window.setTimeout(tick, index === 0 ? options.startDelayMs : options.speedMs);
  }

  function pause() {
    playing = false;
    playPause.textContent = "Play";
    window.clearTimeout(timer);
  }

  function reset() {
    pause();
    index = 0;
    chars.forEach((char) => char.classList.remove("visible"));
    root.querySelectorAll(".code-line.line-started").forEach((line) => line.classList.remove("line-started"));
    placeCursor();
    updateProgress();
  }

  function resetAndPlay() {
    reset();
    play();
  }

  playPause.addEventListener("click", () => {
    if (playing) {
      pause();
    } else {
      play();
    }
  });

  restart.addEventListener("click", resetAndPlay);

  reset();
  if (options.autoplay) {
    play();
  }
})();
</script>
</body>
</html>
"""
