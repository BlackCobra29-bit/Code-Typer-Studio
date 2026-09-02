import json
import re
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from io import BytesIO

from PIL import Image
from fastapi.testclient import TestClient
from src.languages import LANGUAGES
from src.renderer import RenderOptions, build_typing_html
from src.syntax_style import THEME_NAMES, highlight_code, detect_language, normalize_code
from src.typing_timeline import build_timeline
from src.gif_exporter import FrameRenderer, build_typing_gif
from src.diff_renderer import DiffOptions, build_diff_html, build_diff_model
from src.diff_exporter import DiffFrameRenderer
from src.scroll_renderer import ScrollOptions, build_scroll_html, build_scroll_model
from src.scroll_exporter import ScrollFrameRenderer
from main import CODE_ASPECT_RATIOS, _apply_code_aspect_ratio, app


class GlyphReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.glyph = False
        self.text = ''
    def handle_starttag(self, tag, attrs):
        self.glyph = tag == 'span' and dict(attrs).get('class') == 'glyph'
    def handle_endtag(self, tag):
        self.glyph = False
    def handle_data(self, text):
        if self.glyph: self.text += text


class HighlightingTests(unittest.TestCase):
    def test_original_dark_plus_rules_and_context(self):
        source = '@cache\ndef greet(name: str):\n    answer = 42\n    return "hello" # note'
        result = highlight_code(source, 'python', 'VS Code Dark+')
        tokens = {t['content']: t['color'].lower() for line in result['lines'] for t in line}
        expected = {'@cache':'#dcdcaa', 'greet':'#dcdcaa', 'name':'#9cdcfe',
                    'str':'#4ec9b0', '42':'#b5cea8', 'return':'#c586c0', '# note':'#6a9955'}
        for text, color in expected.items(): self.assertEqual(tokens[text], color)
        self.assertEqual(result['background'].lower(), '#1e1e1e')

    def test_dracula_is_a_real_distinct_theme(self):
        result = highlight_code('const greet = (name) => "hello";', 'javascript', 'Dracula')
        self.assertEqual(result['theme'], 'dracula')
        self.assertEqual(result['background'].lower(), '#282a36')
        self.assertTrue(any(t['color'].lower() == '#f1fa8c' for line in result['lines'] for t in line))

    def test_every_offered_language_and_theme_resolves(self):
        for language in LANGUAGES:
            if language in {'text','auto'}: continue
            with self.subTest(language=language):
                self.assertNotEqual(highlight_code('test\n', language, 'VS Code Dark+')['language'], 'text')
        for name, theme_id in THEME_NAMES.items():
            with self.subTest(theme=name):
                self.assertEqual(highlight_code('x = 1', 'python', name)['theme'], theme_id)

    def test_auto_detection_and_explicit_override(self):
        self.assertEqual(detect_language('interface User { id: number }', 'auto'), 'typescript')
        self.assertEqual(detect_language('const n = 1;', 'python'), 'python')
        self.assertEqual(detect_language('def greet(name):\n    return name\n', 'auto'), 'python')
        self.assertEqual(detect_language('', 'auto'), 'text')
        self.assertEqual(highlight_code('hello', 'unknown', 'VS Code Dark+')['language'], 'text')

    def test_source_round_trip_and_multiline_context(self):
        for source in ['', '\n\n', '\tvalue = "🦋 café"\r\n\r\n', 's = """first\nsecond\nthird"""\n']:
            with self.subTest(source=source):
                data = highlight_code(source, 'python', 'Dracula')
                self.assertEqual('\n'.join(''.join(t['content'] for t in line) for line in data['lines']), normalize_code(source))
                timeline = build_timeline(data, RenderOptions())
                self.assertEqual(''.join(c['text'] for c in timeline['chars']), normalize_code(source))


