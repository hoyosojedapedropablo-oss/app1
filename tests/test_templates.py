"""Clip templates (Fase 3): built-in ones per niche and the user's own."""
import tempfile, unittest
from pathlib import Path
import templates, caption_styles, styling


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.old = templates.FILE; templates.FILE = Path(self.tmp.name) / 'templates.json'
        self.addCleanup(setattr, templates, 'FILE', self.old)

    def test_builtin_templates_use_real_styles_fonts_and_formats(self):
        self.assertEqual(len(templates.BUILTIN), 6)
        for t in templates.BUILTIN:
            v = t['values']
            self.assertLessEqual(set(v), templates.KEYS, t['id'])
            self.assertIn(v['caption_style'], caption_styles.STYLES)
            self.assertIn(v['font'], styling.ALL_FONTS); self.assertIn(v['title_font'], styling.ALL_FONTS)
            self.assertIn(v['framing'], ('zoom', 'crop', 'stack', 'fit'))

    def test_only_known_short_values_are_kept(self):
        v = templates.clean({'font': 'Bangers', 'caption_size': 70, 'caption_upper': True, 'start': 3, 'title': 'x',
                             'caption_color': '<script>', 'logo': 'a' * 50})
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


if __name__ == '__main__':
    unittest.main()
