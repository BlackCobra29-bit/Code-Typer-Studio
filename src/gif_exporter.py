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
MAX_GIF_FRAMES = 8
FINAL_HOLD_FRAMES = 1


def build_typing_gif(code: str, options: RenderOptions, frame_step: int = 3) -> bytes:
    theme = THEMES.get(options.theme_name, THEMES["VS Code Dark+"])
    width = max(520, min(1600, int(options.width)))
    height = max(320, min(1400, int(options.height)))
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
    counts = _sample_counts(total, frame_step)
    line_count = max(1, len((code or " ").split("\n")))
    line_ranges = _line_ranges(chars, line_count)
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
                line_count=line_count,
                line_ranges=line_ranges,
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
        frames.extend([frames[-1].copy() for _ in range(FINAL_HOLD_FRAMES)])

    output = BytesIO()
    duration = _frame_duration(options.speed_ms, total, len(counts))
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
    line_count: int,
    line_ranges: list[tuple[int, int]],
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

    cursor_x = content_x
    cursor_y = top_y

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

    for line in range(first_line, min(line_count, first_line + max_visible_lines)):
        start, end = line_ranges[line]
        end = min(end, visible_count)
        if end <= start:
            continue
        y = top_y + (line - first_line) * line_height
        x = content_x
        current_color = None
        text_run = []
        for char in chars[start:end]:
            if char["text"] != "\n":
                if current_color is None:
                    current_color = char["color"]
                if char["color"] != current_color:
                    text = "".join(text_run)
                    draw.text((x, y + 1), text, font=font, fill=current_color)
                    x += draw.textlength(text, font=font)
                    text_run = []
                    current_color = char["color"]
                text_run.append(char["text"])
        if text_run:
            text = "".join(text_run)
            draw.text((x, y + 1), text, font=font, fill=current_color)
            x += draw.textlength(text, font=font)
        if line == active_line:
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


def _active_line(chars: list[dict], visible_count: int) -> int:
    if visible_count <= 0:
        return 0
    for index in range(min(visible_count, len(chars)) - 1, -1, -1):
        return chars[index]["line"]
    return 0


def _sample_counts(total: int, frame_step: int) -> list[int]:
    if total <= 0:
        return [0]

    requested_step = max(1, int(frame_step))
    frame_count = min(MAX_GIF_FRAMES, max(2, (total // requested_step) + 1))
    if frame_count <= 2:
        return [0, total]

    counts = [round(total * index / (frame_count - 1)) for index in range(frame_count)]
    counts[0] = 0
    counts[-1] = total
    deduped = []
    for count in counts:
        count = max(0, min(total, count))
        if not deduped or deduped[-1] != count:
            deduped.append(count)
    if deduped[-1] != total:
        deduped.append(total)
    return deduped


def _line_ranges(chars: list[dict], line_count: int) -> list[tuple[int, int]]:
    ranges = [(0, 0) for _ in range(line_count)]
    line_start = 0
    current_line = 0
    for index, char in enumerate(chars):
        if char["text"] == "\n":
            if current_line < line_count:
                ranges[current_line] = (line_start, index + 1)
            current_line += 1
            line_start = index + 1
    if current_line < line_count:
        ranges[current_line] = (line_start, len(chars))
    return ranges


def _frame_duration(speed_ms: int, total_chars: int, frame_count: int) -> int:
    if frame_count <= 1:
        return max(20, min(250, int(speed_ms)))

    playback_ms = max(1400, min(4200, total_chars * max(4, min(120, int(speed_ms))) // 3))
    return max(20, min(180, playback_ms // frame_count))


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
