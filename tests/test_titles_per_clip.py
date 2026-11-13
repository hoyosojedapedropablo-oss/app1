"""Titles that tell what happens in THIS clip, said by who really speaks (E-26)."""
import unittest
from unittest.mock import patch
import intelligence
import viral

GUEST = 'Juan Camilo cuenta que estuvo ocho años en la cárcel y que la delincuencia te cambia la vida para siempre'


class TitleRuleTests(unittest.TestCase):
    def test_E26_stray_capitals_become_spanish_case(self):
        text = 'Entramos al piso con el ariete y Westcol dispara'
        self.assertEqual(intelligence.clean_title('Desastre en el Piso de entrenamiento', text), 'Desastre en el piso de entrenamiento')
        self.assertEqual(intelligence.clean_title('Recorrido de Tiro Táctico con Westcol', text + ' en el tiro táctico'), 'Recorrido de tiro táctico con Westcol')
        self.assertEqual(intelligence.clean_title('¿Lo logran? Westcol entra al piso', text), '¿Lo logran? Westcol entra al piso')

    def test_E26_a_name_opening_the_title_must_be_said_in_the_clip(self):
        self.assertIsNone(intelligence.clean_title('Westcol: mi historia en la cárcel y cómo la delincuencia te cambia la vida', GUEST))
        self.assertEqual(intelligence.clean_title('Así cambió su vida tras ocho años en la cárcel', GUEST), 'Así cambió su vida tras ocho años en la cárcel')
        self.assertEqual(intelligence.clean_title('Juan Camilo y sus ocho años en la cárcel', GUEST), 'Juan Camilo y sus ocho años en la cárcel')

    def test_E26_generic_titles_are_rejected(self):
        for title in ('Descripción de la misión', 'Preparación para la misión', 'Entrenamiento diferenciado'):
            self.assertIsNone(intelligence.clean_title(title, 'la misión de hoy es entrar al piso'), title)

    def test_E26_viral_titles_do_not_borrow_a_name_from_the_context(self):
        self.assertFalse(viral.grounded_title('Westcol: mi historia en la cárcel', GUEST, names=['Westcol']))
        self.assertTrue(viral.grounded_title('Westcol no encuentra la planta', 'Uescol, la planta, ¿dónde está la planta?', names=['Westcol']))

    def test_E26_a_name_the_transcriber_split_in_two_still_counts(self):
        """«J. Lessie» for JLexis (.62 joined) still passes; «westcol» ~ «estuvo» (.62, one word) does not."""
        said = 'Acuérdense, después que pongan el Tortón J. Lessie y pongan su nombre'
        self.assertTrue(viral.sounds_said('jlexis', said, .7, joined=.6))
        self.assertFalse(viral.sounds_said('westcol', GUEST, .7, joined=.6))
        self.assertTrue(viral.sounds_said('westcol', 'Uescol, la planta', .7, joined=.6))

    def test_E26_title_writer_is_told_the_analysis_decides_who_and_tone(self):
        self.assertIn('una broma no es una crítica', viral.SYSTEM.lower())
        self.assertNotIn('se pelea con', viral.SYSTEM)


class PerClipTitleTests(unittest.TestCase):
    def test_E26_each_judged_clip_gets_its_own_title_from_the_analysis(self):
        import app
        seen = {}
        def generate(text, **kw):
            seen.update(kw); return {'title': 'Juan Camilo y sus ocho años en la cárcel', 'claim': 'x',
                                     'titles': ['Juan Camilo y sus ocho años en la cárcel', 'Westcol: mi historia en la cárcel']}
        class O: speaker = ''; context = 'Podcast'
        clip = {'text': GUEST, 'title': 'Así era su vida', 'titles': [], 'analysis': {'quien': 'Juan Camilo'}}
        with patch('viral.generate', side_effect=generate):
            out = app.clip_title(clip, O(), ['Westcol'])
        self.assertEqual(seen['analysis'], {'quien': 'Juan Camilo'})
        self.assertEqual(out['title'], 'Juan Camilo y sus ocho años en la cárcel')
        self.assertNotIn('Westcol: mi historia en la cárcel', out['titles'])           # filtered by clean_title
        self.assertIn('Así era su vida', out['titles'])                                 # the batch title stays as an option

    def test_E26_the_page_asks_for_each_script_with_its_own_version(self):
        import app
        from fastapi.testclient import TestClient
        html = TestClient(app.app).get('/').text
        stamp = int((app.ROOT / 'static' / 'shell.js').stat().st_mtime)
        self.assertIn(f'/static/shell.js?v={stamp}', html)


if __name__ == '__main__':
    unittest.main()
