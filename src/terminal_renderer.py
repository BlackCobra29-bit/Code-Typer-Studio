from __future__ import annotations

import base64
import html
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .gradients import gradient_css, gradient_stops


TERMINAL_WIDTH = 700
TERMINAL_HEIGHT = 300
VIDEO_FPS = 30
MAX_TERMINAL_GIF_FRAMES = 72
MAX_TERMINAL_VIDEO_FRAMES = 96
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
    title: str = "eminem - zsh"
    prompt: str = "eminem@macbook ~ %"
    command: str = DEFAULT_TERMINAL_COMMAND
    output: str = DEFAULT_TERMINAL_OUTPUT
    word_speed_ms: int = 320
    output_delay_ms: int = 1000
    loop: bool = True
    width: int = TERMINAL_WIDTH
    height: int = TERMINAL_HEIGHT
    aspect_ratio: str = "display"
    background_style: str = "none"
    gradient_name: str = "sunset"
    canvas_padding: int = 52


def build_terminal_html(options: TerminalOptions, standalone: bool = False) -> str:
    gradient_enabled = _gradient_enabled(options)
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
        "__STAGE_WIDTH__": f"{_clamp(options.width, 520, 1600)}px",
        "__STAGE_HEIGHT__": f"{_clamp(options.height, 300, 1400)}px",
        "__CANVAS_FILL__": gradient_css(options.gradient_name) if gradient_enabled else "#eef2f7",
        "__CANVAS_PADDING__": f"{_canvas_padding(options)}px" if gradient_enabled else "0px",
        "__CANVAS_RADIUS__": "0px",
        "__PAGE_PADDING__": "20px" if gradient_enabled and standalone else "0px",
        "__CARD_SHADOW__": "0 10px 24px rgba(15, 23, 42, 0.10)" if gradient_enabled else "0 24px 70px rgb(15 23 42 / 28%)",
        "__EMBEDDED_SHADOW__": "0 10px 24px rgba(15, 23, 42, 0.10)" if gradient_enabled else "none",
        "__EMBEDDED_BORDER__": "1px solid #3b3b3d" if gradient_enabled else "0",
    }
    for token, value in replacements.items():
        document = document.replace(token, value)
    if standalone:
        if options.aspect_ratio == "display":
            return document.replace("<body>", '<body class="flush-frame">')
        return document
    return (
        document.replace('<html lang="en">', '<html lang="en" class="embedded-root">')
        .replace("<body>", '<body class="embedded">')
    )


def build_terminal_gif(options: TerminalOptions) -> bytes:
    frames, durations = _terminal_frames(options, max_frames=MAX_TERMINAL_GIF_FRAMES)
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
    frames[0].save(output, **save_options)
    return output.getvalue()


def build_terminal_mp4(options: TerminalOptions, fps: int = VIDEO_FPS) -> bytes:
    frames, durations = _terminal_frames(options, max_frames=MAX_TERMINAL_VIDEO_FRAMES)
    output = BytesIO()
    with imageio.get_writer(output, format="mp4", fps=fps, codec="libx264", quality=7, macro_block_size=1) as writer:
        for frame, duration in zip(frames, durations):
            repeats = max(1, round(duration / (1000 / fps)))
            array = np.asarray(frame.convert("RGB"))
            for _ in range(repeats):
                writer.append_data(array)
    return output.getvalue()


def terminal_output_tokens(output: str) -> list[dict[str, str | bool]]:
    text = output or ""
    if ANSI_PATTERN.search(text):
        return _ansi_output_tokens(text)

    tokens: list[dict[str, str | bool]] = []
    lines = text.split("\n")
    for line_index, line in enumerate(lines):
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
        if line_index < len(lines) - 1:
            _append_output_token(tokens, "\n", OUTPUT_BASE_COLOR)
    return tokens


