"""60 fps MP4 and palette-stable GIF exports for Code Scroll."""
from __future__ import annotations

import math
from io import BytesIO
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .gif_exporter import EditorFrame, ExportLimitError, VIDEO_FPS, _blend, _ease, _font, _rgb, _smoothstep
from .gradients import gradient_stops
from .scroll_renderer import ScrollOptions, _canvas_padding, build_scroll_model


class ScrollFrameRenderer:
    def __init__(self, code: str, options: ScrollOptions, render_scale: float = 1):
        self.options = o = options
        self.render_scale = s = render_scale
        self.border = max(1, round(s))
        self.radius = o.radius*s
        self.model = build_scroll_model(code, o)
        self.highlight = self.model["highlight"]
        self.timeline = self.model["timeline"]
        self.duration = self.timeline["duration"]
        self.theme = self.model["theme"]
        self.bg = _rgb(self.highlight["background"])
        self.fg = _rgb(self.highlight["foreground"])
        self.accent = _rgb(self.theme["accent"], self.fg)
        self.focus_color = _rgb(self.model["focusColor"], self.bg)
        self.width, self.height = round(o.width*s), round(o.height*s)
        self.padding_y = round(_canvas_padding(o)*s) if o.background_style == "gradient" else 0
        self.padding_x = self.padding_y * 2
        self.ew, self.eh = self.width-self.padding_x*2, self.height-self.padding_y*2
        self.chrome = round(44*s) if o.show_window_chrome else 0
        self.vw, self.vh = self.ew-2*self.border, self.eh-self.chrome-2*self.border
        self.size, self.row_h = o.font_size*s, o.font_size*s*o.line_height
        self.content_x = round(((54 if o.show_line_numbers else 18) + 16)*s)
        self.fonts = [_font(o.font_family, self.size, flag) for flag in range(4)]
        self.number_font = _font(o.font_family, self.size*.82)
        lines = self.highlight["lines"] or [[]]
        self.strips = [self._line_strip(tokens) for tokens in lines]
        self.target_start = self.model["targetStart"]-1
        self.target_end = self.model["targetEnd"]-1
        target_height = (self.target_end-self.target_start+1)*self.row_h
        target_center = 30*s+self.target_start*self.row_h+target_height/2
        total_height = 30*s+len(self.strips)*self.row_h+44*s
        self.target_scroll = max(0, min(max(0, total_height-self.vh), target_center-self.vh/2))
        if not o.highlight_lines:
            self.target_scroll = max(0, total_height-self.vh)
        self.highlight_width = max(self.strips[index].width for index in range(self.target_start, self.target_end+1))+18*s
        self.base = self._background()
        self.focus_label = (f"LINE {self.target_start+1}" if self.target_start==self.target_end
                            else f"LINES {self.target_start+1}-{self.target_end+1}")
        if not o.highlight_lines:
            self.focus_label = "END OF FILE"
        self.travel_label = "SCANNING" if o.highlight_lines else "SCROLLING"
        self.editor_frame = EditorFrame(self,(self.travel_label,self.focus_label))

    def _line_strip(self, tokens):
        s = self.render_scale
        parts=[];width=0.0
        for token in tokens:
            font=self.fonts[token["fontStyle"]&3]
            for char in token["content"]:
                advance=float(font.getlength(char)) if char!="\t" else float(font.getlength(" "))*2-width%(float(font.getlength(" "))*2)
                parts.append((char,width,advance,token,font));width+=advance
        strip=Image.new("RGBA",(max(1,math.ceil(width)+round(6*s)),math.ceil(self.row_h)),(0,0,0,0));draw=ImageDraw.Draw(strip)
        for char,x,advance,token,font in parts:
            ascent,descent=font.getmetrics();baseline=(self.row_h-ascent-descent)/2+ascent
            if char!="\t":draw.text((x,baseline),char,font=font,fill=token["color"],anchor="ls")
            if token["fontStyle"]&4:draw.line((x,baseline+2*s,x+advance,baseline+2*s),fill=token["color"],width=self.border)
        return strip

    def _background(self):
        s = self.render_scale
        if not self.padding_y:return Image.new("RGB",(self.width,self.height),self.bg)
        colors=np.array([_rgb(color) for color in gradient_stops(self.options.gradient_name)],dtype=np.float32)
        yy=np.arange(self.height,dtype=np.float32)[:,None];xx=np.arange(self.width,dtype=np.float32)[None,:];position=(xx+yy)/max(1,self.width+self.height-2)*(len(colors)-1)
        index=np.minimum(len(colors)-2,position.astype(np.int32));weight=(position-index.astype(np.float32))[...,None]
        array=colors[index]*(1-weight)+colors[index+1]*weight;nx=xx/max(1,self.width-1);ny=yy/max(1,self.height-1)
        for cx,cy,sx,sy,color,strength in [(.13,.43,.30,.55,np.array((22,105,255),dtype=np.float32),.18),(.88,.55,.30,.52,np.array((31,188,105),dtype=np.float32),.13),(.50,.04,.48,.36,np.array((126,174,229),dtype=np.float32),.055)]:
            glow=np.exp(-2.2*(((nx-cx)/sx)**2+((ny-cy)/sy)**2))*strength;array=array*(1-glow[...,None])+color*glow[...,None]
        edge=np.clip(((nx-.5)/.62)**2+((ny-.46)/.70)**2,0,1);array*=(1-.34*edge)[...,None]
        image=Image.fromarray(array.astype("uint8"))
        for offset,blur,alpha in [(22,44,150),(10,18,126),(3,6,72)]:
            shadow=Image.new("RGBA",image.size);draw=ImageDraw.Draw(shadow)
            draw.rounded_rectangle((self.padding_x,self.padding_y+round(offset*s),self.width-self.padding_x,self.height-self.padding_y+round(offset*s)),radius=self.radius,fill=(0,0,0,alpha))
            shadow=shadow.filter(ImageFilter.GaussianBlur(blur*s));image.paste(shadow,(0,0),shadow)
        return image

    def _state(self,time):
        t=self.timeline
        scroll=_smoothstep((time-t["scrollStart"])/max(1,t["scrollEnd"]-t["scrollStart"]))
        focus=_ease((time-t["focusStart"])/max(1,t["focusEnd"]-t["focusStart"]))
        if not self.options.highlight_lines:
            focus = 0
        return scroll,focus

    def frame(self,time:float)->Image.Image:
        s = self.render_scale
        o=self.options;t=self.timeline;scroll,focus=self._state(time)
        surface=Image.new("RGB",(self.vw,self.vh),self.bg);draw=ImageDraw.Draw(surface)
        scroll_y=self.target_scroll*scroll
        box_y=30*s+self.target_start*self.row_h-scroll_y-s
        box_h=(self.target_end-self.target_start+1)*self.row_h+2*s
        if focus>0:
            fill=_blend(self.bg,self.focus_color,focus);outline=_blend(self.bg,self.accent,focus)
            x1=self.content_x-8*s;x2=min(self.vw-18*s,x1+self.highlight_width)
            draw.rounded_rectangle((x1,box_y,x2,box_y+box_h),radius=6*s,fill=fill)
            draw.rounded_rectangle((x1,box_y,x1+3*s,box_y+box_h),radius=2*s,fill=outline)
        for line_no,strip in enumerate(self.strips):
            row_y=30*s+line_no*self.row_h-scroll_y
            if row_y+self.row_h<0 or row_y>=self.vh:continue
            target=self.target_start<=line_no<=self.target_end;opacity=1 if target else 1-focus*.65
            if o.show_line_numbers:
                ascent,descent=self.number_font.getmetrics();baseline=row_y+(self.row_h-ascent-descent)/2+ascent
                color=_blend(self.bg,_rgb(self.theme["muted"],self.bg),.48*opacity)
                draw.text((self.content_x-26*s,baseline),str(line_no+1),font=self.number_font,fill=color,anchor="rs")
            if opacity == 1:
                surface.paste(strip,(self.content_x,round(row_y)),strip)
            else:
                shown=strip.copy();alpha=np.asarray(shown.getchannel("A")).copy();shown.putalpha(Image.fromarray((alpha*opacity).astype("uint8")))
                surface.paste(shown,(self.content_x,round(row_y)),shown)
        label = self.travel_label if time<t["scrollEnd"] else self.focus_label
        return self.editor_frame.compose(surface,time,t["startDelay"],label)

    def frame_key(self, time):
        t = self.timeline
        if time >= max(t['scrollEnd'],t['focusEnd'],min(650,t['startDelay'])):
            return 'final'
        if min(650,t['startDelay']) <= time < t['scrollStart']:
            return 'opening-hold'
        return time



