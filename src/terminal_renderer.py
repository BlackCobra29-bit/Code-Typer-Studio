from __future__ import annotations

import base64
import html
import json
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


TERMINAL_WIDTH = 700
TERMINAL_HEIGHT = 300
DEFAULT_TERMINAL_COMMAND = "cargo run"
DEFAULT_TERMINAL_OUTPUT = """error[E0506]: cannot assign to `balance` because it is borrowed
 --> src/main.rs:5:5
  |
3 |     let receipt = &balance;
  |                   -------- `balance` is borrowed here
5 |     balance += 50;
  |     ^^^^^^^^^^^^^ `balance` is assigned to here but it was already borrowed
7 |     println!("Old receipt: {receipt}");
  |                             ------- borrow later used here"""
OUTPUT_BASE_COLOR = "#d7d7d7"
ANSI_COLORS = {
    30: "#5c6370",
    31: "#ff6b6b",
    32: "#69db7c",
    33: "#ffd166",
    34: "#74c0fc",
    35: "#c792ea",
    36: "#66d9ef",
    37: OUTPUT_BASE_COLOR,
    90: "#8b949e",
    91: "#ff8787",
    92: "#8ce99a",
    93: "#ffe066",
    94: "#91caff",
    95: "#d0a9f5",
    96: "#8be9fd",
    97: "#ffffff",
}
ANSI_PATTERN = re.compile(r"\x1b\[([0-9;]*)m")
SEMANTIC_PATTERN = re.compile(
    r"(?P<error>\b(?:error(?:\[[A-Z0-9]+\])?|fatal|failed|failure|panic(?:ked)?)\b:?)"
    r"|(?P<warning>\b(?:warn(?:ing)?|deprecated)\b:?)"
    r"|(?P<success>\b(?:success(?:ful(?:ly)?)?|finished|compiled?|compiling|created|installed|done|passed|ok)\b)"
    r"|(?P<path>(?:\.{0,2}/)?(?:[\w.-]+/)+[\w.-]+(?::\d+(?::\d+)?)?)"
    r"|(?P<string>`[^`]*`|'[^']*'|\"[^\"]*\")"
    r"|(?P<marker>-->|==>|\^+|~{3,}|-{3,})"
    r"|(?P<diagnostic>\b(?:mutable|immutable|borrow(?:ed)?|expected|found|required)\b)"
    r"|(?P<number>\b\d+(?=\s*\|)|\b\d+(?:\.\d+){1,3}\b)",
    re.IGNORECASE,
)
SEMANTIC_COLORS = {
    "error": "#ff6b6b",
    "warning": "#ffd166",
    "success": "#69db7c",
    "path": "#66d9ef",
    "string": "#69db7c",
    "marker": "#ffd166",
    "diagnostic": "#c792ea",
    "number": "#f6a66a",
}


@dataclass(frozen=True)
class TerminalOptions:
    title: str = "eminem — zsh"
    prompt: str = "eminem@macbook ~ %"
    command: str = DEFAULT_TERMINAL_COMMAND
    output: str = DEFAULT_TERMINAL_OUTPUT
    word_speed_ms: int = 320
    output_delay_ms: int = 1000
    loop: bool = True


def build_terminal_html(options: TerminalOptions, standalone: bool = False) -> str:
    config = base64.b64encode(
        json.dumps(
            {
                "command": options.command,
                "outputTokens": terminal_output_tokens(options.output),
                "wordSpeedMs": _clamp(options.word_speed_ms, 80, 1200),
                "outputDelayMs": _clamp(options.output_delay_ms, 0, 5000),
                "loop": options.loop,
            }
        ).encode("utf-8")
    ).decode("ascii")
    document = TERMINAL_HTML
    replacements = {
        "__TITLE__": html.escape(options.title or "Terminal"),
        "__PROMPT__": html.escape(options.prompt or "%"),
        "__CONFIG__": config,
    }
    for token, value in replacements.items():
        document = document.replace(token, value)
    if standalone:
        return document
    return document.replace("<body>", '<body class="embedded">')


def build_terminal_gif(options: TerminalOptions) -> bytes:
    font = _load_font(16)
    title_font = _load_font(13)
    words = re.findall(r"\S+\s*", options.command)
    if not words and options.command:
        words = [options.command]
    visible_commands = [""]
    for index in range(1, len(words) + 1):
        visible_commands.append("".join(words[:index]))

    frames = [
        _draw_terminal_frame(options, visible_command, False, font, title_font)
        for visible_command in visible_commands
    ]
    durations = [max(80, int(options.word_speed_ms))] * len(frames)
    durations[-1] = max(20, int(options.output_delay_ms))
    frames.append(_draw_terminal_frame(options, options.command, True, font, title_font))
    durations.append(2000)

    output = BytesIO()
    save_options = {
        "format": "GIF",
        "save_all": True,
        "append_images": frames[1:],
        "optimize": False,
        "duration": durations,
        "disposal": 2,
    }
    if options.loop:
        save_options["loop"] = 0
    frames[0].save(
        output,
        **save_options,
    )
    return output.getvalue()


