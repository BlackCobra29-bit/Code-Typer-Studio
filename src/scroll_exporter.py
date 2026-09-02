"""60 fps MP4 and palette-stable GIF exports for Code Scroll."""
from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .gif_exporter import ExportLimitError, VIDEO_FPS, _blend, _ease, _font, _rgb, _smoothstep
from .gradients import gradient_stops
from .scroll_renderer import ScrollOptions, _canvas_padding, build_scroll_model


class ScrollFrameRenderer:
    def __init__(self, code: str, options: ScrollOptions):
        self.options = o = options
        self.model = build_scroll_model(code, o)
        self.highlight = self.model["highlight"]
        self.timeline = self.model["timeline"]
        self.duration = self.timeline["duration"]
        self.theme = self.model["theme"]
        self.bg = _rgb(self.highlight["background"])
        self.fg = _rgb(self.highlight["foreground"])
        self.accent = _rgb(self.theme["accent"], self.fg)
        self.focus_color = _rgb(self.model["focusColor"], self.bg)
        self.width, self.height = o.width, o.height
        self.padding_y = _canvas_padding(o) if o.background_style == "gradient" else 0
        self.padding_x = self.padding_y * 2
        self.ew, self.eh = self.width-self.padding_x*2, self.height-self.padding_y*2
        self.chrome = 44 if o.show_window_chrome else 0
        self.vw, self.vh = self.ew-2, self.eh-self.chrome-2
        self.size, self.row_h = o.font_size, o.font_size*o.line_height
        self.content_x = (54 if o.show_line_numbers else 18) + 16
        self.fonts = [_font(o.font_family, o.font_size, flag) for flag in range(4)]
        self.number_font = _font(o.font_family, o.font_size*.82)
        self.badge_font = _font("JetBrains Mono", 8)
        lines = self.highlight["lines"] or [[]]
        self.strips = [self._line_strip(tokens) for tokens in lines]
        self.target_start = self.model["targetStart"]-1
        self.target_end = self.model["targetEnd"]-1
        target_height = (self.target_end-self.target_start+1)*self.row_h
        target_center = 30+self.target_start*self.row_h+target_height/2
        total_height = 30+len(self.strips)*self.row_h+44
        self.target_scroll = max(0, min(max(0, total_height-self.vh), target_center-self.vh/2))
        self.highlight_width = max(self.strips[index].width for index in range(self.target_start, self.target_end+1))+18
        self.base = self._background()

    def _line_strip(self, tokens):
        parts=[];width=0.0
        for token in tokens:
            font=self.fonts[token["fontStyle"]&3]
            for char in token["content"]:
                advance=float(font.getlength(char)) if char!="\t" else float(font.getlength(" "))*2-width%(float(font.getlength(" "))*2)
                parts.append((char,width,advance,token,font));width+=advance
        strip=Image.new("RGBA",(max(1,math.ceil(width)+6),math.ceil(self.row_h)),(0,0,0,0));draw=ImageDraw.Draw(strip)
        for char,x,advance,token,font in parts:
            ascent,descent=font.getmetrics();baseline=(self.row_h-ascent-descent)/2+ascent
            if char!="\t":draw.text((x,baseline),char,font=font,fill=token["color"],anchor="ls")
            if token["fontStyle"]&4:draw.line((x,baseline+2,x+advance,baseline+2),fill=token["color"])
        return strip

    def _background(self):
        if not self.padding_y:return Image.new("RGB",(self.width,self.height),self.bg)
        colors=np.array([_rgb(color) for color in gradient_stops(self.options.gradient_name)],dtype=float)
        yy,xx=np.mgrid[0:self.height,0:self.width];position=(xx+yy)/max(1,self.width+self.height-2)*(len(colors)-1)
        index=np.minimum(len(colors)-2,position.astype(int));weight=(position-index)[...,None]
        array=colors[index]*(1-weight)+colors[index+1]*weight;nx=xx/max(1,self.width-1);ny=yy/max(1,self.height-1)
        for cx,cy,sx,sy,color,strength in [(.13,.43,.30,.55,np.array((22,105,255)),.18),(.88,.55,.30,.52,np.array((31,188,105)),.13),(.50,.04,.48,.36,np.array((126,174,229)),.055)]:
            glow=np.exp(-2.2*(((nx-cx)/sx)**2+((ny-cy)/sy)**2))*strength;array=array*(1-glow[...,None])+color*glow[...,None]
        edge=np.clip(((nx-.5)/.62)**2+((ny-.46)/.70)**2,0,1);array*=(1-.34*edge)[...,None]
        image=Image.fromarray(array.astype("uint8"))
        for offset,blur,alpha in [(22,44,150),(10,18,126),(3,6,72)]:
            shadow=Image.new("RGBA",image.size);draw=ImageDraw.Draw(shadow)
            draw.rounded_rectangle((self.padding_x,self.padding_y+offset,self.width-self.padding_x,self.height-self.padding_y+offset),radius=self.options.radius,fill=(0,0,0,alpha))
            shadow=shadow.filter(ImageFilter.GaussianBlur(blur));image.paste(shadow,(0,0),shadow)
        return image

    def _state(self,time):
        t=self.timeline
        scroll=_smoothstep((time-t["scrollStart"])/max(1,t["scrollEnd"]-t["scrollStart"]))
        focus=_ease((time-t["focusStart"])/max(1,t["focusEnd"]-t["focusStart"]))
        return scroll,focus

    def frame(self,time:float)->Image.Image:
        o=self.options;t=self.timeline;scroll,focus=self._state(time)
        editor=Image.new("RGB",(self.ew,self.eh),self.bg);surface=Image.new("RGB",(self.vw,self.vh),self.bg);draw=ImageDraw.Draw(surface)
        scroll_y=self.target_scroll*scroll
        box_y=30+self.target_start*self.row_h-scroll_y-1
        box_h=(self.target_end-self.target_start+1)*self.row_h+2
        if focus>0:
            fill=_blend(self.bg,self.focus_color,focus);outline=_blend(self.bg,self.accent,focus)
            x1=self.content_x-8;x2=min(self.vw-18,x1+self.highlight_width)
            draw.rounded_rectangle((x1,box_y,x2,box_y+box_h),radius=6,fill=fill)
            draw.rounded_rectangle((x1,box_y,x1+3,box_y+box_h),radius=2,fill=outline)
        for line_no,strip in enumerate(self.strips):
            row_y=30+line_no*self.row_h-scroll_y
            if row_y+self.row_h<0 or row_y>=self.vh:continue
            target=self.target_start<=line_no<=self.target_end;opacity=1 if target else 1-focus*.65
            if o.show_line_numbers:
                ascent,descent=self.number_font.getmetrics();baseline=row_y+(self.row_h-ascent-descent)/2+ascent
                color=_blend(self.bg,_rgb(self.theme["muted"],self.bg),.48*opacity)
                draw.text((self.content_x-26,baseline),str(line_no+1),font=self.number_font,fill=color,anchor="rs")
            shown=strip.copy();alpha=np.asarray(shown.getchannel("A")).copy();shown.putalpha(Image.fromarray((alpha*opacity).astype("uint8")))
            surface.paste(shown,(self.content_x,round(row_y)),shown)
        editor.paste(surface,(1,self.chrome+1));draw=ImageDraw.Draw(editor)
        if self.chrome:
            chrome=_rgb(self.theme["chrome_bg"],self.bg);top=_blend(chrome,self.fg,.10)
            for cy in range(self.chrome):draw.line((0,cy,self.ew,cy),fill=_blend(top,chrome,cy/max(1,self.chrome-1)))
            for index,color in enumerate(("#ff5f57","#febc2e","#28c840")):draw.ellipse((20+index*17,18,29+index*17,27),fill=color,outline=(25,25,25))
            if time<t["scrollEnd"]:label="SCANNING"
            elif self.target_start==self.target_end:label=f"LINE {self.target_start+1}"
            else:label=f"LINES {self.target_start+1}-{self.target_end+1}"
            badge_w=self.badge_font.getlength(label)+16;bx=self.ew-badge_w-14
            draw.rounded_rectangle((bx,14,self.ew-14,30),radius=8,fill=_blend(chrome,self.fg,.04),outline=_blend(chrome,self.fg,.12))
            draw.text(((bx+self.ew-14)/2,22),label,font=self.badge_font,fill=_blend(self.bg,self.fg,.68),anchor="mm")
            draw.line((0,self.chrome,self.ew,self.chrome),fill=_blend(self.bg,self.fg,.10))
        draw.rounded_rectangle((0,0,self.ew-1,self.eh-1),radius=o.radius,outline=_blend(self.bg,self.fg,.17));draw.rounded_rectangle((1,1,self.ew-2,self.eh-2),radius=max(0,o.radius-1),outline=_blend(self.bg,self.fg,.035))
        mask=Image.new("L",editor.size);ImageDraw.Draw(mask).rounded_rectangle((0,0,self.ew-1,self.eh-1),radius=o.radius,fill=255)
        entrance=_smoothstep(time/max(1,min(650,t["startDelay"])))
        if entrance<1:
            scale=.992+entrance*.008;size=(max(1,round(self.ew*scale)),max(1,round(self.eh*scale)))
            editor=editor.resize(size,Image.Resampling.LANCZOS);mask=mask.resize(size,Image.Resampling.LANCZOS);mask=mask.point(lambda value:round(value*(.76+.24*entrance)))
        result=self.base.copy();px=self.padding_x+round((self.ew-editor.width)/2);py=self.padding_y+round((self.eh-editor.height)/2)+round((1-entrance)*14)
        result.paste(editor,(px,py),mask);return result


