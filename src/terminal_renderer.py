"""A seekable terminal scene shared by HTML, GIF and native-resolution MP4."""
from __future__ import annotations

import base64
import json
import math
import re
from bisect import bisect_right
from dataclasses import dataclass
from io import BytesIO
from collections import OrderedDict
from threading import Lock
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .gif_exporter import ExportLimitError, _font, _rgb
from .gradients import gradient_css, gradient_stops
from .renderer import _embedded_font_css
from .terminal_style import command_tokens, prompt_tokens, terminal_output_tokens, prefix_tokens, wrap_tokens
from .video_export import encode_mp4, mp4_render_scale

TERMINAL_WIDTH = 700
TERMINAL_HEIGHT = 300
VIDEO_FPS = 30
DEFAULT_TERMINAL_COMMAND = "npm run build"
DEFAULT_TERMINAL_OUTPUT = """> studio@1.0.0 build
> vite build

vite building for production...
✓ 124 modules transformed.

dist/index.html                0.46 kB
dist/assets/index.css          8.24 kB
dist/assets/index.js         142.68 kB

✓ built in 842ms"""
ROOT = Path(__file__).resolve().parents[1]
BODY_COLOR = '#1e1e22'


@dataclass(frozen=True)
class TerminalOptions:
    title: str = 'eminem — zsh'
    prompt: str = 'eminem@macbook ~ %'
    command: str = DEFAULT_TERMINAL_COMMAND
    output: str = DEFAULT_TERMINAL_OUTPUT
    word_speed_ms: int = 320
    output_delay_ms: int = 1000
    loop: bool = True
    width: int = 1280
    height: int = 720
    aspect_ratio: str = '16_9'
    background_style: str = 'gradient'
    gradient_name: str = 'midnight'
    canvas_padding: int = 50


