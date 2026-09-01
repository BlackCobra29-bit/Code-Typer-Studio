"""60 fps MP4 and palette-stable GIF exports for Code Diff."""
from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .diff_renderer import DiffOptions, build_diff_model, _canvas_padding
from .gif_exporter import ExportLimitError, VIDEO_FPS, _blend, _ease, _font, _rgb, _smoothstep
from .gradients import gradient_stops


class DiffFrameRenderer:
    def __init__(self, original: str, revised: str, options: DiffOptions):
        self.options = o = options
        self.model = build_diff_model(original, revised, o)
        self.rows = self.model["rows"]
        self.timeline = self.model["timeline"]
        self.duration = self.timeline["duration"]
        self.theme = self.model["theme"]
        self.bg = _rgb(self.model["highlight"]["background"])
        self.fg = _rgb(self.model["highlight"]["foreground"])
        self.width, self.height = o.width, o.height
        self.padding_y = _canvas_padding(o) if o.background_style == "gradient" and not o.flush_frame else 0
        self.padding_x = self.padding_y*2
        self.ew, self.eh = self.width-self.padding_x*2, self.height-self.padding_y*2
        self.chrome = 44 if o.show_window_chrome else 0
        self.vw, self.vh = self.ew-2, self.eh-self.chrome-2
        self.size, self.row_h = o.font_size, o.font_size*o.line_height
        self.content_x = 72 if o.show_line_numbers else 30
        self.fonts = [_font(o.font_family,o.font_size,flag) for flag in range(4)]
        self.number_font = _font(o.font_family,o.font_size*.78)
        self.badge_font = _font("JetBrains Mono",8)
        self.strips = [self._line_strip(row["tokens"]) for row in self.rows]
        self.first_changed = next((i for i,row in enumerate(self.rows) if row["kind"] != "equal"),0)
        self.base = self._background()

    def _line_strip(self, tokens):
        parts=[]; width=0.0
        for token in tokens:
            font=self.fonts[token["fontStyle"]&3]
            for char in token["content"]:
                advance=float(font.getlength(char)) if char!="\t" else float(font.getlength(" "))*2-width%(float(font.getlength(" "))*2)
                parts.append((char,width,advance,token,font));width+=advance
        strip=Image.new("RGBA",(max(1,math.ceil(width)+8),math.ceil(self.row_h)),(0,0,0,0));draw=ImageDraw.Draw(strip)
        for char,x,advance,token,font in parts:
            ascent,descent=font.getmetrics();baseline=(self.row_h-ascent-descent)/2+ascent
            if char!="\t":draw.text((x,baseline),char,font=font,fill=token["color"],anchor="ls")
            if token["fontStyle"]&4:draw.line((x,baseline+2,x+advance,baseline+2),fill=token["color"])
        return strip

    def _background(self):
        if not self.padding_y:return Image.new("RGB",(self.width,self.height),self.bg)
        colors=np.array([_rgb(c) for c in gradient_stops(self.options.gradient_name)],dtype=float)
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

    def _progress(self,time,start,duration):
        return _ease((time-start)/max(1,duration))

    def _states(self,time):
        t=self.timeline;resolve=self._progress(time,t["resolveStart"],t["resolveEnd"]-t["resolveStart"]);states=[]
        for row in self.rows:
            intro=0 if row["originalOrder"]<0 else self._progress(time,t["startDelay"]+row["originalOrder"]*t["lineStagger"],260)
            at=t["changeStart"]+max(0,row["changeOrder"])*72
            deletion=self._progress(time,at,t["transition"]*.72) if row["kind"]=="delete" else 0
            insertion=self._progress(time,t["insertStart"]+max(0,row["changeOrder"])*72,t["transition"]*.78) if row["kind"]=="insert" else 0
            height=self.row_h;opacity=intro;translate=(1-intro)*4
            if row["kind"]=="delete":height*=1-resolve;opacity*=1-resolve*.96;translate=-resolve*5
            elif row["kind"]=="insert":height*=insertion;opacity=insertion;translate=(1-insertion)*-5
            strength=deletion*(1-resolve) if row["kind"]=="delete" else insertion*(1-resolve*.90) if row["kind"]=="insert" else 0
            states.append((height,opacity,translate,deletion,insertion,strength))
        return states,resolve

    def frame(self,time:float)->Image.Image:
        o=self.options;t=self.timeline;states,resolve=self._states(time)
        editor=Image.new("RGB",(self.ew,self.eh),self.bg);surface=Image.new("RGB",(self.vw,self.vh),self.bg)
        total=sum(state[0] for state in states)+74;focus=_smoothstep((time-t["changeStart"])/520)
        pre_y=30+self.first_changed*self.row_h
        target=max(0,min(max(0,total-self.vh),pre_y-self.vh*.42));scroll=target*focus
        y=30-scroll
        for index,(row,state,strip) in enumerate(zip(self.rows,states,self.strips)):
            height,opacity,translate,deletion,insertion,strength=state;visible_h=max(0,math.ceil(height))
            if visible_h<=0:y+=height;continue
            row_image=Image.new("RGBA",(self.vw,max(1,math.ceil(self.row_h))),(0,0,0,0));draw=ImageDraw.Draw(row_image)
            if row["kind"]=="delete" and strength:draw.rectangle((0,0,self.vw,self.row_h),fill=(248,81,73,round(46*strength)))
            if row["kind"]=="insert" and strength:draw.rectangle((0,0,self.vw,self.row_h),fill=(46,160,67,round(46*strength)))
            if strength:
                color=(248,81,73,round(255*strength)) if row["kind"]=="delete" else (46,160,67,round(255*strength))
                draw.rectangle((0,0,3,self.row_h),fill=color);draw.text((17,self.row_h/2),"−" if row["kind"]=="delete" else "+",font=self.number_font,fill=color,anchor="mm")
            number=row["newNumber"] if row["kind"]=="insert" and insertion>0 else row["oldNumber"] if resolve<.5 else row["newNumber"]
            if o.show_line_numbers and number:
                draw.text((64,self.row_h/2),str(number),font=self.number_font,fill=(*_rgb(self.theme["muted"],self.bg),round(122*opacity)),anchor="rm")
            token_alpha=opacity*(1-deletion*.20 if row["kind"]=="delete" else 1)
            shown=strip.copy();alpha=np.asarray(shown.getchannel("A")).copy();shown.putalpha(Image.fromarray((alpha*token_alpha).astype("uint8")))
            row_image.paste(shown,(self.content_x,0),shown)
            if row["kind"]=="delete" and deletion>0:
                strike_end=self.content_x+strip.width*deletion
                draw.line((self.content_x,self.row_h/2,strike_end,self.row_h/2),fill=(255,123,114,round(255*deletion*(1-resolve))),width=2)
            crop=row_image.crop((0,0,self.vw,min(row_image.height,visible_h)))
            py=round(y+translate)
            if py<self.vh and py+crop.height>0:surface.paste(crop,(0,py),crop)
            y+=height
        editor.paste(surface,(1,self.chrome+1));draw=ImageDraw.Draw(editor)
        if self.chrome:
            chrome=_rgb(self.theme["chrome_bg"],self.bg);top=_blend(chrome,self.fg,.10)
            for cy in range(self.chrome):draw.line((0,cy,self.ew,cy),fill=_blend(top,chrome,cy/max(1,self.chrome-1)))
            for i,color in enumerate(("#ff5f57","#febc2e","#28c840")):draw.ellipse((20+i*17,18,29+i*17,27),fill=color,outline=(25,25,25))
            label="ORIGINAL" if time<t["changeStart"] else "CHANGES DETECTED" if time<t["resolveEnd"] else "UPDATED"
            badge_w=self.badge_font.getlength(label)+16;bx=self.ew-badge_w-14
            draw.rounded_rectangle((bx,14,self.ew-14,30),radius=8,fill=_blend(chrome,self.fg,.04),outline=_blend(chrome,self.fg,.12))
            draw.text(((bx+self.ew-14)/2,22),label,font=self.badge_font,fill=_blend(self.bg,self.fg,.68),anchor="mm")
            draw.line((0,self.chrome,self.ew,self.chrome),fill=_blend(self.bg,self.fg,.10))
        draw.rounded_rectangle((0,0,self.ew-1,self.eh-1),radius=o.radius,outline=_blend(self.bg,self.fg,.17));draw.rounded_rectangle((1,1,self.ew-2,self.eh-2),radius=max(0,o.radius-1),outline=_blend(self.bg,self.fg,.035))
        mask=Image.new("L",editor.size);ImageDraw.Draw(mask).rounded_rectangle((0,0,self.ew-1,self.eh-1),radius=o.radius,fill=255)
        entrance=_smoothstep(time/max(1,min(650,t["startDelay"])))
        if entrance<1:
            scale=.992+entrance*.008;size=(max(1,round(self.ew*scale)),max(1,round(self.eh*scale)))
            editor=editor.resize(size,Image.Resampling.LANCZOS);mask=mask.resize(size,Image.Resampling.LANCZOS);mask=mask.point(lambda v:round(v*(.76+.24*entrance)))
        result=self.base.copy();px=self.padding_x+round((self.ew-editor.width)/2);py=self.padding_y+round((self.eh-editor.height)/2)+round((1-entrance)*14)
        result.paste(editor,(px,py),mask);return result