def _terminal_frames(options: TerminalOptions, max_frames: int) -> tuple[list[Image.Image], list[int]]:
    width = _clamp(options.width, 520, 1600)
    height = _clamp(options.height, 300, 1400)
    gradient_enabled = _gradient_enabled(options)
    padding = _canvas_padding(options) if gradient_enabled else 0
    terminal_width = max(420, width - (padding * 2))
    terminal_height = max(220, height - (padding * 2))
    font_size = _terminal_font_size(16, terminal_width)
    title_font_size = max(11, _terminal_font_size(13, terminal_width))
    font = _load_font(font_size)
    title_font = _load_font(title_font_size)
    words = re.findall(r"\S+\s*", options.command)
    if not words and options.command:
        words = [options.command]
    visible_commands = [""]
    for index in range(1, len(words) + 1):
        visible_commands.append("".join(words[:index]))
    visible_commands = _limit_sequence(visible_commands, max_frames - 1)

    frames: list[Image.Image] = []
    base_canvas = _terminal_canvas(width, height, options.gradient_name) if gradient_enabled else None
    for visible_command in visible_commands:
        terminal_frame = _draw_terminal_frame(
            options,
            visible_command,
            False,
            font,
            title_font,
            terminal_width,
            terminal_height,
            font_size,
        )
        frames.append(_compose_terminal_canvas(base_canvas, terminal_frame, width, height))

    durations = [max(80, int(options.word_speed_ms))] * len(frames)
    durations[-1] = max(20, int(options.output_delay_ms))
    final_frame = _draw_terminal_frame(
        options,
        options.command,
        True,
        font,
        title_font,
        terminal_width,
        terminal_height,
        font_size,
    )
    frames.append(_compose_terminal_canvas(base_canvas, final_frame, width, height))
    durations.append(2000)
    return frames, durations


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
    width: int,
    height: int,
    font_size: int,
) -> Image.Image:
    chrome_height = 42
    radius = max(12, min(26, round(width * 0.018)))
    image = Image.new("RGB", (width, height), "#151515")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill="#151515", outline="#3b3b3d")
    draw.rounded_rectangle((0, 0, width - 1, chrome_height), radius=radius, fill="#303033")
    draw.rectangle((0, chrome_height - radius, width - 1, chrome_height), fill="#303033")
    draw.line((0, chrome_height, width, chrome_height), fill="#111113")
    for index, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        x = 16 + index * 20
        draw.ellipse((x, 15, x + 12, 27), fill=color)

    title = options.title or "Terminal"
    title_width = draw.textlength(title, font=title_font)
    draw.text(((width - title_width) / 2, 13), title, font=title_font, fill="#d4d4d4")

    x = 22
    y = chrome_height + 23
    prompt = options.prompt or "%"
    draw.text((x, y), prompt, font=font, fill="#75c7ff")
    command_x = x + draw.textlength(prompt + " ", font=font)
    draw.text((command_x, y), visible_command, font=font, fill="#f5f5f5")
    cursor_x = command_x + draw.textlength(visible_command, font=font)
    cursor_height = max(16, font_size + 2)
    draw.rectangle((cursor_x + 1, y + 2, cursor_x + 9, y + cursor_height), fill="#e8e8e8")

    if show_output:
        output_y = y + max(28, font_size + 12)
        output_x = x
        for token in terminal_output_tokens(options.output):
            parts = str(token["text"]).split("\n")
            for part_index, part in enumerate(parts):
                if part:
                    draw.text((output_x, output_y), part, font=font, fill=str(token["color"]))
                    output_x += draw.textlength(part, font=font)
                if part_index < len(parts) - 1:
                    output_x = x
                    output_y += max(24, font_size + 8)
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


def _terminal_font_size(base_size: int, frame_width: int) -> int:
    scale = max(1.0, frame_width / TERMINAL_WIDTH)
    return max(12, min(48, round(base_size * scale)))


def _gradient_enabled(options: TerminalOptions) -> bool:
    return str(options.background_style).lower() == "gradient" and str(options.aspect_ratio).lower() != "display"


