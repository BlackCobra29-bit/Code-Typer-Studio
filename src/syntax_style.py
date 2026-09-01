"""TextMate token colors from pinned Shiki. No hand-written syntax palettes."""
from __future__ import annotations

import json
import re
import atexit
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from threading import Lock, Thread
from queue import Queue, Empty
from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
from .languages import LANGUAGE_CATALOG

DEFAULT_THEME = "VS Code Dark+"
THEME_NAMES = {
    "VS Code Dark+": "dark-plus", "VS Code Light+": "light-plus",
    "Dracula": "dracula", "GitHub Dark": "github-dark", "GitHub Light": "github-light",
    "Monokai": "monokai", "Material Ocean": "material-theme-ocean",
    "Palenight": "material-theme-palenight", "One Dark Pro": "one-dark-pro",
    "Tokyo Night": "tokyo-night", "Night Owl": "night-owl", "Nord": "nord",
    "Catppuccin Mocha": "catppuccin-mocha", "Ayu Mirage": "ayu-mirage",
    "Gruvbox Dark": "gruvbox-dark-medium", "Solarized Dark": "solarized-dark",
    "Solarized Light": "solarized-light", "Synthwave '84": "synthwave-84",
}
LEGACY_THEMES = {"Dracula Glow": "Dracula", "Monokai Pro": "Monokai",
                 "Light Studio": "GitHub Light", "Midnight Pro": "Night Owl",
                 "Synthwave": "Synthwave '84"}
ROOT = Path(__file__).resolve().parents[1]
_worker_lock = Lock()
_process = None
_answers = None


def _stop_worker():
    global _process
    if _process is not None:
        _process.terminate()
        try:
            _process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _process.kill()
            _process.wait()
        for stream in (_process.stdin, _process.stdout):
            if stream:
                stream.close()
        _process = None


atexit.register(_stop_worker)


def _read_answers(process, answers):
    try:
        for line in process.stdout:
            answers.put(line)
    finally:
        answers.put(None)


class HighlightingUnavailable(RuntimeError):
    pass


def normalize_code(code: str) -> str:
    return code.replace("\r\n", "\n").replace("\r", "\n")


def detect_language(code: str, language: str = "auto", filename: str = "") -> str:
    selected = (language or "auto").strip().lower()
    if selected != "auto":
        return selected
    name = Path(filename).name.lower()
    extension = Path(name).suffix.lstrip(".")
    for key, config in LANGUAGE_CATALOG.items():
        if extension in config.get("extensions", []) or name in config.get("filenames", []):
            return key
    # Pygments' corpus guesses can favor niche languages for short snippets.
    # These signatures only choose a grammar; they never assign token colors.
    signatures = [
        ('python', r'(?m)^\s*(?:async\s+)?def\s+\w+\([^\n]*\).*:\s*(?:#.*)?$'),
        ('python', r'(?m)^\s*(?:from\s+[\w.]+\s+import\s+|class\s+\w+(?:\([^\n]*\))?:\s*$)'),
        ('typescript', r'(?m)^\s*(?:export\s+)?(?:interface\s+\w+\s*\{|type\s+\w+\s*=)'),
        ('javascript', r'(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+\w+\s*\('),
        ('javascript', r'(?m)^\s*(?:const|let)\s+[\w$]+\s*='),
        ('rust', r'(?m)^\s*(?:pub\s+)?(?:async\s+)?fn\s+\w+\s*\('),
        ('go', r'(?m)^\s*(?:package\s+\w+|func\s+\w+\s*\()'),
        ('bash', r'^#![^\n]*(?:bash|/sh)\b'),
        ('php', r'^\s*<\?php\b'),
    ]
    for key, pattern in signatures:
        if re.search(pattern, code):
            return key
    try:
        if isinstance(json.loads(code), (dict, list)):
            return 'json'
    except ValueError:
        pass
    if code.strip():
        try:
            guessed = guess_lexer(code).aliases
            for key, config in LANGUAGE_CATALOG.items():
                if key in guessed or config.get("lexer") in guessed:
                    return key
        except ClassNotFound:
            pass
    return "text"


def highlight_code(code: str, language: str, theme_name: str, filename: str = "") -> dict:
    code = normalize_code(code)
    resolved = detect_language(code, language, filename)
    theme = THEME_NAMES.get(LEGACY_THEMES.get(theme_name, theme_name), "dark-plus")
    return _highlight(code, resolved, theme)


@lru_cache(maxsize=48)
def _highlight(code: str, language: str, theme: str) -> dict:
    global _process, _answers
    node = shutil.which("node")
    if not node:
        raise HighlightingUnavailable("Syntax highlighting needs Node.js 20+ and npm ci. See README.md.")
    try:
        # One warm process keeps loaded grammars; serialize the JSON-line protocol.
        # A bounded response wait lets a hung grammar recover on the next request.
        with _worker_lock:
            if _process is None or _process.poll() is not None:
                _stop_worker()
                _answers = Queue()
                _process = subprocess.Popen(
                    [node, str(ROOT / "src" / "highlight.mjs")],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", cwd=ROOT,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                Thread(target=_read_answers, args=(_process, _answers), daemon=True).start()
            try:
                _process.stdin.write(json.dumps({"code": code, "language": language, "theme": theme}) + "\n")
                _process.stdin.flush()
                answer = _answers.get(timeout=30)
                if answer is None:
                    raise OSError("Syntax worker exited")
                data = json.loads(answer)
            except (OSError, Empty, ValueError):
                _stop_worker()
                raise
        if "error" in data:
            raise HighlightingUnavailable("Syntax engine could not tokenize this snippet.")
        if "\n".join("".join(t["content"] for t in line) for line in data["lines"]) != code:
            raise HighlightingUnavailable("Syntax engine returned incomplete source text.")
        return data
    except (OSError, Empty, ValueError) as exc:
        raise HighlightingUnavailable("Syntax highlighting failed or timed out. Check Node.js and run npm ci.") from exc


def editor_theme(highlight: dict) -> dict:
    """Theme UI colors, falling back only to that theme's foreground/background."""
    colors = highlight["colors"]
    bg, fg = highlight["background"], highlight["foreground"]
    return {
        "editor_bg": bg, "page_bg": colors.get("sideBar.background", bg),
        "chrome_bg": colors.get("titleBar.activeBackground", bg), "gutter_bg": bg,
        "text": fg, "muted": colors.get("editorLineNumber.foreground", fg),
        "active": colors.get("editor.lineHighlightBackground", bg),
        "accent": colors.get("editorCursor.foreground", fg),
        "border": colors.get("editorGroup.border", bg),
        "plus": colors.get("gitDecoration.addedResourceForeground", fg),
        "shadow": "rgba(0, 0, 0, 0.4)",
    }
