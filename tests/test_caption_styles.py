"""Animated subtitle styles (Fase 3): the same word timing in the MP4 (ASS) and in the editor preview."""
import re, unittest
import caption_styles as cs
from timeline import make_cues

stamp = lambda s: f'0:00:{s:05.2f}'
CUE = {'start': 1.0, 'end': 2.6, 'text': 'nos tocó llegar 30', 'words': [
    {'text': 'nos', 'start': 1.0, 'end': 1.2}, {'text': 'tocó', 'start': 1.25, 'end': 1.6},
    {'text': 'llegar', 'start': 1.65, 'end': 2.1}, {'text': '30', 'start': 2.15, 'end': 2.5}]}


def events(style, cue=CUE, text=None):
    return cs.events(cue, text or cue['text'], style, '#FFE14D', r'{\an5\pos(540,1555)}{\fs64}', stamp, '#FFFFFF', 64)


class WordTimeTests(unittest.TestCase):
    def test_words_of_the_transcript_are_used_while_they_match(self):
        self.assertEqual(cs.word_times(CUE), [(1.0, 1.2), (1.25, 1.6), (1.65, 2.1), (2.15, 2.5)])

    def test_edited_text_shares_the_cue_time_by_word_length(self):
        times = cs.word_times(dict(CUE, text='llegamos todos'))
        self.assertEqual(len(times), 2); self.assertAlmostEqual(times[0][0], 1.0); self.assertAlmostEqual(times[-1][1], 2.6)
        self.assertGreater(times[0][1] - times[0][0], times[1][1] - times[1][0])          # «llegamos» is longer

    def test_cues_from_the_transcript_carry_their_words(self):
        transcript = [{'start': 0, 'end': 2, 'text': 'hola a todos', 'words': [
            {'start': 0, 'end': .4, 'text': 'hola'}, {'start': .5, 'end': .7, 'text': 'a'}, {'start': .8, 'end': 1.3, 'text': 'todos'}]}]
        cue = make_cues(transcript, 0, 2)[0]
        self.assertEqual([w['text'] for w in cue['words']], ['hola', 'a', 'todos'])


class AssTests(unittest.TestCase):
    def test_classic_is_one_fixed_phrase_as_before(self):
        out = events('clasico')
        self.assertEqual(out, [r'Dialogue: 0,0:00:01.00,0:00:02.60,Caption,,0,0,0,,{\an5\pos(540,1555)}{\fs64}nos tocó llegar 30'])

    def test_karaoke_lights_each_word_in_turn(self):
        out = events('karaoke')
        self.assertEqual(len(out), 4)
        for i, line in enumerate(out):
            lit = re.findall(r'\{\\c&H4DE1FF&\}(\S+)\{', line)
            self.assertEqual(lit, [CUE['text'].split()[i]])
        self.assertIn('0:00:01.25', out[1]); self.assertTrue(out[-1].split(',')[2] == '0:00:02.60')

    def test_pop_scales_the_word_being_said(self):
        self.assertIn(r'\t(0,70,\fscx115\fscy115)', events('pop')[2])

    def test_highlighter_boxes_the_word_and_restores_the_size(self):
        line = events('resaltador')[0]
        self.assertIn(r'{\rBox\fs64}nos{\rCaption\fs64}', line)
        self.assertIn(',3,10,', cs.styles_block('Montserrat', 64, '&H00FFFFFF', '&H00000000', 4, '#FFE14D', 'resaltador', lambda c: '&H004DE1FF'))

    def test_key_words_are_numbers_and_the_longest(self):
        line = events('palabra_clave')[0]
        self.assertEqual(re.findall(r'\{\\c&H4DE1FF&\\fscx115\\fscy115\}(\S+)\{', line), ['llegar', '30'])

    def test_line_breaks_of_the_layout_are_kept(self):
        line = events('karaoke', text='nos tocó\nllegar 30')[0]
        self.assertIn(r'tocó\Nllegar', line)

    def test_cinema_fades_and_gaming_outline_is_thick(self):
        self.assertIn(r'\fad(120,80)', events('cine')[0])
        block = cs.styles_block('Montserrat', 64, '&H00FFFFFF', '&H00000000', 4, '#FFE14D', 'contorno', lambda c: '&H004DE1FF')
        self.assertIn(',1,9,4,2,', block.splitlines()[0])


class LookTests(unittest.TestCase):
    def test_each_style_has_a_heavy_face_and_a_strong_outline(self):
        self.assertEqual(set(cs.STYLE_FONT), set(cs.STYLES))
        block = cs.styles_block('Luckiest Guy', 64, '&H00FFFFFF', '&H00000000', 2, '#FFE14D', 'pop', lambda c: '&H004DE1FF')
        self.assertIn(',1,7,4,2,', block.splitlines()[0])            # outline 7, hard shadow 4, even with 2 chosen

    def test_a_face_that_is_not_installed_is_not_offered_to_the_export(self):
        import styling
        for name, file in styling.FONTS.items(): self.assertTrue((styling.ROOT / 'static/fonts' / file).exists(), name)
        self.assertIn('Montserrat', styling.FONTS)


class ExportTests(unittest.TestCase):
    def test_export_writes_the_chosen_style(self):
        import tempfile
        from pathlib import Path
        import app
        opts = app.Export(title='', subtitles='nos tocó llegar 30', start=0, end=3, caption_style='karaoke',
                          caption_upper=True, captions=[CUE])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'c.ass'; app.ass_file(path, opts, [])
            text = path.read_text(encoding='utf-8')
        self.assertEqual(text.count('Dialogue:'), 4)
        self.assertIn('NOS', text); self.assertIn('Style: Box,', text)


if __name__ == '__main__':
    unittest.main()
