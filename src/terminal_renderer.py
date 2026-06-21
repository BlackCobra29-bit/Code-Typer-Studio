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


@dataclass(frozen=True)
class TerminalOptions:
    title: str = "eminem — zsh"
    prompt: str = "eminem@macbook ~ %"
    command: str = "python --version"
    output: str = "Python 3.12.4"
    word_speed_ms: int = 320
    output_delay_ms: int = 2000
    loop: bool = False


def build_terminal_html(options: TerminalOptions, standalone: bool = False) -> str:
    config = base64.b64encode(
        json.dumps(
            {
                "command": options.command,
                "output": options.output,
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
        for line in (options.output or "").splitlines() or [""]:
            draw.text((x, output_y), line, font=font, fill="#d7d7d7")
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
  overflow: auto;
  padding: 19px 21px 22px;
  font-family: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 16px;
  line-height: 1.5;
  scrollbar-width: none;
}
.screen::-webkit-scrollbar { display: none; }
.command-line { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.prompt { color: #75c7ff; font-weight: 600; }
.command { color: #f5f5f5; }
.output { margin: 2px 0 0; color: #d7d7d7; white-space: pre-wrap; overflow-wrap: anywhere; }
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
    output.textContent = config.output;
    screen.scrollTop = screen.scrollHeight;
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
