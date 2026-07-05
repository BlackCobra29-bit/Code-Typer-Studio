from __future__ import annotations

from io import BytesIO
from functools import lru_cache
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from .gradients import gradient_stops
from .languages import LANGUAGE_LEXERS
from .renderer import RenderOptions
from .syntax_style import syntax_color, syntax_palette
from .themes import THEMES


PREVIEW_DISPLAY_WIDTH = 700
VIDEO_FPS = 30
MAX_GIF_FRAMES = 54
MAX_VIDEO_FRAMES = 72


def build_typing_gif(code: str, options: RenderOptions, frame_step: int = 3) -> bytes:
    frames, duration = _build_typing_frames(code, options, frame_step, max_frames=MAX_GIF_FRAMES)
    output = BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=duration,
        loop=0 if options.loop else 1,
        disposal=2,
    )
    return output.getvalue()


def build_typing_mp4(code: str, options: RenderOptions, frame_step: int = 3, fps: int = VIDEO_FPS) -> bytes:
    frames, duration = _build_typing_frames(code, options, frame_step, max_frames=MAX_VIDEO_FRAMES)
    frame_hold = max(1, round(duration / (1000 / fps)))
    output = BytesIO()
    with imageio.get_writer(output, format="mp4", fps=fps, codec="libx264", quality=7, macro_block_size=1) as writer:
        for frame in frames:
            array = np.asarray(frame.convert("RGB"))
            for _ in range(frame_hold):
                writer.append_data(array)
    return output.getvalue()


def _build_typing_frames(code: str, options: RenderOptions, frame_step: int, max_frames: int) -> tuple[list[Image.Image], int]:
    theme = THEMES.get(options.theme_name, THEMES["VS Code Dark+"])
    width = max(520, min(1600, int(options.width)))
    height = max(260, min(1400, int(options.height)))
    use_gradient_canvas = _gradient_enabled(options)
    canvas_padding = _canvas_padding(options, width, height) if use_gradient_canvas else 0
    editor_width = max(420, width - (canvas_padding * 2))
    editor_height = max(220, height - (canvas_padding * 2))
    font_size = _gif_font_size(options.font_size, editor_width)
    line_height = int(font_size * max(1.1, min(2.2, float(options.line_height))))
    chrome_height = 42 if options.show_window_chrome else 0
    gutter_width = 84 if options.show_line_numbers else 30
    content_x = gutter_width + 24
    top_y = chrome_height + 20
    padding_bottom = 24
    font = _load_font(options.font_family, font_size)
    small_font = _load_font(options.font_family, max(10, _gif_font_size(13, editor_width)))
    chars = _token_chars(code or " ", options.language, options.theme_name)
    step = max(1, min(12, int(frame_step)))
    raw_counts = _visible_counts(chars, options.typing_mode, step)
    counts = _limit_counts(raw_counts, max_frames)

    max_visible_lines = max(1, (editor_height - chrome_height - padding_bottom) // line_height)
    frames: list[Image.Image] = []
    base_canvas = (
        _base_canvas(width, height, canvas_padding, options.gradient_name, max(12, min(42, int(options.radius) + 14)))
        if use_gradient_canvas
        else None
    )
    for visible_count in counts:
        active_line = _active_line(chars, visible_count)
        first_line = max(0, active_line - max_visible_lines + 2)
        editor_frame = _draw_editor_frame(
            chars=chars,
            visible_count=visible_count,
            first_line=first_line,
            max_visible_lines=max_visible_lines,
            active_line=active_line,
            code=code,
            width=editor_width,
            height=editor_height,
            line_height=line_height,
            chrome_height=chrome_height,
            gutter_width=gutter_width,
            content_x=content_x,
            top_y=top_y,
            font=font,
            small_font=small_font,
            theme=theme,
            options=options,
        )
        if use_gradient_canvas:
            frames.append(
                _compose_canvas_frame(
                    editor_frame=editor_frame,
                    canvas=base_canvas,
                    radius=max(12, min(42, int(options.radius) + 14)),
                )
            )
        else:
            frames.append(editor_frame)

    if frames:
        frames.extend([frames[-1].copy() for _ in range(6)])

    duration = _scaled_frame_duration(options, step, len(raw_counts), len(counts))
    return frames, duration


def _draw_editor_frame(
    chars,
    visible_count: int,
    first_line: int,
    max_visible_lines: int,
    active_line: int,
    code: str,
    width: int,
    height: int,
    line_height: int,
    chrome_height: int,
    gutter_width: int,
    content_x: int,
    top_y: int,
    font,
    small_font,
    theme,
    options: RenderOptions,
) -> Image.Image:
    image = Image.new("RGB", (width, height), theme["editor_bg"])
    draw = ImageDraw.Draw(image)
    radius = max(0, min(32, int(options.radius)))
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=theme["editor_bg"], outline=theme["border"])

    if options.show_window_chrome:
        draw.rounded_rectangle((0, 0, width - 1, chrome_height), radius=radius, fill=theme["chrome_bg"])
        draw.rectangle((0, chrome_height - radius, width - 1, chrome_height), fill=theme["chrome_bg"])
        for index, color in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
            x = 18 + index * 20
            draw.ellipse((x, 16, x + 10, 26), fill=color)
        draw.text((88, 13), options.title or "code-typer-studio", font=small_font, fill=theme["muted"])

    draw.rectangle((0, chrome_height, gutter_width, height), fill=theme["gutter_bg"])

    visible_chars = chars[:visible_count]
    cursor_x = content_x
    cursor_y = top_y
    line_count = max(1, len(code.split("\n")))

    for visible_line in range(first_line, min(line_count, first_line + max_visible_lines)):
        y = top_y + (visible_line - first_line) * line_height
        if visible_line == active_line:
            draw.rectangle((0, y, width, y + line_height), fill=theme["active"])
        if visible_line > active_line:
            continue
        if options.show_diff_gutter:
            draw.text((18, y + 1), "+", font=font, fill=theme["plus"])
        if options.show_line_numbers:
            number = str(visible_line + 1)
            number_width = draw.textlength(number, font=font)
            draw.text((gutter_width - number_width - 14, y + 1), number, font=font, fill=theme["muted"])

    line_x = {}
    for char in visible_chars:
        line = char["line"]
        if line < first_line or line >= first_line + max_visible_lines:
            continue
        y = top_y + (line - first_line) * line_height
        x = line_x.get(line, content_x)
        if char["text"] != "\n":
            draw.text((x, y + 1), char["text"], font=font, fill=char["color"])
            x += draw.textlength(char["text"], font=font)
            line_x[line] = x
            cursor_x = x
            cursor_y = y

    _draw_cursor(draw, cursor_x, cursor_y + 3, font, theme["accent"], options.cursor)
    return image


