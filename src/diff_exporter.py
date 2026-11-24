"""60 fps MP4 and palette-stable GIF exports for Code Diff."""
from __future__ import annotations

import math
from io import BytesIO
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .diff_renderer import DiffOptions, build_diff_model, _canvas_padding
from .gif_exporter import EditorFrame, ExportLimitError, VIDEO_FPS, _blend, _ease, _font, _rgb, _smoothstep
from .gradients import gradient_stops


class DiffFrameRenderer:
    def __init__(self, original: str, revised: str, options: DiffOptions, render_scale: float = 1):
        self.options = o = options
        self.render_scale = s = render_scale
        self.border = max(1, round(s))
        self.radius = o.radius*s
        self.model = build_diff_model(original, revised, o)
        self.rows = self.model["rows"]
        self.timeline = self.model["timeline"]
        self.duration = self.timeline["duration"]
        self.theme = self.model["theme"]
        self.bg = _rgb(self.model["highlight"]["background"])
        self.fg = _rgb(self.model["highlight"]["foreground"])
        self.width, self.height = round(o.width*s), round(o.height*s)
        self.padding_y = round(_canvas_padding(o)*s) if o.background_style == "gradient" and not o.flush_frame else 0
        self.padding_x = self.padding_y*2
        self.ew, self.eh = self.width-self.padding_x*2, self.height-self.padding_y*2
        self.chrome = round(44*s) if o.show_window_chrome else 0
        self.vw, self.vh = self.ew-2*self.border, self.eh-self.chrome-2*self.border
        self.size, self.row_h = o.font_size*s, o.font_size*s*o.line_height
        self.content_x = round(((54 if o.show_line_numbers else 18) + 16)*s)
        self.fonts = [_font(o.font_family,self.size,flag) for flag in range(4)]
        self.number_font = _font(o.font_family,self.size*.82)
        self.strips = [self._line_strip(row["tokens"]) for row in self.rows]
        self.first_changed = next((i for i,row in enumerate(self.rows) if row["kind"] != "equal"),0)
        self.base = self._background()
        self.editor_frame = EditorFrame(self,("ORIGINAL","CHANGES DETECTED","UPDATED"))
        last_change = max((row["changeOrder"] for row in self.rows),default=0)
        t = self.timeline
        self.motion_end = max(t["resolveEnd"],t["revealEnd"],t["changeStart"]+520,
                              t["changeStart"]+last_change*72+t["transition"]*.72,
                              t["insertStart"]+last_change*72+t["transition"]*.78)

    def _line_strip(self, tokens):
        s = self.render_scale
        parts=[]; width=0.0
        for token in tokens:
            font=self.fonts[token["fontStyle"]&3]
            for char in token["content"]:
                advance=float(font.getlength(char)) if char!="\t" else float(font.getlength(" "))*2-width%(float(font.getlength(" "))*2)
                parts.append((char,width,advance,token,font));width+=advance
        strip=Image.new("RGBA",(max(1,math.ceil(width)+round(8*s)),math.ceil(self.row_h)),(0,0,0,0));draw=ImageDraw.Draw(strip)
        for char,x,advance,token,font in parts:
            ascent,descent=font.getmetrics();baseline=(self.row_h-ascent-descent)/2+ascent
            if char!="\t":draw.text((x,baseline),char,font=font,fill=token["color"],anchor="ls")
            if token["fontStyle"]&4:draw.line((x,baseline+2*s,x+advance,baseline+2*s),fill=token["color"],width=self.border)
        return strip

    def _background(self):
        s = self.render_scale
        if not self.padding_y:return Image.new("RGB",(self.width,self.height),self.bg)
        colors=np.array([_rgb(c) for c in gradient_stops(self.options.gradient_name)],dtype=np.float32)
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

    def _progress(self,time,start,duration):
        return _ease((time-start)/max(1,duration))

    def _states(self,time):
        t=self.timeline;resolve=self._progress(time,t["resolveStart"],t["resolveEnd"]-t["resolveStart"]);states=[]
        for row in self.rows:
            intro=0 if row["originalOrder"]<0 else self._progress(time,t["startDelay"]+row["originalOrder"]*t["lineStagger"],260)
            at=t["changeStart"]+max(0,row["changeOrder"])*72
            deletion=self._progress(time,at,t["transition"]*.72) if row["kind"]=="delete" else 0
            insertion=self._progress(time,t["insertStart"]+max(0,row["changeOrder"])*72,t["transition"]*.78) if row["kind"]=="insert" else 0
            height=self.row_h;opacity=intro;translate=(1-intro)*4*self.render_scale
            if row["kind"]=="delete" and row["silentDelete"]:height*=1-deletion;opacity*=1-deletion;translate=-deletion*3*self.render_scale
            elif row["kind"]=="delete":height*=1-resolve;opacity*=1-resolve*.96;translate=-resolve*5*self.render_scale
            elif row["kind"]=="insert":height*=insertion;opacity=insertion;translate=(1-insertion)*-5*self.render_scale
            strength=0 if row["silentDelete"] else deletion*(1-resolve) if row["kind"]=="delete" else insertion*(1-resolve*.90) if row["kind"]=="insert" else 0
            states.append((height,opacity,translate,deletion,insertion,strength))
        return states,resolve

    def frame(self,time:float)->Image.Image:
        s = self.render_scale
        o=self.options;t=self.timeline;states,resolve=self._states(time)
        surface=Image.new("RGB",(self.vw,self.vh),self.bg)
        total=sum(state[0] for state in states)+74*s;focus=_smoothstep((time-t["changeStart"])/520)
        pre_y=30*s+self.first_changed*self.row_h
        target=max(0,min(max(0,total-self.vh),pre_y-self.vh*.42));scroll=target*focus
        y=30*s-scroll
        for index,(row,state,strip) in enumerate(zip(self.rows,states,self.strips)):
            height,opacity,translate,deletion,insertion,strength=state;visible_h=max(0,math.ceil(height))
            if visible_h<=0:y+=height;continue
            py=round(y+translate)
            if py>=self.vh or py+visible_h<=0:y+=height;continue
            row_image=Image.new("RGBA",(self.vw,max(1,math.ceil(self.row_h))),(0,0,0,0));draw=ImageDraw.Draw(row_image)
            if row["kind"]=="delete" and strength:draw.rectangle((0,0,self.vw,self.row_h),fill=(248,81,73,round(46*strength)))
            if row["kind"]=="insert" and strength:draw.rectangle((0,0,self.vw,self.row_h),fill=(46,160,67,round(46*strength)))
            if strength:
                color=(248,81,73,round(255*strength)) if row["kind"]=="delete" else (46,160,67,round(255*strength))
                draw.rectangle((0,0,3*s,self.row_h),fill=color);draw.text((17*s,self.row_h/2),"−" if row["kind"]=="delete" else "+",font=self.number_font,fill=color,anchor="mm")
            number=row["newNumber"] if row["kind"]=="insert" and insertion>0 else row["oldNumber"] if resolve<.5 else row["newNumber"]
            if o.show_line_numbers and number:
                ascent,descent=self.number_font.getmetrics();baseline=(self.row_h-ascent-descent)/2+ascent
                draw.text((self.content_x-26*s,baseline),str(number),font=self.number_font,fill=(*_rgb(self.theme["muted"],self.bg),round(122*opacity)),anchor="rs")
            token_alpha=opacity*(1-deletion*.20 if row["kind"]=="delete" else 1)
            shown=strip.copy();alpha=np.asarray(shown.getchannel("A")).copy();shown.putalpha(Image.fromarray((alpha*token_alpha).astype("uint8")))
            row_image.alpha_composite(shown,(self.content_x,0))
            if row["kind"]=="delete" and not row["silentDelete"] and deletion>0:
                strike_end=self.content_x+strip.width*deletion
                draw.line((self.content_x,self.row_h/2,strike_end,self.row_h/2),fill=(255,123,114,round(255*deletion*(1-resolve))),width=round(2*s))
            crop=row_image.crop((0,0,self.vw,min(row_image.height,visible_h)))
            if py<self.vh and py+crop.height>0:surface.paste(crop,(0,py),crop)
            y+=height
        label="ORIGINAL" if time<t["changeStart"] else "CHANGES DETECTED" if time<t["resolveEnd"] else "UPDATED"
        return self.editor_frame.compose(surface,time,t["startDelay"],label)

    def frame_key(self, time):
        if time >= self.motion_end:
            return 'final'
        if max(self.timeline['revealEnd'],min(650,self.timeline['startDelay'])) <= time < self.timeline['changeStart']:
            return 'original-hold'
        return time



