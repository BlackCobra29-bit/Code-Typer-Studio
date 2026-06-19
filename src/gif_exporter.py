from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from .languages import LANGUAGE_LEXERS
from .renderer import RenderOptions
from .syntax_style import syntax_color, syntax_palette
from .themes import THEMES


PREVIEW_DISPLAY_WIDTH = 700


def build_typing_gif(code: str, options: RenderOptions, frame_step: int = 3) -> bytes:
    theme = THEMES.get(options.theme_name, THEMES["VS Code Dark+"])
    width = max(520, min(1600, int(options.width)))
    height = max(260, min(1400, int(options.height)))
    font_size = _gif_font_size(options.font_size, width)
    line_height = int(font_size * max(1.1, min(2.2, float(options.line_height))))
    chrome_height = 42 if options.show_window_chrome else 0
    gutter_width = 84 if options.show_line_numbers else 30
    content_x = gutter_width + 24
    top_y = chrome_height + 20
    padding_bottom = 24
    font = _load_font(options.font_family, font_size)
    small_font = _load_font(options.font_family, max(10, _gif_font_size(13, width)))
    chars = _token_chars(code or " ", options.language, options.theme_name)
    total = len(chars)
    step = max(1, min(12, int(frame_step)))
    counts = _visible_counts(chars, options.typing_mode, step)

    max_visible_lines = max(1, (height - chrome_height - padding_bottom) // line_height)
    frames = []
    for visible_count in counts:
        active_line = _active_line(chars, visible_count)
        first_line = max(0, active_line - max_visible_lines + 2)
        frames.append(
            _draw_frame(
                chars=chars,
                visible_count=visible_count,
                first_line=first_line,
                max_visible_lines=max_visible_lines,
                active_line=active_line,
                code=code,
                width=width,
                height=height,
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
        )

    if frames:
        frames.extend([frames[-1].copy() for _ in range(6)])

    output = BytesIO()
    duration = _frame_duration(options, step)
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


def _draw_frame(
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


def _frame_duration(options: RenderOptions, frame_step: int) -> int:
    if options.typing_mode == "line":
        return max(20, min(1000, int(options.speed_ms) + int(options.line_pause_ms)))
    if options.typing_mode == "word":
        return max(20, min(600, int(options.speed_ms) * 4))
    return max(20, min(250, int(options.speed_ms) * frame_step))


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