def _compose_canvas_frame(
    editor_frame: Image.Image,
    canvas: Image.Image,
    radius: int,
) -> Image.Image:
    background = canvas.copy()
    left = (background.width - editor_frame.width) // 2
    top = (background.height - editor_frame.height) // 2
    mask = _rounded_mask(editor_frame.size, radius)
    background.paste(editor_frame, (left, top), mask)
    return background


@lru_cache(maxsize=32)
def _gradient_background(width: int, height: int, gradient_name: str) -> Image.Image:
    colors = [_hex_to_rgb(color) for color in gradient_stops(gradient_name)]
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    denominator = max(1, width + height - 2)
    for y in range(height):
        for x in range(width):
            position = (x + y) / denominator
            color = _sample_gradient(colors, position)
            pixels[x, y] = color
    return image


@lru_cache(maxsize=32)
def _base_canvas(width: int, height: int, padding: int, gradient_name: str, radius: int) -> Image.Image:
    return _gradient_background(width, height, gradient_name).copy()


@lru_cache(maxsize=16)
def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


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


def _draw_cursor(draw: ImageDraw.ImageDraw, x: float, y: int, font, color: str, cursor: str) -> None:
    ascent, descent = font.getmetrics()
    height = ascent + descent - 2
    if cursor == "block":
        draw.rectangle((x + 1, y, x + 10, y + height), fill=color)
    elif cursor == "underline":
        draw.rectangle((x + 1, y + height - 3, x + 13, y + height), fill=color)
    else:
        draw.rectangle((x + 1, y, x + 3, y + height), fill=color)


def _token_chars(code: str, language: str, theme_name: str) -> list[dict]:
    lexer = _lexer(language)
    line = 0
    color = syntax_palette(theme_name)["base"]
    chars = []

    for token, text in lexer.get_tokens(code):
        color = syntax_color(theme_name, token)
        for char in text:
            chars.append({"text": char, "line": line, "color": color})
            if char == "\n":
                line += 1

    return chars


