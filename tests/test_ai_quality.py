"""Quality of what the AI delivers: clips with speech, titles a clipper would write, names heard right, the format chosen."""
import unittest
import live, quality, viral


def said(text, start=0.0, rate=3.0):
    """Words of `text` at `rate` words per second from `start`."""
    out, t = [], start
    for w in text.split():
        out.append({'start': round(t, 2), 'end': round(t + .8 / rate * 2, 2), 'text': ' ' + w}); t += 1 / rate
    return out


class SpeechSpanTests(unittest.TestCase):
    def test_a_clip_that_is_mostly_silence_is_dropped(self):
        words = said('hola qué tal todo bien', 0) + said('sí claro vamos', 20)          # 7 words in 30 s
        self.assertIsNone(quality.speech_span(words, 0, 30, 15))

    def test_a_long_pause_cuts_the_clip_to_the_part_with_the_talk(self):
        talk = said(' '.join(f'palabra{i}' for i in range(60)), 10, rate=3)             # 20 s of talk from 10 s
        words = said('eh', 0) + talk
        span = quality.speech_span(words, 0, 40, 15)
        self.assertIsNotNone(span); self.assertGreaterEqual(span[0], 9.5); self.assertLessEqual(span[1], 31)

    def test_a_dense_clip_is_kept_as_it_is(self):
        words = said(' '.join(f'p{i}' for i in range(75)), 0, rate=3)                   # 25 s of talk
        self.assertEqual(quality.speech_span(words, 0, 25, 15), (0, 25))


class TitleRuleTests(unittest.TestCase):
    TEXT = ('Lessie. Actívense. Quiero escuchar el par de Super Chat. Actívense de la gente mía, los panos míos. '
            'Acuérdense, después que pongan el Tortón J. Lessie y pongan su nombre para yo saber quién me lo envió')

    def ok(self, title, names=('JLexis',)):
        return viral.grounded_title(title, self.TEXT, 'HotSpanish Vlogs', list(names), 'LA MANSIÓN VIP')

    def test_a_clipper_style_title_with_the_right_name_passes(self):
        self.assertTrue(self.ok('JLexis le hace un llamado a sus fans para que se activen con los superchats'))
        self.assertTrue(self.ok('¿Quién responderá al llamado de JLexis en los superchats?'))

    def test_invented_names_and_quotes_do_not(self):
        self.assertFalse(self.ok('Westcol le hace un llamado a sus fans con los superchats'))       # not in the stream
        self.assertFalse(self.ok('JLexis pide superchats a Kunno'))
        self.assertFalse(self.ok('JLexis explota: «Actívense o desaparecerán»'))                     # never said
        self.assertFalse(self.ok('Un viaje a Cancún que nadie esperaba'))

    def test_a_listed_name_only_where_it_sounds_said(self):
        other = 'la comida está muy chiquito, no me alcanza para nada, quiero más arroz'
        self.assertFalse(viral.grounded_title('JLexis se queja de la comida chiquita', other, 'HotSpanish Vlogs', ['JLexis'], ''))
        self.assertTrue(viral.sounds_said('jlexis', 'pongan el Tortón J. Lessie'))

    def test_the_model_gets_the_names_and_the_channel(self):
        seen = {}
        def complete(payload, cancel):
            seen.update(payload)
            return {'afirmacion': 'pide superchats', 'tipo': 'reacción', 'mejor': 0,
                    'titulos': ['JLexis le hace un llamado a sus fans para que se activen con los superchats', 'a', 'b', 'c', 'd']}
        r = viral.generate(self.TEXT, speaker='HotSpanish Vlogs', context='LA MANSIÓN VIP', names=['JLexis'], complete=complete)
        self.assertEqual(seen['nombres_del_directo'], ['JLexis']); self.assertEqual(seen['canal'], 'HotSpanish Vlogs')
        self.assertTrue(r['title'].startswith('JLexis'))


class StreamNamesTests(unittest.TestCase):
    def test_names_come_from_the_title_description_and_tags(self):
        names = live.stream_names('LA MANSIÓN VIP TEMPORADA 2 | DÍA 2', 'Participantes: JLexis, Lupita Villalobos y @kunno. #LaMansionVIP Sígueme en Instagram',
                                  tags=['hotspanish'])
        for n in ('JLexis', 'Lupita Villalobos', 'kunno', 'LaMansionVIP', 'hotspanish'): self.assertIn(n, names)
        for n in ('Participantes', 'Sígueme', 'Instagram'): self.assertNotIn(n, names)

    def test_E28_a_shouted_word_of_the_stream_title_is_not_a_name(self):
        self.assertNotIn('PESAJE', live.stream_names('EL PESAJE - STREAM FIGHERS 5'))
        names = live.stream_names('WESTCOL vs SPREEN: EL PESAJE', 'Hoy Westcol se pesa en directo', tags=['Spreen'])
        self.assertIn('WESTCOL', names); self.assertIn('SPREEN', names); self.assertNotIn('PESAJE', names)
        self.assertIn('VIP', live.stream_names('fiesta VIP con todos'))   # short acronyms still count («Fiesta VIP» is one two-word name)

    def test_the_transcriber_is_told_the_names(self):
        import tempfile
        try: from test_live import make_segment
        except ImportError: from tests.test_live import make_segment
        calls = []
        class Whisper:
            def transcribe(self, audio, **kw): calls.append(kw); return iter([]), None
        with tempfile.TemporaryDirectory() as tmp:
            s = live.LiveSession(tmp, 'https://kick.com/canal', vocabulary=['JLexis']); s.stream_words = ['La Mansión VIP']; s.channel = 'HotSpanish'
            s.segments.mkdir(parents=True); s.clips.mkdir(parents=True); s._model = Whisper(); s.transcription_device = 'CPU'
            make_segment(s.segments / 'seg000000.ts', loud=True)
            s._ingest(s.segments / 'seg000000.ts')
        self.assertEqual(s.names()[:3], ['JLexis', 'La Mansión VIP', 'HotSpanish'])
        self.assertTrue(calls, 'the transcriber was not called')
        self.assertIn('JLexis', calls[0]['hotwords']); self.assertIn('JLexis', calls[0]['initial_prompt'])


class ChosenFormatTests(unittest.TestCase):
    def test_another_format_is_never_turned_into_camera_and_game(self):
        import app as backend
        self.assertFalse(backend.wants_stack(dict(clip_settings=dict(framing='crop', auto_stack=True))))
        self.assertFalse(backend.wants_stack(dict(clip_settings=dict(framing='zoom', auto_stack=True))))
        self.assertTrue(backend.wants_stack(dict(clip_settings=dict(framing='stack'))))


if __name__ == '__main__':
    unittest.main()