def terminal_output_tokens(output: str) -> list[dict[str, str | bool]]:
    text = output or ""
    if ANSI_PATTERN.search(text):
        return _ansi_output_tokens(text)

    tokens: list[dict[str, str | bool]] = []
    for line_index, line in enumerate(text.split("\n")):
        position = 0
        for match in SEMANTIC_PATTERN.finditer(line):
            if match.start() > position:
                _append_output_token(tokens, line[position : match.start()], OUTPUT_BASE_COLOR)
            kind = match.lastgroup or ""
            _append_output_token(
                tokens,
                match.group(0),
                SEMANTIC_COLORS.get(kind, OUTPUT_BASE_COLOR),
                bold=kind in {"error", "warning", "success"},
            )
            position = match.end()
        if position < len(line):
            _append_output_token(tokens, line[position:], OUTPUT_BASE_COLOR)
        if line_index < len(text.split("\n")) - 1:
            _append_output_token(tokens, "\n", OUTPUT_BASE_COLOR)
    return tokens


def _ansi_output_tokens(text: str) -> list[dict[str, str | bool]]:
    tokens: list[dict[str, str | bool]] = []
    color = OUTPUT_BASE_COLOR
    bold = False
    position = 0
    for match in ANSI_PATTERN.finditer(text):
        if match.start() > position:
            _append_output_token(tokens, text[position : match.start()], color, bold)
        codes = [int(code) for code in match.group(1).split(";") if code] or [0]
        for code in codes:
            if code == 0:
                color = OUTPUT_BASE_COLOR
                bold = False
            elif code == 1:
                bold = True
            elif code == 22:
                bold = False
            elif code in {39, 49}:
                color = OUTPUT_BASE_COLOR
            elif code in ANSI_COLORS:
                color = ANSI_COLORS[code]
        position = match.end()
    if position < len(text):
        _append_output_token(tokens, text[position:], color, bold)
    return tokens


def _append_output_token(
    tokens: list[dict[str, str | bool]],
    text: str,
    color: str,
    bold: bool = False,
) -> None:
    if not text:
        return
    if tokens and tokens[-1]["color"] == color and tokens[-1]["bold"] == bold:
        tokens[-1]["text"] = str(tokens[-1]["text"]) + text
        return
    tokens.append({"text": text, "color": color, "bold": bold})


def _draw_terminal_frame(
    options: TerminalOptions,
    visible_command: str,
    show_output: bool,
    font,
    title_font,
) -> Image.Image:
    image = Image.new("RGB", (TERMINAL_WIDTH, TERMINAL_HEIGHT), "#151515")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, TERMINAL_WIDTH - 1, TERMINAL_HEIGHT - 1),
        radius=13,
        fill="#151515",
        outline="#3b3b3d",
    )
    draw.rounded_rectangle((0, 0, TERMINAL_WIDTH - 1, 42), radius=13, fill="#303033")
    draw.rectangle((0, 29, TERMINAL_WIDTH - 1, 42), fill="#303033")
    draw.line((0, 42, TERMINAL_WIDTH, 42), fill="#111113")
    for index, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        x = 16 + index * 20
        draw.ellipse((x, 15, x + 12, 27), fill=color)

    title = options.title or "Terminal"
    title_width = draw.textlength(title, font=title_font)
    draw.text(((TERMINAL_WIDTH - title_width) / 2, 13), title, font=title_font, fill="#d4d4d4")

    x = 22
    y = 65
    prompt = options.prompt or "%"
    draw.text((x, y), prompt, font=font, fill="#75c7ff")
    command_x = x + draw.textlength(prompt + " ", font=font)
    draw.text((command_x, y), visible_command, font=font, fill="#f5f5f5")
    cursor_x = command_x + draw.textlength(visible_command, font=font)
    draw.rectangle((cursor_x + 1, y + 2, cursor_x + 9, y + 19), fill="#e8e8e8")

    if show_output:
        output_y = y + 28
        output_x = x
        for token in terminal_output_tokens(options.output):
            parts = str(token["text"]).split("\n")
            for part_index, part in enumerate(parts):
                if part:
                    draw.text((output_x, output_y), part, font=font, fill=str(token["color"]))
                    output_x += draw.textlength(part, font=font)
                if part_index < len(parts) - 1:
                    output_x = x
                    output_y += 24
    return image


