"""Video frames sampled from the same TextMate tokens and timeline as HTML.

MP4 is streamed to the encoder, never reduced to a handful of repeated frames.
GIF is a smaller, 20 fps delivery format with an explicit duration limit.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from .gradients import gradient_stops
from .renderer import RenderOptions, _canvas_padding, _gradient_enabled
from .syntax_style import highlight_code, editor_theme
from .typing_timeline import build_timeline

VIDEO_FPS = 60
FONT_DIR = Path(__file__).resolve().parents[1] / 'static' / 'fonts'


class ExportLimitError(ValueError):
    pass


def _ease(value):
    return 1 - (1 - max(0, min(1, value))) ** 3


def _rgb(value, background=(0, 0, 0)):
    channels = ImageColor.getrgb(value)
    if len(channels) == 4:
        alpha = channels[3] / 255
        return tuple(round(channels[i] * alpha + background[i] * (1-alpha)) for i in range(3))
    return channels


def _blend(a, b, amount):
    return tuple(round(x + (y-x)*amount) for x, y in zip(a, b))


def _font(family, size, flags=0):
    suffix = 'BoldItalic' if flags & 3 == 3 else 'Italic' if flags & 1 else 'Bold' if flags & 2 else 'Regular'
    # Honor fonts installed on this host; the bundled family is the portable fallback.
    windows = {'consolas': 'consola', 'cascadia code': 'CascadiaCode', 'menlo': 'Menlo', 'fira code': 'FiraCode'}
    first = family.split(',')[0].strip().strip('"').lower()
    candidates = []
    if first in windows:
        name = windows[first]
        if first == 'consolas': name = {0:'consola', 1:'consolai', 2:'consolab', 3:'consolaz'}[flags & 3]
        candidates.append(Path('C:/Windows/Fonts') / f'{name}.ttf')
    candidates.append(FONT_DIR / f'JetBrainsMono-{suffix}.ttf')
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), max(8, round(size)))
    raise RuntimeError('Bundled JetBrains Mono font is missing. Restore static/fonts.')


class FrameRenderer:
    def __init__(self, code: str, options: RenderOptions):
        self.options = o = options
        self.highlight = highlight_code(code, o.language, o.theme_name, o.title)
        self.timeline = build_timeline(self.highlight, o)
        self.times = [e['at'] for e in self.timeline['events']]
        self.duration = self.timeline['duration']
        self.theme = editor_theme(self.highlight)
        self.bg = _rgb(self.highlight['background'])
        self.fg = _rgb(self.highlight['foreground'])
        self.width, self.height = o.width, o.height
        self.padding = _canvas_padding(o) if _gradient_enabled(o) else 0
        self.ew, self.eh = self.width-self.padding*2, self.height-self.padding*2
        self.chrome = 48 if o.show_window_chrome else 0
        self.vw, self.vh = self.ew-2, self.eh-self.chrome-2
        self.size = o.font_size
        self.lh = o.font_size * o.line_height
        self.content_x = (54 if o.show_line_numbers else 18) + (24 if o.show_diff_gutter else 0) + 16
        self.fonts = [_font(o.font_family, self.size, flag) for flag in range(4)]
        self.small = _font('JetBrains Mono', 12)
        self.number_font = _font(o.font_family, self.size*.82)
        self.line_images, self.line_chars = [], []
        self.positions = [(self.content_x, 28 + (self.lh-self.size)/2, 0)]
        self._layout()
        self.scroll_keys = []
        self.scroll_times = []
        target_x = target_y = 0
        max_y = max(0, 28 + len(self.highlight['lines'])*self.lh + 40-self.vh)
        max_x = max(0, max((line.width for line in self.line_images), default=0)+self.content_x+32-self.vw)
        for event in self.timeline['events']:
            x, y, _ = self.positions[event['count']]
            sx = max(0, min(max_x, x-self.vw+60))
            sy = max(0, min(max_y, y-self.vh+self.lh*2.5))
            if (sx, sy) != (target_x, target_y):
                previous = self._scroll_at(event['at'])
                self.scroll_keys.append((previous[0], previous[1], sx, sy))
                self.scroll_times.append(event['at'])
                target_x, target_y = sx, sy
        self.base = self._background()

    def _layout(self):
        char_index = 0
        for line_no, tokens in enumerate(self.highlight['lines']):
            items, x = [], 0.0
            for token in tokens:
                font = self.fonts[token['fontStyle'] & 3]
                for char in token['content']:
                    advance = float(font.getlength(char)) if char != '\t' else float(font.getlength(' '))*2 - x % (float(font.getlength(' '))*2)
                    at = self.timeline['chars'][char_index]['at']
                    items.append((char, x, advance, token, at, char_index))
                    x += advance
                    self.positions.append((self.content_x+x, 28+line_no*self.lh+(self.lh-self.size)/2, line_no))
                    char_index += 1
            strip = Image.new('RGBA', (max(1, math.ceil(x)+6), math.ceil(self.lh)), (0,0,0,0))
            draw = ImageDraw.Draw(strip)
            for char, x, advance, token, _, _ in items:
                font = self.fonts[token['fontStyle'] & 3]
                ascent, descent = font.getmetrics()
                baseline = (self.lh-ascent-descent)/2+ascent
                if char != '\t':
                    draw.text((x, baseline), char, font=font, fill=token['color'], anchor='ls')
                if token['fontStyle'] & 4:
                    draw.line((x, baseline+2, x+advance, baseline+2), fill=token['color'])
            self.line_images.append(strip)
            self.line_chars.append(items)
            if line_no < len(self.highlight['lines'])-1:
                self.positions.append((self.content_x, 28+(line_no+1)*self.lh+(self.lh-self.size)/2, line_no+1))
                char_index += 1

    def _background(self):
        if not self.padding:
            return Image.new('RGB', (self.width, self.height), self.bg)
        # Vectorized equivalent of the 135-degree CSS gradient.
        colors = np.array([_rgb(c) for c in gradient_stops(self.options.gradient_name)], dtype=float)
        yy, xx = np.mgrid[0:self.height, 0:self.width]
        position = (xx+yy)/max(1, self.width+self.height-2)*(len(colors)-1)
        index = np.minimum(len(colors)-2, position.astype(int))
        weight = (position-index)[..., None]
        array = colors[index]*(1-weight)+colors[index+1]*weight
        image = Image.fromarray(array.astype('uint8'))
        shadow = Image.new('RGBA', image.size)
        draw = ImageDraw.Draw(shadow)
        draw.rounded_rectangle((self.padding, self.padding+16, self.width-self.padding, self.height-self.padding+16), radius=self.options.radius, fill=(0,0,0,110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(22))
        image.paste(shadow, (0,0), shadow)
        return image

    def _scroll_at(self, time):
        index = bisect_right(self.scroll_times, time)-1
        if index < 0: return 0, 0
        fx, fy, x, y = self.scroll_keys[index]
        t = _ease((time-self.scroll_times[index])/220)
        return fx+(x-fx)*t, fy+(y-fy)*t

    def frame(self, time: float) -> Image.Image:
        o = self.options
        event_index = bisect_right(self.times, time)-1
        event = self.timeline['events'][event_index] if event_index >= 0 else None
        count = event['count'] if event else 0
        x, y, active = self.positions[count]
        scroll_x, scroll_y = self._scroll_at(time)
        editor = Image.new('RGB', (self.ew, self.eh), self.bg)
        surface = Image.new('RGB', (self.vw, self.vh), self.bg)
        draw = ImageDraw.Draw(surface)
        active_y = 28+active*self.lh-scroll_y
        draw.rectangle((0, active_y, self.vw, active_y+self.lh), fill=_blend(self.bg, self.fg, .03))
        for line_no, strip in enumerate(self.line_images):
            row_y = 28+line_no*self.lh-scroll_y
            if row_y+self.lh < 0 or row_y >= self.vh: continue
            if o.show_line_numbers:
                color = self.fg if line_no == active else _blend(self.bg, _rgb(self.theme['muted'], self.bg), .55)
                ascent, descent = self.number_font.getmetrics()
                baseline = row_y+(self.lh-ascent-descent)/2+ascent
                draw.text((self.content_x-26-scroll_x, baseline), str(line_no+1), font=self.number_font, fill=color, anchor='rs')
            if o.show_diff_gutter:
                draw.text((10-scroll_x, row_y), '+', font=self.number_font, fill=self.theme['plus'])
            items = self.line_chars[line_no]
            if not items: continue
            # Crop settled glyphs once. Only the reveal frontier needs alpha work.
            settled = [item for item in items if item[4]+self.timeline['fadeMs'] <= time]
            end_x = math.ceil(settled[-1][1]+settled[-1][2]) if settled else 0
            left = max(0, math.floor(scroll_x-self.content_x))
            right = min(strip.width, math.ceil(scroll_x+self.vw-self.content_x))
            if right <= left: continue
            region = strip.crop((left, 0, right, strip.height))
            alpha = np.asarray(region.getchannel('A')).copy()
            if end_x < right:
                alpha[:, max(0,end_x-left):] = 0
                for char, char_x, advance, token, at, index in items[len(settled):]:
                    if at > time: break
                    start, end = max(left, math.floor(char_x)), min(right, math.ceil(char_x+advance))
                    if end <= start: continue
                    amount = max(0,min(1,(time-at)/self.timeline['fadeMs']))
                    original = np.asarray(strip.getchannel('A').crop((start,0,end,strip.height)))
                    alpha[:, start-left:end-left] = (original*amount).astype('uint8')
            region.putalpha(Image.fromarray(alpha))
            surface.paste(region, (round(self.content_x+left-scroll_x), round(row_y)), region)
        age = time-(event['at'] if event else 0)
        before_count = self.timeline['events'][event_index-1]['count'] if event_index > 0 else 0
        bx, by, before_line = self.positions[before_count]
        if before_line == active: x = bx+(x-bx)*_ease(age/45)
        if time < self.timeline['typingEnd']+1100 and (age < 350 or int((age-350)/500)%2 == 0):
            cx, cy = x-scroll_x, y-scroll_y
            color = _rgb(self.theme['accent'], self.bg)
            if o.cursor == 'underline': draw.rectangle((cx,cy+self.size,cx+self.size*.6,cy+self.size+1),fill=color)
            elif o.cursor == 'block': draw.rectangle((cx,cy,cx+self.size*.6,cy+self.size),fill=_blend(self.bg,color,.55))
            else: draw.rectangle((cx,cy,cx+1,cy+self.size),fill=color)
        editor.paste(surface, (1,self.chrome+1))
        draw = ImageDraw.Draw(editor)
        if self.chrome:
            draw.rectangle((0,0,self.ew,self.chrome),fill=_rgb(self.theme['chrome_bg'],self.bg))
            for i,color in enumerate(('#ff5f57','#febc2e','#28c840')):
                draw.ellipse((22+i*18,19,32+i*18,29),fill=color)
            title = o.title if len(o.title)<55 else o.title[:52]+'…'
            draw.text((self.ew/2,24),title,font=self.small,fill=_blend(self.bg,self.fg,.82),anchor='mm')
            draw.line((0,self.chrome,self.ew,self.chrome),fill=_blend(self.bg,self.fg,.08))
        draw.rounded_rectangle((0,0,self.ew-1,self.eh-1),radius=o.radius,outline=_blend(self.bg,self.fg,.12))
        mask = Image.new('L',editor.size)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,self.ew-1,self.eh-1),radius=o.radius,fill=255)
        entrance = _ease(time/max(1,min(550,o.start_delay_ms or 1)))
        if entrance < 1: mask = mask.point(lambda value: round(value*(.88+.12*entrance)))
        result = self.base.copy()
        result.paste(editor,(self.padding,self.padding+round((1-entrance)*10)),mask)
        return result


def build_typing_mp4(code: str, options: RenderOptions, frame_step: int = 3, fps: int = VIDEO_FPS) -> bytes:
    renderer = FrameRenderer(code, options)
    if renderer.duration > 180000:
        raise ExportLimitError('MP4 is limited to 3 minutes. Increase typing speed or export HTML for longer scenes.')
    with TemporaryDirectory(prefix='code-typing-') as directory:
        path = Path(directory) / 'animation.mp4'
        with imageio.get_writer(str(path), fps=fps, codec='libx264', quality=8, macro_block_size=1, pixelformat='yuv420p') as writer:
            for frame_no in range(math.ceil(renderer.duration*fps/1000)):
                writer.append_data(np.asarray(renderer.frame(frame_no*1000/fps)))
        return path.read_bytes()


def build_typing_gif(code: str, options: RenderOptions, frame_step: int = 3) -> bytes:
    renderer = FrameRenderer(code, options)
    if renderer.duration > 45000:
        raise ExportLimitError('GIF is limited to 45 seconds. Increase typing speed, shorten the snippet, or choose MP4/HTML.')
    scale = min(1, 700/renderer.width, 700/renderer.height)
    size = (round(renderer.width*scale),round(renderer.height*scale))
    # One palette for the whole clip prevents theme colors flickering between frames.
    poster = renderer.frame(renderer.timeline['typingEnd']+200).resize(size,Image.Resampling.LANCZOS)
    quantized = poster.quantize(colors=256)
    original = quantized.getpalette()
    # Reserve theme colors from every line, including lines already scrolled out.
    colors = list(dict.fromkeys([renderer.bg, renderer.fg] +
                  [_rgb(token['color'],renderer.bg) for line in renderer.highlight['lines'] for token in line]))
    colors = list(dict.fromkeys(colors + [tuple(original[i:i+3]) for i in range(0,len(original),3)]))[:256]
    colors.extend([(0,0,0)]*(256-len(colors)))
    palette = Image.new('P',(1,1))
    palette.putpalette([channel for color in colors for channel in color])
    frames = []
    for time in range(0, math.ceil(renderer.duration), 50):
        frame = renderer.frame(time).resize(size,Image.Resampling.LANCZOS)
        frames.append(frame.quantize(palette=palette,dither=Image.Dither.NONE))
    output = BytesIO()
    loop = {'loop': 0} if options.loop else {}
    frames[0].save(output,format='GIF',save_all=True,append_images=frames[1:],duration=50,disposal=2,optimize=False,**loop)
    return output.getvalue()
