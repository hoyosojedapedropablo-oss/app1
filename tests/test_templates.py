"""Subtitle templates: built-in ones per niche and the user's own — only the subtitles' look, never format, title or logo."""
import json, re
import tempfile, unittest
from pathlib import Path
import templates, caption_styles, styling


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.old = templates.FILE; templates.FILE = Path(self.tmp.name) / 'templates.json'
        self.addCleanup(setattr, templates, 'FILE', self.old)

    SUBTITLE_KEYS = {'font', 'caption_size', 'caption_color', 'outline_color', 'outline_width', 'caption_style', 'caption_accent',
                     'caption_upper', 'caption_y'}

    def test_templates_carry_only_the_subtitles_look(self):
        self.assertEqual(templates.KEYS, self.SUBTITLE_KEYS)
        self.assertEqual(len(templates.BUILTIN), 6)
        for t in templates.BUILTIN:
            v = t['values']
            self.assertLessEqual(set(v), self.SUBTITLE_KEYS, t['id'])
            self.assertFalse({k for k in v if k in ('framing', 'zoom', 'show_subtitles', 'style') or k.startswith(('title', 'logo'))}, t['id'])
            self.assertIn(v['caption_style'], caption_styles.STYLES)
            self.assertIn(v['font'], styling.ALL_FONTS)
            self.assertTrue(40 <= v['caption_size'] <= 90 and 0 <= v['outline_width'] <= 9, t['id'])   # the editor's ranges

    def test_a_saved_template_keeps_only_subtitle_values(self):
        t = templates.save('Solo subtítulos', {'font': 'Anton', 'caption_style': 'pop', 'caption_y': 70, 'framing': 'stack', 'zoom': 'soft',
                                               'title_font': 'Anton', 'title_size': 50, 'logo': 'abc', 'logo_width': 20, 'show_subtitles': False})
        self.assertEqual(t['values'], {'font': 'Anton', 'caption_style': 'pop', 'caption_y': 70})

    def test_an_older_user_template_is_read_without_its_format_title_or_logo(self):
        old = [{'id': 'abcdef123456', 'name': 'Vieja', 'niche': 'Mis plantillas',
                'values': {'framing': 'crop', 'zoom': 'close', 'font': 'Bangers', 'title_font': 'Anton', 'logo': 'x', 'caption_size': 80}}]
        templates.FILE.write_text(json.dumps(old), encoding='utf-8')
        mine = [t for t in templates.all_templates() if not t['builtin']]
        self.assertEqual(mine[0]['values'], {'font': 'Bangers', 'caption_size': 80})
        self.assertEqual(json.loads(templates.FILE.read_text(encoding='utf-8')), old)          # the file is not rewritten

    def test_only_known_short_values_are_kept(self):
        v = templates.clean({'font': 'Bangers', 'caption_size': 70, 'caption_upper': True, 'start': 3, 'title': 'x',
                             'caption_color': '<script>', 'caption_accent': 'a' * 50})
        self.assertEqual(v, {'font': 'Bangers', 'caption_size': 70, 'caption_upper': True})

    def test_save_replace_and_delete_a_user_template(self):
        a = templates.save('Mi estilo', {'font': 'Anton', 'caption_style': 'pop'})
        b = templates.save('mi estilo', {'font': 'Bangers'})                    # same name: replaced
        mine = [t for t in templates.all_templates() if not t['builtin']]
        self.assertEqual([t['values'] for t in mine], [{'font': 'Bangers'}])
        self.assertFalse(templates.delete(a['id'])); self.assertTrue(templates.delete(b['id']))
        self.assertEqual([t for t in templates.all_templates() if not t['builtin']], [])
        with self.assertRaises(ValueError): templates.save('  ', {'font': 'Anton'})
        with self.assertRaises(ValueError): templates.save('Vacía', {'start': 1})

    def test_api_lists_saves_and_deletes(self):
        import app
        from fastapi.testclient import TestClient
        old = app._templates.FILE; app._templates.FILE = Path(self.tmp.name) / 'api.json'
        self.addCleanup(setattr, app._templates, 'FILE', old)
        client = TestClient(app.app)
        self.assertEqual(len(client.get('/api/templates').json()['templates']), 6)
        made = client.post('/api/templates', json={'name': 'Clipero', 'values': {'font': 'Anton'}}).json()
        self.assertEqual(len(client.get('/api/templates').json()['templates']), 7)
        self.assertEqual(client.delete('/api/templates/streamer-pop').status_code, 404)    # built-in ones stay
        self.assertEqual(client.delete(f"/api/templates/{made['id']}").status_code, 200)


    def test_the_editor_has_the_card_the_font_pickers_and_the_size_box(self):
        root = Path(__file__).resolve().parents[1] / 'static'
        html = (root / 'index.html').read_text(encoding='utf-8'); js = (root / 'app.js').read_text(encoding='utf-8')
        self.assertIn('id="tplCard"', html); self.assertIn('Ver plantillas de subtítulos', html)
        for gone in ('templateSelect', 'templateApply', 'templateName', 'templateSave', 'tpl-box'): self.assertNotIn(gone, html)
        self.assertIn('<select id="font">', html); self.assertIn('<select id="title_font">', html)     # kept, hidden and in sync
        self.assertIn("fontPicker('font');fontPicker('title_font');", js)
        self.assertIn("SEL_KEYS={previewTitle:'title_size',previewCaption:'caption_size',previewLogo:'logo_width'}", js)
        self.assertNotIn('prompt(', js[js.index('// Subtitle templates (templates.py)'):])
        keys = re.search(r"const TPL_KEYS=\[(.*?)\];", js).group(1)
        self.assertEqual(set(re.findall(r"'(\w+)'", keys)), templates.KEYS)        # the editor applies and saves the same keys

if __name__ == '__main__':
    unittest.main()