def build_diff_mp4(original:str,revised:str,options:DiffOptions,fps:int=VIDEO_FPS)->bytes:
    from .video_export import encode_mp4, mp4_render_scale
    renderer=DiffFrameRenderer(original,revised,options,render_scale=mp4_render_scale(options))
    if renderer.duration>180000:raise ExportLimitError("MP4 is limited to 3 minutes.")
    return encode_mp4(renderer,"code-diff-",fps)


def build_diff_gif(original:str,revised:str,options:DiffOptions)->bytes:
    renderer=DiffFrameRenderer(original,revised,options)
    if renderer.duration>45000:raise ExportLimitError("GIF is limited to 45 seconds.")
    scale=min(1,700/renderer.width,700/renderer.height);size=(round(renderer.width*scale),round(renderer.height*scale))
    palette=renderer.frame(renderer.duration).resize(size,Image.Resampling.LANCZOS).quantize(colors=256)
    frames=[renderer.frame(time).resize(size,Image.Resampling.LANCZOS).quantize(palette=palette,dither=Image.Dither.NONE) for time in range(0,math.ceil(renderer.duration),50)]
    output=BytesIO();loop={"loop":0} if options.loop else {}
    frames[0].save(output,format="GIF",save_all=True,append_images=frames[1:],duration=50,disposal=2,optimize=False,**loop);return output.getvalue()
