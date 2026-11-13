import json, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from fastapi.testclient import TestClient
import app as backend
import profanity


def words(*items):
    return [dict(start=a, end=b, text=t) for a, b, t in items]


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.p = patch.object(profanity, 'FILE', None); self.p.start()
    def tearDown(self): self.p.stop()

    def test_strong_words_with_accents_case_punctuation_and_phrases(self):
        w = words((1, 1.3, ' ¡Mierda!'), (2, 2.2, ' hijo'), (2.2, 2.3, ' de'), (2.3, 2.6, ' puta'), (3, 3.3, ' CABRÓN,'), (4, 4.2, ' hola'))
        ranges = profanity.find(w, 0, 10)
        self.assertEqual(len(ranges), 3)
        self.assertAlmostEqual(ranges[1][0], 2 - profanity.LEAD, places=3); self.assertAlmostEqual(ranges[1][1], 2.6 + profanity.TAIL, places=3)
        self.assertTrue(all(not (a <= 4.1 <= b) for a, b in ranges))          # «hola» is never muted

    def test_doubtful_words_are_off_until_turned_on_and_custom_words_count(self):
        w = words((1, 1.3, ' marica'), (2, 2.3, ' parcero'))
        self.assertEqual(profanity.find(w, 0, 5), [])
        config = profanity.load(); [x.update(on=True) for x in config['words'] if x['word'] == 'marica']; config['custom'] = ['parcero']
        self.assertEqual(len(profanity.find(w, 0, 5, config)), 2)

    def test_times_are_relative_to_the_clip_and_outside_words_ignored(self):
        w = words((99, 99.4, ' mierda'), (101, 101.4, ' mierda'))
        self.assertEqual(profanity.find(w, 100, 110), [(round(1 - profanity.LEAD, 3), round(1.4 + profanity.TAIL, 3))])

    def test_subtitles_show_the_first_letter_and_asterisks(self):
        self.assertEqual(profanity.censor_text('Qué mierda, hijo de puta'), 'Qué m*****, h*** d* p***')
        self.assertEqual(profanity.censor_text('Hola parcero'), 'Hola parcero')

    def test_saved_choices_survive_and_unknown_words_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(profanity, 'FILE', Path(tmp) / 'p.json'):
            profanity.save({'mierda': False, 'marica': True, 'inventada': True}, ['gonorreíta'])
            c = profanity.load()
        on = {x['word']: x['on'] for x in c['words']}
        self.assertFalse(on['mierda']); self.assertTrue(on['marica']); self.assertNotIn('inventada', on); self.assertEqual(c['custom'], ['gonorreíta'])


def level(path, a, b, freq=None):
    """RMS (and the share of energy near `freq` Hz) of the audio of `path` between a and b seconds."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(a), '-t', str(b - a), '-i', str(path), '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'], capture_output=True).stdout
    x = np.frombuffer(raw, dtype='<f4')
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    if freq is None: return rms
    spec = np.abs(np.fft.rfft(x)) ** 2; f = np.fft.rfftfreq(len(x), 1 / 16000)
    return rms, float(spec[(f > freq - 40) & (f < freq + 40)].sum() / max(1e-9, spec.sum()))


class ExportTests(unittest.TestCase):
    def test_export_mutes_or_beeps_exactly_the_bad_word_and_hides_it_in_subtitles(self):
        client = TestClient(backend.app)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'src.mp4'
            backend.command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=size=320x180:rate=24', '-f', 'lavfi', '-i', 'sine=frequency=300:sample_rate=48000',
                             '-t', '4', '-c:v', 'libx264', '-c:a', 'aac', str(source)])
            with source.open('rb') as raw: ident = client.post('/api/upload', files={'file': ('src.mp4', raw, 'video/mp4')}).json()['id']
            backend.JOBS[ident]['transcript'] = [dict(start=.5, end=2.5, text=' esto es una mierda total', words=words((.5, .8, ' esto'), (.8, 1.0, ' es'), (1.0, 1.2, ' una'), (1.5, 2.0, ' mierda'), (2.1, 2.5, ' total')))]
            with patch.object(profanity, 'FILE', None):
                base = dict(start=0, end=4, title='', subtitles='esto es una mierda total', framing='crop')
                plain = Path(tmp) / 'plain.mp4'; plain.write_bytes(client.post(f'/api/jobs/{ident}/export', json=base).content)
                quiet = Path(tmp) / 'quiet.mp4'; r = client.post(f'/api/jobs/{ident}/export', json=dict(base, mute_words=True))
                self.assertEqual(r.status_code, 200, r.text[:300]); quiet.write_bytes(r.content)
                beep = Path(tmp) / 'beep.mp4'; beep.write_bytes(client.post(f'/api/jobs/{ident}/export', json=dict(base, mute_words=True, mute_sound='beep')).content)
                ranges = client.post(f'/api/jobs/{ident}/mute-ranges', json=dict(start=0, end=4)).json()['ranges']
                cues = backend.caption_cues(backend.Export(**dict(base, mute_words=True)), backend.JOBS[ident]['transcript'])
            self.assertEqual(len(ranges), 1)
            self.assertGreater(level(plain, 1.6, 1.9), .05)                         # the original has sound there
            self.assertLess(level(quiet, 1.6, 1.9), .01)                           # muted during «mierda»
            self.assertGreater(level(quiet, .5, 1.2), .05); self.assertGreater(level(quiet, 2.4, 3.5), .05)   # the rest keeps its sound
            rms, share = level(beep, 1.6, 1.9, 1000)
        self.assertGreater(share, .8)                                          # a 1 kHz beep instead of the 300 Hz tone
        self.assertNotIn('mierda', ' '.join(c['text'] for c in cues)); self.assertIn('m*****', ' '.join(c['text'] for c in cues))

    def test_off_by_default_for_new_projects_and_old_ones(self):
        self.assertFalse(backend.CLIP_DEFAULTS['mute_words']); self.assertFalse(backend.LEGACY_CLIP_SETTINGS['mute_words'])
        self.assertFalse(backend.Export(start=0, end=1, title='', subtitles='').mute_words)
        self.assertEqual(backend.ClipSettings().mute_sound, 'silence')


if __name__ == '__main__':
    unittest.main()
