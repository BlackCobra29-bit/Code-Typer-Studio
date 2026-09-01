import json
import re
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from io import BytesIO

from PIL import Image
from src.languages import LANGUAGES
from src.renderer import RenderOptions, build_typing_html
from src.syntax_style import THEME_NAMES, highlight_code, detect_language, normalize_code
from src.typing_timeline import build_timeline
from src.gif_exporter import FrameRenderer, build_typing_gif
from src.diff_renderer import DiffOptions, build_diff_html, build_diff_model
from src.diff_exporter import DiffFrameRenderer


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

    def test_diff_frame_renderer_covers_change_and_resolved_states(self):
        options = DiffOptions(width=700,height=400,font_size=17,canvas_padding=48,background_style='gradient')
        renderer = DiffFrameRenderer('x = 1\nprint(x)','x = 2\nprint(x)',options)
        changing = renderer.frame(renderer.timeline['insertEnd'])
        resolved = renderer.frame(renderer.timeline['duration'])
        self.assertEqual(changing.size,(700,400))
        self.assertNotEqual(changing.tobytes(),resolved.tobytes())


if __name__ == '__main__': unittest.main()