def _canvas_padding(options: TerminalOptions) -> int:
    size_bound = min(_clamp(options.width, 520, 1600), _clamp(options.height, 300, 1400))
    high = max(18, int(size_bound * 0.18))
    return _clamp(options.canvas_padding, 18, high)


def _limit_sequence(items: list[str], max_frames: int) -> list[str]:
    if len(items) <= max_frames:
        return items
    limited: list[str] = []
    for index in range(max_frames):
        source_index = round(index * (len(items) - 1) / max(1, max_frames - 1))
        value = items[source_index]
        if not limited or limited[-1] != value:
            limited.append(value)
    if limited[-1] != items[-1]:
        limited.append(items[-1])
    return limited


@lru_cache(maxsize=32)
def _terminal_canvas(width: int, height: int, gradient_name: str) -> Image.Image:
    colors = [_hex_to_rgb(color) for color in gradient_stops(gradient_name)]
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    denominator = max(1, width + height - 2)
    for y in range(height):
        for x in range(width):
            position = (x + y) / denominator
            pixels[x, y] = _sample_gradient(colors, position)
    return image


def _compose_terminal_canvas(canvas: Image.Image | None, terminal_frame: Image.Image, width: int, height: int) -> Image.Image:
    if canvas is None:
        return terminal_frame
    background = canvas.copy()
    left = (width - terminal_frame.width) // 2
    top = (height - terminal_frame.height) // 2
    background.paste(terminal_frame, (left, top))
    return background


def _sample_gradient(colors: list[tuple[int, int, int]], position: float) -> tuple[int, int, int]:
    if len(colors) == 1:
        return colors[0]
    bounded = max(0.0, min(1.0, position))
    scaled = bounded * (len(colors) - 1)
    index = min(len(colors) - 2, int(scaled))
    local = scaled - index
    start = colors[index]
    end = colors[index + 1]
    return tuple(
        int(start[channel] + ((end[channel] - start[channel]) * local))
        for channel in range(3)
    )


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        return (0, 0, 0)
    return tuple(int(clean[index : index + 2], 16) for index in (0, 2, 4))


TERMINAL_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
* { box-sizing: border-box; }
html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; }
.embedded-root {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
body {
  display: grid;
  place-items: center;
  padding: __PAGE_PADDING__;
  background: #eef2f7;
  color: #f5f5f5;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
body.embedded {
  display: block;
  width: 100vw;
  height: 100vh;
  min-height: 0;
  background: transparent;
  padding: 0;
  overflow: hidden;
}
.stage-shell {
  width: min(100%, __STAGE_WIDTH__);
  height: __STAGE_HEIGHT__;
  padding: __CANVAS_PADDING__;
  border-radius: __CANVAS_RADIUS__;
  background: __CANVAS_FILL__;
}
body.embedded .stage-shell {
  width: 100%;
  height: 100%;
}
.terminal {
  width: 100%;
  height: 100%;
  overflow: hidden;
  border: 1px solid #3b3b3d;
  border-radius: 13px;
  background: #151515;
  box-shadow: __CARD_SHADOW__;
}
body.embedded .terminal {
  width: 100%;
  height: 100%;
  box-shadow: __EMBEDDED_SHADOW__;
  border: __EMBEDDED_BORDER__;
}
body.flush-frame {
  width: __STAGE_WIDTH__;
  height: __STAGE_HEIGHT__;
  min-height: __STAGE_HEIGHT__;
  background: transparent;
}
body.flush-frame .stage-shell {
  width: 100%;
  height: 100%;
  padding: 0;
  border-radius: 0;
  background: transparent;
}
body.flush-frame .terminal {
  box-shadow: none;
  border: 0;
}
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
<div class="stage-shell">
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
</div>
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
    index = 0;
    output.textContent = "";
    command.textContent = "";
    screen.scrollTop = 0;
    screen.scrollLeft = 0;
    schedule(typeNextWord, 160);
  }

  window.addEventListener("message", (event) => {
    if (event.data === "terminal:restart") restart();
  });

  restart();
})();
</script>
</body>
</html>"""