def build_scroll_mp4(code:str,options:ScrollOptions,fps:int=VIDEO_FPS)->bytes:
    renderer=ScrollFrameRenderer(code,options)
    if renderer.duration>180000:raise ExportLimitError("MP4 is limited to 3 minutes.")
    with TemporaryDirectory(prefix="code-scroll-") as directory:
        path=Path(directory)/"code-scroll.mp4"
        with imageio.get_writer(str(path),fps=fps,codec="libx264",quality=8,macro_block_size=1,pixelformat="yuv420p") as writer:
            for frame_no in range(math.ceil(renderer.duration*fps/1000)):writer.append_data(np.asarray(renderer.frame(frame_no*1000/fps)))
        return path.read_bytes()


def build_scroll_gif(code:str,options:ScrollOptions)->bytes:
    renderer=ScrollFrameRenderer(code,options)
    if renderer.duration>45000:raise ExportLimitError("GIF is limited to 45 seconds.")
    scale=min(1,700/renderer.width,700/renderer.height);size=(round(renderer.width*scale),round(renderer.height*scale))
    palette=renderer.frame(renderer.duration).resize(size,Image.Resampling.LANCZOS).quantize(colors=256)
    frames=[renderer.frame(time).resize(size,Image.Resampling.LANCZOS).quantize(palette=palette,dither=Image.Dither.NONE) for time in range(0,math.ceil(renderer.duration),50)]
    output=BytesIO();loop={"loop":0} if options.loop else {}
    frames[0].save(output,format="GIF",save_all=True,append_images=frames[1:],duration=50,disposal=2,optimize=False,**loop);return output.getvalue()