def _load_font(size: int):
    candidates = [
        Path("C:/Windows/Fonts/CascadiaMono.ttf"),
        Path("C:/Windows/Fonts/CascadiaCode.ttf"),
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("/System/Library/Fonts/Menlo.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


TERMINAL_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
* { box-sizing: border-box; }
html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; }
body {
  display: grid;
  place-items: center;
  background: #eef2f7;
  color: #f5f5f5;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
body.embedded { background: transparent; }
.terminal {
  width: 700px;
  height: 300px;
  overflow: hidden;
  border: 1px solid #3b3b3d;
  border-radius: 13px;
  background: #151515;
  box-shadow: 0 24px 70px rgb(15 23 42 / 28%);
}
body.embedded .terminal { width: 100%; height: 100%; box-shadow: none; }
.titlebar {
  position: relative;
  display: flex;
  align-items: center;
  height: 42px;
  padding: 0 15px;
  border-bottom: 1px solid #111113;
  background: linear-gradient(#38383b, #2d2d30);
}
.lights { display: flex; gap: 8px; }
.light { width: 12px; height: 12px; border-radius: 50%; box-shadow: inset 0 0 0 0.5px rgb(0 0 0 / 25%); }
.red { background: #ff5f57; } .yellow { background: #febc2e; } .green { background: #28c840; }
.title {
  position: absolute;
  left: 50%;
  max-width: 70%;
  transform: translateX(-50%);
  overflow: hidden;
  color: #d7d7d7;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.screen {
  height: calc(100% - 42px);
  overflow-x: auto;
  overflow-y: auto;
  padding: 19px 21px 22px;
  font-family: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 16px;
  line-height: 1.5;
  scrollbar-width: thin;
  scrollbar-color: #62656b #1b1b1d;
  scrollbar-gutter: stable;
}
.screen::-webkit-scrollbar { width: 10px; height: 10px; }
.screen::-webkit-scrollbar-track { background: #1b1b1d; }
.screen::-webkit-scrollbar-thumb { border: 2px solid #1b1b1d; border-radius: 999px; background: #62656b; }
.screen::-webkit-scrollbar-thumb:hover { background: #7b7f86; }
.screen::-webkit-scrollbar-corner { background: #1b1b1d; }
.command-line { width: max-content; min-width: 100%; margin: 0; white-space: pre; }
.prompt { color: #75c7ff; font-weight: 600; }
.command { color: #f5f5f5; }
.output { width: max-content; min-width: 100%; margin: 2px 0 0; color: #d7d7d7; white-space: pre; }
.output-token { color: var(--token-color); }
.cursor {
  display: inline-block;
  width: 0.58em;
  height: 1.05em;
  margin-left: 1px;
  vertical-align: -0.16em;
  background: #ededed;
  animation: blink 0.9s steps(2, start) infinite;
}
@keyframes blink { 50% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .cursor { animation: none; } }
</style>
</head>
<body>
<main class="terminal" aria-label="Animated macOS terminal">
  <header class="titlebar">
    <span class="lights" aria-hidden="true"><span class="light red"></span><span class="light yellow"></span><span class="light green"></span></span>
    <span class="title">__TITLE__</span>
  </header>
  <section class="screen" id="screen">
    <p class="command-line"><span class="prompt">__PROMPT__</span> <span class="command" id="command"></span><span class="cursor" aria-hidden="true"></span></p>
    <pre class="output" id="output" aria-live="polite"></pre>
  </section>
</main>
<script>
(() => {
  const configBytes = Uint8Array.from(atob("__CONFIG__"), (char) => char.charCodeAt(0));
  const config = JSON.parse(new TextDecoder().decode(configBytes));
  const command = document.getElementById("command");
  const output = document.getElementById("output");
  const screen = document.getElementById("screen");
  const words = config.command.match(/\\S+\\s*/g) || (config.command ? [config.command] : []);
  let index = 0;
  let timer = null;

  function schedule(callback, delay) {
    window.clearTimeout(timer);
    timer = window.setTimeout(callback, delay);
  }

  function typeNextWord() {
    if (index >= words.length) {
      schedule(showOutput, config.outputDelayMs);
      return;
    }
    command.textContent += words[index];
    index += 1;
    screen.scrollTop = screen.scrollHeight;
    if (index >= words.length) {
      schedule(showOutput, config.outputDelayMs);
    } else {
      schedule(typeNextWord, config.wordSpeedMs);
    }
  }

  function showOutput() {
    const fragment = document.createDocumentFragment();
    config.outputTokens.forEach((token) => {
      const span = document.createElement("span");
      span.className = "output-token";
      span.style.setProperty("--token-color", token.color);
      span.style.fontWeight = token.bold ? "700" : "400";
      span.textContent = token.text;
      fragment.appendChild(span);
    });
    output.replaceChildren(fragment);
    screen.scrollTop = 0;
    screen.scrollLeft = 0;
    if (config.loop) schedule(restart, 2200);
  }

  function restart() {
    window.clearTimeout(timer);
    index = 0;
    command.textContent = "";
    output.textContent = "";
    schedule(typeNextWord, 350);
  }

  window.addEventListener("message", (event) => {
    if (event.data === "terminal:restart") restart();
  });
  restart();
})();
</script>
</body>
</html>
"""