def build_terminal_model(options: TerminalOptions) -> dict:
    o = options
    padded = o.background_style == 'gradient' and o.aspect_ratio != 'display'
    py = min(o.canvas_padding, (o.height-180)//2) if padded else 0
    px = min(o.canvas_padding*2, (o.width-260)//2) if padded else 0
    width, height = o.width-2*px, o.height-2*py
    size = 16 if o.aspect_ratio == 'display' else 20
    cell = _font('JetBrains Mono', size).getlength('M')
    inset, chrome, row_height = 24, 44, round(size*1.5)
    columns = max(4, math.floor((width-2*inset-2)/cell))
    visible = max(1, math.floor((height-chrome-2*inset)/row_height))
    command = command_tokens(o.command.replace('\r\n', '\n').replace('\r', '\n'))
    source = ''.join(t['text'] for t in command)
    events = [{'at': 350+i*o.word_speed_ms, 'count': m.end()}
              for i, m in enumerate(re.finditer(r'\S+\s*|\s+', source))]
    output = terminal_output_tokens(o.output)
    rows = wrap_tokens(output, columns) if output else []
    # A final newline terminates the last output row; it does not add a blank row.
    if rows and not rows[-1] and o.output.endswith(('\n', '\r')):
        rows.pop()
    output_start = (events[-1]['at'] if events else 350)+o.output_delay_ms
    interval = min(65, 1500/max(1, len(rows)))
    done = output_start+len(rows)*interval
    return dict(width=o.width, height=o.height, x=px, y=py, windowWidth=width,
                windowHeight=height, fontSize=size, cellWidth=cell, inset=inset,
                chrome=chrome, rowHeight=row_height, columns=columns, visibleRows=visible,
                prompt=prompt_tokens(o.prompt), command=command, events=events,
                output=rows, outputStart=output_start, outputInterval=interval,
                done=done, duration=done+1800, loop=o.loop, title=o.title)


def terminal_state(model, time):
    times = [event['at'] for event in model['events']]
    index = bisect_right(times, time)-1
    count = model['events'][index]['count'] if index >= 0 else 0
    output_count = min(len(model['output']), max(0, math.floor(
        (time-model['outputStart'])/model['outputInterval'])+1))
    done = time >= model['done']
    cursor = (time < model['outputStart'] or done) and int(time//530) % 2 == 0
    return count, output_count, done, cursor


def terminal_rows(model, state):
    count, output_count, done, _ = state
    rows = wrap_tokens(model['prompt']+prefix_tokens(model['command'], count), model['columns'])
    rows += model['output'][:output_count]
    if done:
        rows += wrap_tokens(model['prompt'], model['columns'])
    # Reserve a cursor cell when a command exactly fills the last row.
    if (not output_count or done) and sum(len(t['text']) for t in rows[-1]) >= model['columns']:
        rows.append([])
    return rows[-model['visibleRows']:]


def build_terminal_html(options: TerminalOptions, standalone: bool = False) -> str:
    model = build_terminal_model(options)
    model['background'] = gradient_css(options.gradient_name) if model['x'] else BODY_COLOR
    payload = base64.b64encode(json.dumps(model, ensure_ascii=False).encode()).decode()
    css = (ROOT/'static/terminal_frame.css').read_text(encoding='utf-8')
    script = (ROOT/'static/terminal_frame.js').read_text(encoding='utf-8')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Terminal animation</title><style>'+_embedded_font_css()+css+
            '</style></head><body><div id="stage"><section id="terminal" aria-label="Terminal">'
            '<header><div class="lights"><i></i><i></i><i></i></div><span id="title"></span></header>'
            '<div id="screen" aria-live="off"></div></section></div>'
            '<script id="terminal-model" type="application/octet-stream">'+payload+
            '</script><script>'+script+'</script></body></html>')


class TerminalFrameRenderer:
    def __init__(self, options: TerminalOptions, render_scale=1.0):
        self.options = options
        self.model = m = build_terminal_model(options)
        self.duration = m['duration']
        self.scale = s = render_scale
        self.width, self.height = round(m['width']*s), round(m['height']*s)
        self.ew, self.eh = round(m['windowWidth']*s), round(m['windowHeight']*s)
        self.fonts = [_font('JetBrains Mono', m['fontSize']*s, flags) for flags in range(4)]
        self._rows = OrderedDict()
        self._row_lock = Lock()
        self.base = self._background()
        self.window = Image.new('RGB', (self.ew, self.eh), BODY_COLOR)
        draw = ImageDraw.Draw(self.window)
        chrome = round(m['chrome']*s)
        for y in range(chrome):
            v = round(51-7*y/max(1,chrome-1))
            draw.line((0,y,self.ew,y), fill=(v,v,v+4))
        draw.line((0,chrome,self.ew,chrome), fill='#111114', width=max(1,round(s)))
        for x,color in [(23,'#ff5f57'),(43,'#febc2e'),(63,'#28c840')]:
            draw.ellipse(((x-6)*s,16*s,(x+6)*s,28*s), fill=color)
        title_font = _font('JetBrains Mono', 13*s, 2)
        title = options.title
        while title and title_font.getlength(title) > self.ew-190*s:
            title = title[:-2]+'…' if len(title)>2 else ''
        draw.text((self.ew/2,22*s),title,font=title_font,fill='#c4c4cd',anchor='mm')
        self.mask = Image.new('L', self.window.size)
        ImageDraw.Draw(self.mask).rounded_rectangle((0,0,self.ew-1,self.eh-1),radius=12*s,fill=255)
        draw.rounded_rectangle((0,0,self.ew-1,self.eh-1),radius=12*s,outline='#515156',width=max(1,round(s)))

    def _background(self):
        m, s = self.model, self.scale
        if not m['x']:
            return Image.new('RGB', (self.width,self.height), BODY_COLOR)
        colors = np.array([_rgb(c) for c in gradient_stops(self.options.gradient_name)],dtype=np.float32)
        yy = np.arange(self.height,dtype=np.float32)[:,None]
        xx = np.arange(self.width,dtype=np.float32)[None,:]
        p = (xx+yy)/max(1,self.width+self.height-2)*(len(colors)-1)
        idx = np.minimum(len(colors)-2,p.astype(np.int32))
        weight = (p-idx.astype(np.float32))[...,None]
        array = colors[idx]*(1-weight)+colors[idx+1]*weight
        nx,ny = xx/max(1,self.width-1), yy/max(1,self.height-1)
        for cx,cy,sx,sy,color,strength in [(.13,.43,.3,.55,(22,105,255),.18),(.88,.55,.3,.52,(31,188,105),.13),(.5,.04,.48,.36,(126,174,229),.055)]:
            glow = np.exp(-2.2*(((nx-cx)/sx)**2+((ny-cy)/sy)**2))*strength
            array = array*(1-glow[...,None])+np.array(color,dtype=np.float32)*glow[...,None]
        edge = np.clip(((nx-.5)/.62)**2+((ny-.46)/.7)**2,0,1)
        array *= (1-.34*edge)[...,None]
        image = Image.fromarray(array.astype('uint8'))
        shadow = Image.new('RGBA', image.size)
        ImageDraw.Draw(shadow).rounded_rectangle((m['x']*s,(m['y']+18)*s,(m['x']+m['windowWidth'])*s,(m['y']+m['windowHeight']+18)*s),radius=12*s,fill=(0,0,0,185))
        shadow = shadow.filter(ImageFilter.GaussianBlur(28*s))
        image.paste(shadow,(0,0),shadow)
        return image

    def frame_key(self,time):
        return terminal_state(self.model,time)

    def row_image(self, key):
        # Bounded, instance-owned cache; frames are rendered concurrently.
        with self._row_lock:
            if key in self._rows:
                self._rows.move_to_end(key)
                return self._rows[key]
        image = self._render_row(key)
        with self._row_lock:
            self._rows[key] = image
            if len(self._rows) > 128:
                self._rows.popitem(last=False)
        return image

    def _render_row(self, key):
        m,s = self.model,self.scale
        image = Image.new('RGB',(round((m['windowWidth']-2*m['inset'])*s),round(m['rowHeight']*s)),BODY_COLOR)
        draw = ImageDraw.Draw(image)
        x = 0
        for pairs in key:
            item = dict(pairs)
            flags = int(item.get('italic',False))+2*int(item.get('bold',False))
            width = len(item['text'])*m['cellWidth']*s
            if item.get('background'):
                draw.rectangle((x,0,x+width,image.height),fill=item['background'])
            for index,char in enumerate(item['text']):
                draw.text((x+index*m['cellWidth']*s,(m['fontSize']+2)*s),char,
                          font=self.fonts[flags],fill=item['color'],anchor='ls')
            if item.get('underline'):
                draw.line((x,(m['fontSize']+4)*s,x+width,(m['fontSize']+4)*s),
                          fill=item['color'],width=max(1,round(s)))
            x += width
        return image

    def frame(self,time):
        m,s = self.model,self.scale
        state = self.frame_key(time)
        rows = terminal_rows(m,state)
        window = self.window.copy()
        for row_index,row in enumerate(rows):
            y = (m['chrome']+m['inset']+row_index*m['rowHeight'])*s
            key = tuple(tuple(sorted(item.items())) for item in row)
            window.paste(self.row_image(key),(round(m['inset']*s),round(y)))
        if state[3]:
            x = (m['inset']+sum(len(item['text']) for item in rows[-1])*m['cellWidth'])*s
            ImageDraw.Draw(window).rectangle((x,y,x+m['cellWidth']*s-1,y+(m['fontSize']+4)*s),fill='#c4c4cd')
        image = self.base.copy()
        image.paste(window,(round(m['x']*s),round(m['y']*s)),self.mask)
        return image


def build_terminal_mp4(options: TerminalOptions) -> bytes:
    if build_terminal_model(options)['duration']>180000:
        raise ExportLimitError('Terminal MP4 exports support up to 3 minutes. Increase typing speed or shorten the command.')
    renderer = TerminalFrameRenderer(options,mp4_render_scale(options))
    return encode_mp4(renderer,'terminal-mp4-',VIDEO_FPS)


def build_terminal_gif(options: TerminalOptions) -> bytes:
    if build_terminal_model(options)['duration']>45000:
        raise ExportLimitError('Terminal GIF exports support up to 45 seconds. Use MP4 for longer animations.')
    renderer = TerminalFrameRenderer(options,min(1,700/max(options.width,options.height)))
    frames, durations = [], []
    last_key = None
    # A shared palette keeps the backdrop and text colors stable between frames.
    palette = renderer.frame(renderer.duration).quantize(colors=256)
    for time in range(0,math.ceil(renderer.duration),50):
        key = renderer.frame_key(time)
        if key == last_key:
            durations[-1] += 50
        else:
            frames.append(renderer.frame(time).quantize(palette=palette,dither=Image.Dither.NONE))
            durations.append(50)
            last_key = key
    output = BytesIO()
    kwargs = {'loop':0} if options.loop else {}
    frames[0].save(output,format='GIF',save_all=True,append_images=frames[1:],duration=durations,disposal=1,optimize=False,**kwargs)
    return output.getvalue()
