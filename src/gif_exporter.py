"""Video frames sampled from the same TextMate tokens and timeline as HTML.

MP4 is streamed to the encoder, never reduced to a handful of repeated frames.
GIF is a smaller, 20 fps delivery format with an explicit duration limit.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from .renderer import RenderOptions, _canvas_padding, _gradient_enabled
from .syntax_style import highlight_code, editor_theme
from .typing_timeline import build_timeline
from .gradients import gradient_stops

VIDEO_FPS = 60
FONT_DIR = Path(__file__).resolve().parents[1] / 'static' / 'fonts'


class ExportLimitError(ValueError):
    pass


def _ease(value):
    return 1 - (1 - max(0, min(1, value))) ** 4


def _smoothstep(value):
    value = max(0, min(1, value))
    return value ** 3 * (value * (value * 6 - 15) + 10)


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


class EditorFrame:
    """Immutable chrome and clipping assets shared by every sampled frame."""

    def __init__(self, renderer, labels=()):
        r = renderer
        s = r.render_scale
        self.renderer = r
        self.template = Image.new('RGB', (r.ew, r.eh), r.bg)
        draw = ImageDraw.Draw(self.template)
        chrome = _rgb(r.theme['chrome_bg'], r.bg)
        if r.chrome:
            top = _blend(chrome, r.fg, .10)
            for y in range(r.chrome):
                draw.line((0, y, r.ew, y), fill=_blend(top, chrome, y/max(1, r.chrome-1)))
            for i, color in enumerate(('#ff5f57', '#febc2e', '#28c840')):
                draw.ellipse(((20+i*17)*s, 18*s, (29+i*17)*s, 27*s), fill=color, outline=(25,25,25))
            draw.line((0,r.chrome,r.ew,r.chrome), fill=_blend(r.bg,r.fg,.10), width=r.border)
        self.headers = {}
        if r.chrome and labels:
            font = _font('JetBrains Mono', 8*s)
            for label in labels:
                header = self.template.crop((0,0,r.ew,r.chrome+r.border))
                badge = ImageDraw.Draw(header)
                bx = r.ew-font.getlength(label)-30*s
                badge.rounded_rectangle((bx,14*s,r.ew-14*s,30*s), radius=8*s,
                                        fill=_blend(chrome,r.fg,.04), outline=_blend(chrome,r.fg,.12))
                badge.text(((bx+r.ew-14*s)/2,22*s),label,font=font,
                           fill=_blend(r.bg,r.fg,.68),anchor='mm')
                self.headers[label] = header
        self.mask = Image.new('L', self.template.size)
        ImageDraw.Draw(self.mask).rounded_rectangle((0,0,r.ew-1,r.eh-1),radius=r.radius,fill=255)

    def compose(self, surface, time, start_delay, label=None):
        r = self.renderer
        editor = self.template.copy()
        editor.paste(surface,(r.border,r.chrome+r.border))
        if label in self.headers:
            editor.paste(self.headers[label],(0,0))
        draw = ImageDraw.Draw(editor)
        draw.rounded_rectangle((0,0,r.ew-1,r.eh-1),radius=r.radius,
                               outline=_blend(r.bg,r.fg,.17),width=r.border)
        b = r.border
        draw.rounded_rectangle((b,b,r.ew-b-1,r.eh-b-1),radius=max(0,r.radius-b),
                               outline=_blend(r.bg,r.fg,.035),width=b)
        mask = self.mask
        entrance = _smoothstep(time/max(1,min(650,start_delay or 1)))
        if entrance < 1:
            scale = .992+entrance*.008
            size = (max(1,round(r.ew*scale)),max(1,round(r.eh*scale)))
            editor = editor.resize(size,Image.Resampling.LANCZOS)
            mask = mask.resize(size,Image.Resampling.LANCZOS).point(
                lambda value: round(value*(.76+.24*entrance)))
        result = r.base.copy()
        px = r.padding_x+round((r.ew-editor.width)/2)
        py = r.padding_y+round((r.eh-editor.height)/2)+round((1-entrance)*14*r.render_scale)
        result.paste(editor,(px,py),mask)
        return result


class FrameRenderer:
    def __init__(self, code: str, options: RenderOptions, render_scale: float = 1):
        self.options = o = options
        self.render_scale = s = render_scale
        self.border = max(1, round(s))
        self.radius = o.radius*s
        self.highlight = highlight_code(code, o.language, o.theme_name)
        self.timeline = build_timeline(self.highlight, o)
        self.times = [e['at'] for e in self.timeline['events']]
        self.duration = self.timeline['duration']
        self.theme = editor_theme(self.highlight)
        self.bg = _rgb(self.highlight['background'])
        self.fg = _rgb(self.highlight['foreground'])
        self.width, self.height = round(o.width*s), round(o.height*s)
        self.padding_y = round(_canvas_padding(o)*s) if _gradient_enabled(o) else 0
        self.padding_x = self.padding_y * 2
        self.padding = self.padding_y  # Backwards-compatible public measurement.
        self.ew, self.eh = self.width-self.padding_x*2, self.height-self.padding_y*2
        self.chrome = round(44*s) if o.show_window_chrome else 0
        self.vw, self.vh = self.ew-2*self.border, self.eh-self.chrome-2*self.border
        self.size = o.font_size*s
        self.lh = self.size * o.line_height
        self.content_x = round(((54 if o.show_line_numbers else 18) + (24 if o.show_diff_gutter else 0) + 16)*s)
        self.fonts = [_font(o.font_family, self.size, flag) for flag in range(4)]
        self.number_font = _font(o.font_family, self.size*.82)
        self.line_images, self.line_chars = [], []
        self.positions = [(self.content_x, 30*s + (self.lh-self.size)/2, 0)]
        self._layout()
        self.scroll_keys = []
        self.scroll_times = []
        target_x = target_y = 0
        max_y = max(0, 30*s + len(self.highlight['lines'])*self.lh + 44*s-self.vh)
        max_x = max(0, max((line.width for line in self.line_images), default=0)+self.content_x+32*s-self.vw)
        for event in self.timeline['events']:
            x, y, _ = self.positions[event['count']]
            sx = max(0, min(max_x, x-self.vw+60*s))
            sy = max(0, min(max_y, y-self.vh+self.lh*2.5))
            if (sx, sy) != (target_x, target_y):
                previous = self._scroll_at(event['at'])
                self.scroll_keys.append((previous[0], previous[1], sx, sy))
                self.scroll_times.append(event['at'])
                target_x, target_y = sx, sy
        self.base = self._background()
        self.editor_frame = EditorFrame(self)
        self.line_times = [[item[4] for item in items] for items in self.line_chars]

    def _layout(self):
        s = self.render_scale
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
                    self.positions.append((self.content_x+x, 30*s+line_no*self.lh+(self.lh-self.size)/2, line_no))
                    char_index += 1
            strip = Image.new('RGBA', (max(1, math.ceil(x)+round(6*s)), math.ceil(self.lh)), (0,0,0,0))
            draw = ImageDraw.Draw(strip)
            for char, x, advance, token, _, _ in items:
                font = self.fonts[token['fontStyle'] & 3]
                ascent, descent = font.getmetrics()
                baseline = (self.lh-ascent-descent)/2+ascent
                if char != '\t':
                    draw.text((x, baseline), char, font=font, fill=token['color'], anchor='ls')
                if token['fontStyle'] & 4:
                    draw.line((x, baseline+2*s, x+advance, baseline+2*s), fill=token['color'],width=self.border)
            self.line_images.append(strip)
            self.line_chars.append(items)
            if line_no < len(self.highlight['lines'])-1:
                self.positions.append((self.content_x, 30*s+(line_no+1)*self.lh+(self.lh-self.size)/2, line_no+1))
                char_index += 1

    def _background(self):
        s = self.render_scale
        if not self.padding:
            return Image.new('RGB', (self.width, self.height), self.bg)
        colors = np.array([_rgb(color) for color in gradient_stops(self.options.gradient_name)], dtype=np.float32)
        yy = np.arange(self.height, dtype=np.float32)[:, None]
        xx = np.arange(self.width, dtype=np.float32)[None, :]
        position = (xx+yy)/max(1, self.width+self.height-2)*(len(colors)-1)
        index = np.minimum(len(colors)-2, position.astype(np.int32))
        weight = (position-index.astype(np.float32))[..., None]
        array = colors[index]*(1-weight)+colors[index+1]*weight
        nx = xx / max(1, self.width-1)
        ny = yy / max(1, self.height-1)
        for center_x, center_y, spread_x, spread_y, color, strength in [
            (.13, .43, .30, .55, np.array((22, 105, 255), dtype=np.float32), .18),
            (.88, .55, .30, .52, np.array((31, 188, 105), dtype=np.float32), .13),
            (.50, .04, .48, .36, np.array((126, 174, 229), dtype=np.float32), .055),
        ]:
            glow = np.exp(-2.2 * (((nx-center_x)/spread_x)**2 + ((ny-center_y)/spread_y)**2)) * strength
            array = array*(1-glow[..., None]) + color*glow[..., None]
        edge = np.clip(((nx-.5)/.62)**2 + ((ny-.46)/.70)**2, 0, 1)
        array *= (1-.34*edge)[..., None]
        grid = ((xx % round(48*s) == 0) | (yy % round(48*s) == 0)) & (edge < .78)
        array[grid] = array[grid]*.985 + np.array((129, 181, 230), dtype=np.float32)*.015
        image = Image.fromarray(array.astype('uint8'))
        for offset, blur, alpha in [(22, 44, 150), (10, 18, 126), (3, 6, 72)]:
            shadow = Image.new('RGBA', image.size)
            draw = ImageDraw.Draw(shadow)
            draw.rounded_rectangle(
                (self.padding_x, self.padding_y+round(offset*s),
                 self.width-self.padding_x, self.height-self.padding_y+round(offset*s)),
                radius=self.radius, fill=(0,0,0,alpha))
            shadow = shadow.filter(ImageFilter.GaussianBlur(blur*s))
            image.paste(shadow, (0,0), shadow)
        return image

    def _scroll_at(self, time):
        index = bisect_right(self.scroll_times, time)-1
        if index < 0: return 0, 0
        fx, fy, x, y = self.scroll_keys[index]
        t = _smoothstep((time-self.scroll_times[index])/260)
        return fx+(x-fx)*t, fy+(y-fy)*t

    def frame(self, time: float) -> Image.Image:
        o = self.options
        s = self.render_scale
        event_index = bisect_right(self.times, time)-1
        event = self.timeline['events'][event_index] if event_index >= 0 else None
        count = event['count'] if event else 0
        x, y, active = self.positions[count]
        scroll_x, scroll_y = self._scroll_at(time)
        surface = Image.new('RGB', (self.vw, self.vh), self.bg)
        draw = ImageDraw.Draw(surface)
        for line_no, strip in enumerate(self.line_images):
            row_y = 30*s+line_no*self.lh-scroll_y
            if row_y+self.lh < 0 or row_y >= self.vh: continue
            if o.show_line_numbers:
                color = _blend(self.bg,self.fg,.72) if line_no == active else _blend(self.bg, _rgb(self.theme['muted'], self.bg), .48)
                ascent, descent = self.number_font.getmetrics()
                baseline = row_y+(self.lh-ascent-descent)/2+ascent
                draw.text((self.content_x-26*s-scroll_x, baseline), str(line_no+1), font=self.number_font, fill=color, anchor='rs')
            if o.show_diff_gutter:
                draw.text((10*s-scroll_x, row_y), '+', font=self.number_font, fill=self.theme['plus'])
            items = self.line_chars[line_no]
            if not items: continue
            # Crop settled glyphs once, then place each frontier glyph with the
            # same eased opacity and short vertical settle used by the HTML frame.
            settled_count = bisect_right(self.line_times[line_no], time-self.timeline['fadeMs'])
            settled = items[settled_count-1] if settled_count else None
            end_x = math.ceil(settled[1]+settled[2]) if settled else 0
            left = max(0, math.floor(scroll_x-self.content_x))
            right = min(strip.width, math.ceil(scroll_x+self.vw-self.content_x))
            if right <= left: continue
            settled_right = min(right, end_x)
            if settled_right > left:
                region = strip.crop((left, 0, settled_right, strip.height))
                surface.paste(region, (round(self.content_x+left-scroll_x), round(row_y)), region)
            for char, char_x, advance, token, at, index in items[settled_count:]:
                if at > time: break
                start, end = max(left, math.floor(char_x)), min(right, math.ceil(char_x+advance+2*s))
                if end <= start: continue
                amount = _ease((time-at)/self.timeline['fadeMs'])
                glyph = strip.crop((start, 0, end, strip.height))
                alpha = np.asarray(glyph.getchannel('A')).copy()
                glyph.putalpha(Image.fromarray((alpha*amount).astype('uint8')))
                settle_y = round((1-amount)*3.5*s)
                surface.paste(glyph, (round(self.content_x+start-scroll_x), round(row_y)+settle_y), glyph)
        age = time-(event['at'] if event else 0)
        before_count = self.timeline['events'][event_index-1]['count'] if event_index > 0 else 0
        bx, by, before_line = self.positions[before_count]
        next_at = self.times[event_index+1] if event_index+1 < len(self.times) else None
        available = max(16, next_at-event['at']) if event and next_at is not None else self.timeline.get('cursorEaseMs',70)
        travel = min(self.timeline.get('cursorEaseMs',70), available)
        if before_line == active: x = bx+(x-bx)*_smoothstep(age/travel)
        if time < self.timeline['typingEnd']+1100 and (age < 350 or int((age-350)/500)%2 == 0):
            cx, cy = x-scroll_x, y-scroll_y
            color = _rgb(self.theme['accent'], self.bg)
            line_alpha = _ease(age/90) if before_line != active else 1
            if o.cursor == 'underline': draw.rectangle((cx,cy+self.size,cx+self.size*.6,cy+self.size+self.border),fill=color)
            elif o.cursor == 'block': draw.rectangle((cx,cy,cx+self.size*.6,cy+self.size),fill=_blend(self.bg,color,.55*line_alpha))
            else: draw.rectangle((cx,cy,cx+self.border,cy+self.size),fill=_blend(self.bg,color,line_alpha))
        return self.editor_frame.compose(surface,time,o.start_delay_ms)

    def frame_key(self, time):
        event_index = bisect_right(self.times,time)-1
        at = self.times[event_index] if event_index >= 0 else 0
        scroll_index = bisect_right(self.scroll_times,time)-1
        scroll_end = self.scroll_times[scroll_index]+260 if scroll_index >= 0 else 0
        if time >= max(at+self.timeline['fadeMs'],scroll_end,min(650,self.options.start_delay_ms or 1)):
            age = time-at
            cursor = time < self.timeline['typingEnd']+1100 and (age < 350 or int((age-350)/500)%2 == 0)
            return ('hold',event_index,cursor)
        return time



def build_typing_mp4(code: str, options: RenderOptions, frame_step: int = 3, fps: int = VIDEO_FPS) -> bytes:
    from .video_export import encode_mp4, mp4_render_scale

    renderer = FrameRenderer(code, options, render_scale=mp4_render_scale(options))
    if renderer.duration > 180000:
        raise ExportLimitError('MP4 is limited to 3 minutes. Increase typing speed or export HTML for longer scenes.')
    return encode_mp4(renderer, 'code-typing-', fps)


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