def _visible_counts(chars: list[dict], typing_mode: str, frame_step: int) -> list[int]:
    total = len(chars)
    if typing_mode == "line":
        counts = [0]
        for index, char in enumerate(chars, start=1):
            next_char = chars[index] if index < total else None
            if next_char is None or next_char["line"] != char["line"]:
                counts.append(index)
        return _unique_counts(counts, total)

    if typing_mode == "word":
        counts = [0]
        has_word_char = False
        for index, char in enumerate(chars, start=1):
            text = char["text"]
            next_char = chars[index] if index < total else None
            is_space = text.isspace()
            next_is_space = bool(next_char and next_char["text"].isspace())
            next_is_same_line = bool(next_char and next_char["line"] == char["line"])

            has_word_char = has_word_char or not is_space
            if next_char is None or not next_is_same_line or (has_word_char and is_space and not next_is_space):
                counts.append(index)
                has_word_char = False
        return _unique_counts(counts, total)

    counts = list(range(0, total + 1, frame_step))
    if not counts or counts[-1] != total:
        counts.append(total)
    return counts


def _unique_counts(counts: list[int], total: int) -> list[int]:
    clean_counts = []
    seen = set()
    for count in counts:
        bounded = max(0, min(total, count))
        if bounded not in seen:
            seen.add(bounded)
            clean_counts.append(bounded)
    if not clean_counts or clean_counts[-1] != total:
        clean_counts.append(total)
    return clean_counts


def _limit_counts(counts: list[int], max_frames: int) -> list[int]:
    if len(counts) <= max_frames:
        return counts
    if max_frames < 2:
        return [counts[0], counts[-1]]
    limited = []
    for index in range(max_frames):
        source_index = round(index * (len(counts) - 1) / (max_frames - 1))
        value = counts[source_index]
        if not limited or limited[-1] != value:
            limited.append(value)
    if limited[-1] != counts[-1]:
        limited.append(counts[-1])
    return limited


def _frame_duration(options: RenderOptions, frame_step: int) -> int:
    if options.typing_mode == "line":
        return max(20, min(1000, int(options.speed_ms) + int(options.line_pause_ms)))
    if options.typing_mode == "word":
        return max(20, min(600, int(options.speed_ms) * 4))
    return max(20, min(250, int(options.speed_ms) * frame_step))


def _scaled_frame_duration(options: RenderOptions, frame_step: int, original_frame_count: int, final_frame_count: int) -> int:
    base = _frame_duration(options, frame_step)
    if final_frame_count <= 0:
        return base
    factor = max(1.0, original_frame_count / final_frame_count)
    return max(20, min(1200, int(base * factor)))


def _active_line(chars: list[dict], visible_count: int) -> int:
    if visible_count <= 0:
        return 0
    for char in reversed(chars[:visible_count]):
        return char["line"]
    return 0


def _lexer(language: str):
    language_key = (language or "").strip().lower()
    lexer_name = LANGUAGE_LEXERS.get(language_key, language_key or "text")
    try:
        return get_lexer_by_name(lexer_name)
    except ClassNotFound:
        return TextLexer()


def _gif_font_size(font_size: int, frame_width: int) -> int:
    base_size = max(12, min(32, int(font_size)))
    scale = max(1.0, frame_width / PREVIEW_DISPLAY_WIDTH)
    return max(12, min(96, round(base_size * scale)))


def _gradient_enabled(options: RenderOptions) -> bool:
    return str(options.background_style).lower() == "gradient" and not options.flush_frame


def _canvas_padding(options: RenderOptions, width: int, height: int) -> int:
    high = max(18, int(min(width, height) * 0.18))
    return max(18, min(high, int(options.canvas_padding)))


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        return (0, 0, 0)
    return tuple(int(clean[index : index + 2], 16) for index in (0, 2, 4))


def _load_font(font_family: str, size: int):
    candidates = _font_candidates(font_family)
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _font_candidates(font_family: str) -> list[Path]:
    requested_fonts = [item.strip().strip("\"'").lower() for item in font_family.split(",")]
    font_map = {
        "cascadia code": [Path("C:/Windows/Fonts/CascadiaCode.ttf"), Path("C:/Windows/Fonts/CascadiaMono.ttf")],
        "cascadia mono": [Path("C:/Windows/Fonts/CascadiaMono.ttf"), Path("C:/Windows/Fonts/CascadiaCode.ttf")],
        "consolas": [Path("C:/Windows/Fonts/consola.ttf")],
        "lucida console": [Path("C:/Windows/Fonts/lucon.ttf")],
    }
    fallback = [
        Path("C:/Windows/Fonts/CascadiaCode.ttf"),
        Path("C:/Windows/Fonts/CascadiaMono.ttf"),
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/lucon.ttf"),
    ]

    candidates: list[Path] = []
    for name in requested_fonts:
        candidates.extend(font_map.get(name, []))
    candidates.extend(fallback)

    unique_candidates = []
    seen = set()
    for path in candidates:
        if path not in seen:
            seen.add(path)
            unique_candidates.append(path)
    return unique_candidates
