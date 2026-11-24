import math
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

import imageio.v2 as imageio
from PIL import Image

from src.diff_exporter import DiffFrameRenderer
from src.diff_renderer import DiffOptions
from src.gif_exporter import FrameRenderer
from src.renderer import RenderOptions
from src.scroll_exporter import ScrollFrameRenderer
from src.scroll_renderer import ScrollOptions
from src.video_export import encode_mp4, mp4_render_scale


class VideoExportTests(unittest.TestCase):
    def test_native_scale_preserves_layout_and_timeline_in_all_studios(self):
        source = '\n'.join(f'value_{i} = {i}' for i in range(30))
        common = dict(width=1280,height=720,font_size=20,canvas_padding=50,background_style='gradient')
        jobs = (
            (FrameRenderer,(source,),RenderOptions(**common)),
            (DiffFrameRenderer,(source,source.replace('= 15','= 16')),DiffOptions(**common)),
            (ScrollFrameRenderer,(source,),ScrollOptions(**common,target_start=23,target_end=24)),
        )
        for factory,args,options in jobs:
            with self.subTest(studio=factory.__name__):
                preview = factory(*args,options)
                hd = factory(*args,options,render_scale=mp4_render_scale(options))
                self.assertEqual(hd.timeline,preview.timeline)
                for name in ('width','height','size','padding_x','padding_y','content_x','chrome','radius'):
                    self.assertEqual(getattr(hd,name),getattr(preview,name)*1.5,name)
                self.assertEqual(hd.fonts[0].size,30)
                self.assertEqual(hd.frame(hd.duration).size,(1920,1080))

    def test_hold_keys_never_reuse_a_changed_frame(self):
        source = 'value = 1\nprint(value)\nreturn value'
        common = dict(width=480,height=270,font_size=18,background_style='none')
        renderers = (
            FrameRenderer(source,RenderOptions(**common,speed_ms=4,line_pause_ms=500,start_delay_ms=350)),
            DiffFrameRenderer(source,source.replace('= 1','= 2'),DiffOptions(**common,hold_ms=300,transition_ms=240)),
            ScrollFrameRenderer('\n'.join([source]*8),ScrollOptions(**common,target_start=20,scroll_ms=450,hold_ms=300)),
        )
        for renderer in renderers:
            with self.subTest(studio=type(renderer).__name__):
                previous_key = previous_bytes = None
                reused = 0
                for index in range(math.ceil(renderer.duration*60/1000)):
                    at = index*1000/60
                    key = renderer.frame_key(at)
                    pixels = renderer.frame(at).tobytes()
                    if key == previous_key:
                        self.assertEqual(pixels,previous_bytes,f'incorrect reuse at {at} ms')
                        reused += 1
                    previous_key,previous_bytes = key,pixels
                self.assertGreater(reused,10)

    def test_parallel_encoder_preserves_order_holds_and_odd_dimensions(self):
        class TestRenderer:
            duration = 200

            def __init__(self):
                self.calls = []

            def frame_key(self, at):
                return min(4,round(at*30/1000))

            def frame(self, at):
                index = self.frame_key(at)
                # Later frames finish first; the encoded stream must stay ordered.
                time.sleep(.03 if index == 0 else .001)
                self.calls.append(index)
                value = 20+index*30
                return Image.new('RGB',(97,65),(value,value,value))

        renderer = TestRenderer()
        data = encode_mp4(renderer,'test-video-',30)
        self.assertEqual(sorted(renderer.calls),[0,1,2,3,4])
        # Fast-start MP4 places playback metadata ahead of the media payload.
        self.assertLess(data.index(b'moov'),data.index(b'mdat'))
        with TemporaryDirectory() as directory:
            path = Path(directory)/'ordered.mp4'
            path.write_bytes(data)
            with imageio.get_reader(str(path)) as reader:
                self.assertEqual(reader.get_meta_data()['size'],(98,66))
                self.assertEqual(reader.get_meta_data()['fps'],30)
                self.assertEqual(reader.count_frames(),6)
                for index,value in enumerate((20,50,80,110,140,140)):
                    self.assertLessEqual(abs(int(reader.get_data(index)[20,20,0])-value),3)

    def test_invalid_frame_rate_is_rejected_before_encoding(self):
        for fps in (0,-1,121,float('nan'),float('inf')):
            with self.subTest(fps=fps),self.assertRaises(ValueError):
                encode_mp4(None,'test-video-',fps)


if __name__ == '__main__':
    unittest.main()