class AnimationTests(unittest.TestCase):
    def test_timing_is_deterministic_and_honors_line_pause(self):
        data = highlight_code('a\n\nb', 'text', 'VS Code Dark+')
        opts = RenderOptions(speed_ms=20, line_pause_ms=300, start_delay_ms=550)
        timeline = build_timeline(data, opts)
        self.assertEqual(timeline, build_timeline(data, opts))
        self.assertEqual(timeline['events'][0]['at'], 550)
        self.assertGreaterEqual(timeline['events'][2]['at']-timeline['events'][1]['at'], 300)
        self.assertEqual(timeline['duration']-timeline['typingEnd'], 1500)
        for mode in ['character','token','word','line']:
            other = build_timeline(data, replace(opts, typing_mode=mode))
            self.assertEqual(other['events'][-1]['count'], 4)
            self.assertEqual(sorted(e['at'] for e in other['events']), [e['at'] for e in other['events']])

    def test_html_escapes_source_without_replacing_user_markers(self):
        source = '</script><script>alert(1)</script> & __TITLE__ 🦋\n\n'
        output = build_typing_html(source, RenderOptions(language='text', autoplay=False))
        self.assertNotIn('</script><script>alert(1)', output)
        payload = json.loads(re.search(r'id="typingOptions">(.*?)</script>', output, re.S)[1])
        self.assertEqual(''.join(c['text'] for c in payload['timeline']['chars']), source)
        parser = GlyphReader(); parser.feed(output)
        self.assertEqual(parser.text, source.replace('\n',''))
        self.assertIn('data:font/ttf;base64,', output)
        self.assertIn('<title>Code Typing Animation</title>', output)
        self.assertNotIn('file-title', output)

    def test_frame_reveal_scroll_and_theme_match(self):
        source = '\n'.join(f'const n{i} = "test";' for i in range(16))
        opts = RenderOptions(language='javascript',theme_name='Dracula',width=700,height=300,font_family='JetBrains Mono',font_size=22)
        renderer = FrameRenderer(source, opts)
        self.assertEqual(renderer.timeline, build_timeline(renderer.highlight, opts))
        self.assertEqual(renderer.positions[-1][2], 15)
        self.assertGreater(renderer._scroll_at(renderer.duration)[1], 0)
        self.assertNotEqual(renderer.frame(0).tobytes(), renderer.frame(renderer.duration).tobytes())
        self.assertEqual(renderer.frame(renderer.duration).size, (700,300))
        self.assertEqual(renderer.bg, (40,42,54))

    def test_gif_does_not_repeat_unless_requested(self):
        opts = RenderOptions(width=520,height=260,speed_ms=4,start_delay_ms=0,loop=False)
        data = build_typing_gif('x = 1', opts)
        gif = Image.open(BytesIO(data))
        self.assertNotIn('loop', gif.info)
        self.assertGreater(gif.n_frames, 1)


class CodeDiffTests(unittest.TestCase):
    def test_diff_model_places_replacements_and_insertions_at_source_location(self):
        original = 'total = 1\nprint(total)'
        revised = 'total = 2\nprint(total)\n# complete'
        options = DiffOptions(language='python',theme_name='VS Code Dark+')
        model = build_diff_model(original,revised,options)
        changed = [(row['kind'],row['oldNumber'],row['newNumber']) for row in model['rows'] if row['kind'] != 'equal']
        self.assertEqual(changed,[('delete',1,None),('insert',None,1),('insert',None,3)])
        self.assertEqual(model['additions'],2)
        self.assertEqual(model['deletions'],1)
        self.assertGreater(model['timeline']['resolveStart'],model['timeline']['insertEnd'])
        only_insertions = build_diff_model('', 'first\nsecond', options)
        self.assertEqual([row['kind'] for row in only_insertions['rows']], ['insert','insert'])

    def test_diff_html_is_seekable_and_keeps_real_theme_tokens(self):
        output = build_diff_html('value = 1','value = "new"',DiffOptions(autoplay=False))
        self.assertIn('window.codeDiff=Object.freeze',output)
        self.assertIn('row-delete',output)
        self.assertIn('row-insert',output)
        self.assertIn('#ce9178',output.lower())
        self.assertNotIn('__ROWS__',output)
        self.assertIn('<title>Code Diff Animation</title>',output)
        self.assertNotIn('file-title',output)

    def test_blank_line_replaced_by_code_is_an_addition_only(self):
        options = DiffOptions(language='python',theme_name='VS Code Dark+')
        model = build_diff_model('first\n\nlast','first\n@decorator\nlast',options)
        changed = [row for row in model['rows'] if row['kind'] != 'equal']
        self.assertEqual([(row['kind'],row['silentDelete']) for row in changed],
                         [('delete',True),('insert',False)])
        self.assertEqual(model['additions'],1)
        self.assertEqual(model['deletions'],0)
        output = build_diff_html('first\n\nlast','first\n@decorator\nlast',options)
        self.assertIn('row-delete row-silent-delete',output)
        self.assertIn('"silentDelete": true',output)
        silent_row = re.search(r'<div class="diff-row row-delete row-silent-delete".*?</div>',output)
        self.assertIsNotNone(silent_row)
        self.assertNotIn('>−<',silent_row.group(0))

    def test_diff_frame_renderer_covers_change_and_resolved_states(self):
        options = DiffOptions(width=700,height=400,font_size=17,canvas_padding=48,background_style='gradient')
        renderer = DiffFrameRenderer('x = 1\nprint(x)','x = 2\nprint(x)',options)
        changing = renderer.frame(renderer.timeline['insertEnd'])
        resolved = renderer.frame(renderer.timeline['duration'])
        self.assertEqual(changing.size,(700,400))
        self.assertNotEqual(changing.tobytes(),resolved.tobytes())

    def test_diff_uses_the_same_code_metrics_as_typing(self):
        font = 'JetBrains Mono, Consolas, monospace'
        typing = FrameRenderer('value = 20',RenderOptions(
            font_family=font,font_size=20,line_height=1.55,width=700,height=400,
        ))
        diff = DiffFrameRenderer('value = 20','value = 20',DiffOptions(
            font_family=font,font_size=20,line_height=1.55,width=700,height=400,
        ))
        self.assertEqual(diff.content_x,typing.content_x)
        self.assertEqual(diff.row_h,typing.lh)
        self.assertEqual(diff.number_font.size,typing.number_font.size)
        self.assertEqual(diff.fonts[0].getlength('value = 20'),typing.fonts[0].getlength('value = 20'))


