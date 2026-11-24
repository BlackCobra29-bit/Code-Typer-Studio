"""Terminal regressions: real ANSI, seekable layout, and native HD exports."""
import base64
import json
import math
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import imageio.v2 as imageio
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from main import app, _default_terminal_payload
from src.gif_exporter import ExportLimitError
from src.terminal_renderer import (
    TerminalOptions, TerminalFrameRenderer, build_terminal_model, build_terminal_html,
    build_terminal_mp4, build_terminal_gif, terminal_state, terminal_rows,
)
from src.terminal_style import terminal_output_tokens, wrap_tokens, token, OUTPUT_BASE_COLOR
from src.video_export import mp4_render_scale


class TerminalTests(unittest.TestCase):
    def test_ansi_styles_colors_resets_and_literal_content(self):
        tokens=terminal_output_tokens('\x1b[1;3;4;38;2;12;34;56;48;5;196mRGB\x1b[0m plain\x1b[38;5;244mgray\x1b[39m normal')
        self.assertEqual(tokens[0]['color'],'#0c2238')
        self.assertEqual(tokens[0]['background'],'#ff0000')
        self.assertTrue(all(tokens[0][key] for key in ('bold','italic','underline')))
        self.assertEqual(tokens[1],token(' plain'))
        self.assertEqual(tokens[2]['color'],'#808080')
        self.assertEqual(tokens[3]['color'],OUTPUT_BASE_COLOR)
        text='warning: café <script>\n\tfile/name.py ✓ built in 200ms'
        self.assertEqual(''.join(t['text'] for t in terminal_output_tokens(text)),text)
        self.assertEqual(''.join(t['text'] for t in terminal_output_tokens('\x1b]0;window\x07hello\x1b[2K')),'hello')

    def test_wrapping_and_scroll_preserve_last_output_and_prompt(self):
        rows=wrap_tokens([token('abc\tdef\n\nEND')],8)
        self.assertEqual([''.join(t['text'] for t in row) for row in rows],['abc     ','def','','END'])
        o=TerminalOptions(width=400,height=260,background_style='none',command='echo '+('word '*120),output='\n'.join(f'line {i}' for i in range(100)))
        m=build_terminal_model(o)
        self.assertEqual(m['events'][-1]['count'],len(o.command))
        self.assertGreater(len(m['events']),96)  # old exporter dropped words at this cap
        rows=terminal_rows(m,terminal_state(m,m['duration']))
        self.assertEqual(len(rows),m['visibleRows'])
        self.assertIn('line 99','\n'.join(''.join(t['text'] for t in row) for row in rows))
        self.assertEqual(''.join(t['text'] for t in rows[-1]),o.prompt+' ')

    def test_html_is_self_contained_safe_and_keeps_utf8(self):
        o=TerminalOptions(title='</script><b>café</b>',command='echo "✓ café"',output='__CONFIG__ </script>')
        document=build_terminal_html(o,True)
        payload=re.search(r'id="terminal-model"[^>]*>([^<]+)',document)[1]
        self.assertEqual(json.loads(base64.b64decode(payload)),dict(build_terminal_model(o),background='linear-gradient(135deg, #071321, #080d16, #07140f)'))
        self.assertNotIn(o.title,document)
        self.assertIn('data:font/',document)
        self.assertIn('document.fonts.ready',document)

    def test_frame_keys_and_hd_geometry(self):
        options=TerminalOptions(width=400,height=260,background_style='none',command='echo hello',output='one\ntwo\nthree')
        r=TerminalFrameRenderer(options)
        previous_key=previous_image=None
        for time in range(0,math.ceil(r.duration),100):
            key=r.frame_key(time);pixels=r.frame(time).tobytes()
            if key==previous_key:self.assertEqual(pixels,previous_image)
            previous_key,previous_image=key,pixels
        for options,size in [(TerminalOptions(),(1920,1080)),(TerminalOptions(width=720,height=1280,aspect_ratio='9_16'),(1080,1920))]:
            r=TerminalFrameRenderer(options,mp4_render_scale(options))
            self.assertEqual(r.frame(r.duration).size,size)
            self.assertEqual(r.fonts[0].size,30)
            self.assertEqual(r.model,build_terminal_model(options))

    def test_actual_mp4_gif_and_duration_limits(self):
        o=TerminalOptions(command='echo ok',output='✓ done',word_speed_ms=80,output_delay_ms=0,loop=False)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'terminal.mp4';path.write_bytes(build_terminal_mp4(o))
            reader=imageio.get_reader(str(path))
            try:
                self.assertEqual(reader.get_meta_data()['size'],(1920,1080))
                self.assertEqual(reader.get_meta_data()['fps'],30)
                self.assertEqual(reader.count_frames(),math.ceil(build_terminal_model(o)['duration']*30/1000))
                self.assertGreater(np.asarray(reader.get_data(reader.count_frames()-1)).std(),10)
            finally:reader.close()
        gif=Image.open(BytesIO(build_terminal_gif(o)))
        self.assertEqual(gif.width,700)
        self.assertNotIn('loop',gif.info)
        duration=0
        for frame in range(gif.n_frames):
            gif.seek(frame);duration+=gif.info['duration']
        self.assertLess(abs(duration-build_terminal_model(o)['duration']),50)
        with self.assertRaises(ExportLimitError):build_terminal_gif(replace(o,command='word '*100,word_speed_ms=1200))
        with self.assertRaises(ExportLimitError):build_terminal_mp4(replace(o,command='word '*200,word_speed_ms=1200))

    def test_routes_defaults_download_and_limit_response(self):
        values=_default_terminal_payload()
        self.assertEqual((values['background_style'],values['gradient_name']),('gradient','midnight'))
        with TestClient(app) as client:
            page=client.get('/terminal');self.assertEqual(page.status_code,200)
            for marker in ('terminal-seek','terminal-export-status','terminal.css','Full HD'):
                self.assertIn(marker,page.text)
            response=client.post('/terminal/download/html',data=values)
            self.assertEqual(response.status_code,200)
            self.assertIn('attachment',response.headers['content-disposition'])
            with patch('main.build_terminal_mp4',side_effect=ExportLimitError('Too long')):
                response=client.post('/terminal/download/mp4',data=values)
                self.assertEqual(response.status_code,422)
                self.assertEqual(response.text,'Too long')

    @unittest.skipUnless(shutil.which('node'),'Node.js needed for preview timeline parity')
    def test_javascript_preview_matches_python_at_seek_boundaries(self):
        # Run the preview state logic with a minimal DOM, without a browser/server.
        script=r'''
const fs=require('fs'),vm=require('vm');const fixtures=JSON.parse(fs.readFileSync(0,'utf8'));
function node(){return {style:{},classList:{toggle(){}},children:[],textContent:'',append(v){this.children.push(v)},replaceChildren(v){this.children=v.children}}}
(async()=>{const result=[];for(const f of fixtures){
 const ids={};for(const id of ['stage','terminal','screen','title','terminal-model'])ids[id]=node();
 ids['terminal-model'].textContent=Buffer.from(JSON.stringify(f.model)).toString('base64');
 const listeners={},parent={postMessage(){}};
 const context={document:{getElementById:id=>ids[id],createElement:node,createDocumentFragment:node,fonts:{ready:Promise.resolve()}},innerWidth:920,innerHeight:600,addEventListener:(name,fn)=>listeners[name]=fn,parent,window:{},requestAnimationFrame(){},atob:s=>Buffer.from(s,'base64').toString('binary'),TextDecoder,Uint8Array};
 vm.runInNewContext(fs.readFileSync('static/terminal_frame.js','utf8'),context);await Promise.resolve();
 const states=[];for(const time of f.times){listeners.message({source:parent,data:{type:'terminal:seek',time}});states.push(ids.screen.children.map(row=>row.children.filter(v=>v.className!=='cursor').map(v=>v.textContent).join('')))}result.push(states);
}process.stdout.write(JSON.stringify(result));})();'''
        options=[TerminalOptions(command='echo "café ✓"',output='\x1b[31merror\x1b[0m\n\tindented\n\nEND'),TerminalOptions(width=400,height=260,background_style='none',command='ab '*40,output='\n'.join('row '+str(i) for i in range(30))),TerminalOptions(command='',output='')]
        fixtures=[];expected=[]
        for o in options:
            m=build_terminal_model(o);times=[0,350,529,530,m['outputStart']-1,m['outputStart'],m['done']-1,m['done'],m['duration']]
            fixtures.append(dict(model=m,times=times))
            expected.append([[''.join(t['text'] for t in row) for row in terminal_rows(m,terminal_state(m,time))] for time in times])
        run=subprocess.run(['node','-e',script],input=json.dumps(fixtures),capture_output=True,text=True,encoding='utf-8',check=True)
        self.assertEqual(json.loads(run.stdout),expected)


if __name__=='__main__':unittest.main()