def build_scroll_mp4(code:str,options:ScrollOptions,fps:int=VIDEO_FPS)->bytes:
    from .video_export import encode_mp4, mp4_render_scale
    renderer=ScrollFrameRenderer(code,options,render_scale=mp4_render_scale(options))
    if renderer.duration>180000:raise ExportLimitError("MP4 is limited to 3 minutes.")
    return encode_mp4(renderer,"code-scroll-",fps)


def build_scroll_gif(code:str,options:ScrollOptions)->bytes:
    renderer=ScrollFrameRenderer(code,options)
    if renderer.duration>45000:raise ExportLimitError("GIF is limited to 45 seconds.")
    scale=min(1,700/renderer.width,700/renderer.height);size=(round(renderer.width*scale),round(renderer.height*scale))
    palette=renderer.frame(renderer.duration).resize(size,Image.Resampling.LANCZOS).quantize(colors=256)
    frames=[renderer.frame(time).resize(size,Image.Resampling.LANCZOS).quantize(palette=palette,dither=Image.Dither.NONE) for time in range(0,math.ceil(renderer.duration),50)]
    output=BytesIO();loop={"loop":0} if options.loop else {}
    frames[0].save(output,format="GIF",save_all=True,append_images=frames[1:],duration=50,disposal=2,optimize=False,**loop);return output.getvalue()