def build_diff_mp4(original:str,revised:str,options:DiffOptions,fps:int=VIDEO_FPS)->bytes:
    renderer=DiffFrameRenderer(original,revised,options)
    if renderer.duration>180000:raise ExportLimitError("MP4 is limited to 3 minutes.")
    with TemporaryDirectory(prefix="code-diff-") as directory:
        path=Path(directory)/"code-diff.mp4"
        with imageio.get_writer(str(path),fps=fps,codec="libx264",quality=8,macro_block_size=1,pixelformat="yuv420p") as writer:
            for frame_no in range(math.ceil(renderer.duration*fps/1000)):writer.append_data(np.asarray(renderer.frame(frame_no*1000/fps)))
        return path.read_bytes()


def build_diff_gif(original:str,revised:str,options:DiffOptions)->bytes:
    renderer=DiffFrameRenderer(original,revised,options)
    if renderer.duration>45000:raise ExportLimitError("GIF is limited to 45 seconds.")
    scale=min(1,700/renderer.width,700/renderer.height);size=(round(renderer.width*scale),round(renderer.height*scale))
    palette=renderer.frame(renderer.duration).resize(size,Image.Resampling.LANCZOS).quantize(colors=256)
    frames=[renderer.frame(time).resize(size,Image.Resampling.LANCZOS).quantize(palette=palette,dither=Image.Dither.NONE) for time in range(0,math.ceil(renderer.duration),50)]
    output=BytesIO();loop={"loop":0} if options.loop else {}
    frames[0].save(output,format="GIF",save_all=True,append_images=frames[1:],duration=50,disposal=2,optimize=False,**loop);return output.getvalue()