class AspectRatioTests(unittest.TestCase):
    def test_code_studios_offer_only_landscape_and_square_pixel_sizes(self):
        self.assertEqual(
            [(item['value'],item['width'],item['height']) for item in CODE_ASPECT_RATIOS],
            [('16_9',1280,720),('1_1',1080,1080)],
        )
        self.assertEqual(_apply_code_aspect_ratio('1_1'),(1080,1080,'1_1'))
        self.assertEqual(_apply_code_aspect_ratio('unsupported'),(1280,720,'16_9'))


class CodeScrollTests(unittest.TestCase):
    def test_scroll_model_normalizes_range_and_builds_cinematic_timeline(self):
        source = '\n'.join(f'const line{i} = {i};' for i in range(1,31))
        model = build_scroll_model(source,ScrollOptions(
            language='javascript',target_start=20,target_end=18,scroll_ms=1700,
        ))
        self.assertEqual((model['targetStart'],model['targetEnd']),(18,20))
        self.assertEqual(model['lineCount'],30)
        self.assertLess(model['timeline']['scrollStart'],model['timeline']['focusStart'])
        self.assertLess(model['timeline']['focusStart'],model['timeline']['scrollEnd'])
        self.assertGreater(model['timeline']['duration'],model['timeline']['focusEnd'])

    def test_scroll_html_is_seekable_theme_accurate_and_supports_line_ranges(self):
        source = 'const first = 1;\nconst second = "two";\nreturn second;'
        output = build_scroll_html(source,ScrollOptions(
            language='javascript',theme_name='VS Code Dark+',target_start=2,target_end=3,autoplay=False,
        ))
        self.assertIn('window.codeScroll=Object.freeze',output)
        self.assertEqual(output.count('class="scroll-line target-line"'),2)
        self.assertIn('#ce9178',output.lower())
        self.assertIn('"targetStart": 2',output)
        self.assertNotIn('__CODE_LINES__',output)
        self.assertNotIn('file-title',output)

    def test_scroll_raster_centers_target_and_matches_typing_metrics(self):
        source = '\n'.join(f'value_{i} = {i}' for i in range(1,31))
        options = ScrollOptions(width=700,height=400,font_size=20,line_height=1.55,
                                target_start=20,target_end=21,background_style='gradient',canvas_padding=48)
        renderer = ScrollFrameRenderer(source,options)
        typing = FrameRenderer(source,RenderOptions(width=700,height=400,font_size=20,line_height=1.55,
                                                     background_style='gradient',canvas_padding=48))
        self.assertGreater(renderer.target_scroll,0)
        self.assertEqual(renderer.content_x,typing.content_x)
        self.assertEqual(renderer.row_h,typing.lh)
        before = renderer.frame(renderer.timeline['scrollStart'])
        focused = renderer.frame(renderer.timeline['focusEnd'])
        self.assertEqual(focused.size,(700,400))
        self.assertNotEqual(before.tobytes(),focused.tobytes())

    def test_code_scroll_page_and_html_export_are_wired(self):
        client = TestClient(app)
        page = client.get('/code-scroll')
        self.assertEqual(page.status_code,200)
        self.assertIn('id="scroll-form"',page.text)
        select = page.text.split('id="scroll-aspect-ratio"',1)[1].split('</select>',1)[0]
        self.assertIn('value="16_9"',select)
        self.assertIn('value="1_1"',select)
        self.assertNotIn('value="9_16"',select)
        exported = client.post('/code-scroll/download/html',data={
            'code':'one\ntwo\nthree','language':'text','theme_name':'VS Code Dark+',
            'target_start':'2','target_end':'3','aspect_ratio':'16_9','font_size':'20',
            'line_height':'1.55','scroll_ms':'900','hold_ms':'500','start_delay_ms':'300',
            'font_family':'JetBrains Mono, Consolas, monospace','background_style':'none',
            'show_line_numbers':'on','show_window_chrome':'on',
        })
        self.assertEqual(exported.status_code,200)
        self.assertIn('window.codeScroll=Object.freeze',exported.text)
        self.assertIn('code-scroll-animation.html',exported.headers['content-disposition'])


if __name__ == '__main__': unittest.main()
