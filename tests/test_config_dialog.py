"""E-35: «Configura tus clips» fits the window, in a real browser.

The app is served on a free local port and a headless Chrome or Edge (whichever is installed) opens it through the
DevTools protocol, at 770x910, 1280x720, 1366x768 and 1920x1080, in live and video mode. For each it checks that the
header is inside the window, that the buttons are inside the window and at the very end of the card (no empty area
under them), and that the options body scrolls to its top and to its bottom. `websockets` is in requirements.txt: if
it is missing the tests fail (they never skip for it). Only a machine with neither Chrome nor Edge skips them.
"""
import json, os, shutil, socket, subprocess, tempfile, threading, time, unittest, urllib.request
from pathlib import Path

SIZES = [(770, 910), (1280, 720), (1366, 768), (1920, 1080)]
CANDIDATES = [os.environ.get('CLIPSTUDIO_BROWSER', ''),
              r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
              shutil.which('google-chrome') or '', shutil.which('chromium') or '', shutil.which('chromium-browser') or '', shutil.which('msedge') or '']
BROWSER = next((c for c in CANDIDATES if c and Path(c).exists()), None)
from websockets.sync.client import connect      # in requirements.txt: missing it is an error, not a skip

# Opens the dialog in `mode` and measures it, as the user sees it (the visible area excludes scrollbars).
MEASURE = r"""
(async (mode) => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  if (typeof closeConfig === 'function') closeConfig();
  openConfig(mode);
  const modal = document.getElementById('configModal'), card = modal.querySelector('.modal-card');
  // the card «rises» 10 px when it opens: measure once its animations are over (a cold first run can be slow)
  // (only the finite ones: the start button's shine loops forever)
  await wait(100);
  const finite = card.getAnimations({subtree: true}).filter((a) => Number.isFinite(a.effect?.getComputedTiming?.().endTime));
  await Promise.race([Promise.all(finite.map((a) => a.finished.catch(() => {}))), wait(3000)]);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const head = card.querySelector('.cfg-head'), body = card.querySelector('.cfg-body'), actions = card.querySelector('.modal-actions');
  const H = Math.min(innerHeight, document.documentElement.clientHeight), r = (e) => e.getBoundingClientRect();
  const c = r(card), h = r(head), a = r(actions), b = r(body);
  body.scrollTop = 0; await wait(50); const top = body.scrollTop;
  // to the bottom; the body may still grow a little (frames, preferences load after it opens): retry for up to 1 s
  let bottomReached = false;
  for (let i = 0; i < 20 && !bottomReached; i++) {
    body.scrollTop = body.scrollHeight; await wait(50);
    bottomReached = Math.abs(body.scrollTop + body.clientHeight - body.scrollHeight) <= 1;
  }
  const scrollsWhenNeeded = body.scrollHeight <= body.clientHeight + 1 || getComputedStyle(body).overflowY === 'auto' || getComputedStyle(body).overflowY === 'scroll';
  body.scrollTop = 0; await wait(50); const backToTop = body.scrollTop;
  return {H, card: [c.top, c.bottom], head: [h.top, h.bottom], actions: [a.top, a.bottom], body: [b.top, b.bottom],
          title: document.getElementById('configTitle').textContent, top, backToTop, bottomReached, scrollsWhenNeeded,
          tall: body.scrollHeight > body.clientHeight};
})
"""


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


class ConfigDialogRequirementsTests(unittest.TestCase):
    def test_E35_the_browser_check_needs_only_what_requirements_txt_installs(self):
        reqs = (Path(__file__).resolve().parents[1] / 'requirements.txt').read_text(encoding='utf-8')
        self.assertRegex(reqs, r'(?m)^websockets\b')


@unittest.skipUnless(BROWSER, 'needs Chrome or Edge installed (set CLIPSTUDIO_BROWSER to its path)')
class ConfigDialogInABrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import uvicorn, app
        cls.port = free_port()
        cls.server = uvicorn.Server(uvicorn.Config(app.app, host='127.0.0.1', port=cls.port, log_level='warning'))
        threading.Thread(target=cls.server.run, daemon=True).start()
        for _ in range(100):
            try: urllib.request.urlopen(f'http://127.0.0.1:{cls.port}/', timeout=1); break
            except OSError: time.sleep(.1)
        cls.profile = tempfile.TemporaryDirectory()
        cls.browser = subprocess.Popen([BROWSER, '--headless=new', '--remote-debugging-port=0', f'--user-data-dir={cls.profile.name}',
                                        '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--mute-audio', 'about:blank'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        active = Path(cls.profile.name) / 'DevToolsActivePort'
        for _ in range(200):
            if active.exists() and active.read_text().strip(): break
            time.sleep(.1)
        debug_port = int(active.read_text().split()[0])
        pages = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json/list', timeout=5).read())
        # entered by hand (setUpClass/tearDownClass), as websockets wants connect() used as a context manager
        cls.conn = connect(next(p for p in pages if p['type'] == 'page')['webSocketDebuggerUrl'], max_size=None, open_timeout=10)
        cls.ws = cls.conn.__enter__()
        cls.ids = 0

    @classmethod
    def tearDownClass(cls):
        try: cls.conn.__exit__(None, None, None)
        finally:
            cls.browser.kill(); cls.browser.wait(10); cls.server.should_exit = True
            time.sleep(.3); cls.profile.cleanup()

    @classmethod
    def cdp(cls, method, **params):
        cls.ids += 1; me = cls.ids
        cls.ws.send(json.dumps({'id': me, 'method': method, 'params': params}))
        while True:
            msg = json.loads(cls.ws.recv(timeout=30))
            if msg.get('id') == me:
                if 'error' in msg: raise AssertionError(f'{method}: {msg["error"]}')
                return msg.get('result', {})

    def evaluate(self, expression):
        out = self.cdp('Runtime.evaluate', expression=expression, awaitPromise=True, returnByValue=True)
        if 'exceptionDetails' in out: raise AssertionError(out['exceptionDetails'])
        return out['result'].get('value')

    def open_app(self, width, height):
        self.cdp('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=False)
        self.cdp('Page.navigate', url=f'http://127.0.0.1:{self.port}/')
        for _ in range(150):
            # 'interactive' is enough: the page keeps some requests open (live status), so it may never be 'complete'
            if self.evaluate("document.readyState!=='loading' && typeof openConfig==='function' && !!document.getElementById('configModal') && document.fonts.status==='loaded'"): break
            time.sleep(.1)
        else: self.fail('the app did not load')

    def test_E35_configure_dialog_fits_every_window_in_live_and_video_mode(self):
        for width, height in SIZES:
            self.open_app(width, height)
            for mode in ('live', 'video'):
                with self.subTest(size=f'{width}x{height}', mode=mode):
                    m = self.evaluate(f'{MEASURE}({json.dumps(mode)})')
                    H = m['H']
                    self.assertIn('Clipping en vivo' if mode == 'live' else 'Video', m['title'])
                    self.assertGreaterEqual(m['head'][0], 0, m); self.assertLessEqual(m['head'][1], H, m)          # header in view
                    self.assertGreaterEqual(m['actions'][0], 0, m); self.assertLessEqual(m['actions'][1], H + .5, m)  # buttons in view
                    self.assertLessEqual(m['card'][1] - m['actions'][1], 2, m)                                       # no gap under them
                    self.assertGreaterEqual(m['card'][0], 0, m)                                                      # never cut at the top
                    self.assertTrue(m['scrollsWhenNeeded'], m)
                    self.assertEqual(m['top'], 0, m); self.assertTrue(m['bottomReached'], m); self.assertEqual(m['backToTop'], 0, m)
                    if m['tall']: self.assertLessEqual(m['card'][1], H + .5, m)                                      # a long body scrolls inside

    def test_E35_the_card_fits_a_dialog_layer_shorter_than_100vh(self):
        """What the user saw: the visible area shorter than 100vh (browser bars, zoom, a scrollbar). The layer is made
        300 px shorter than the window; a card sized only by 100vh overflowed it, centred, and lost its header."""
        self.open_app(770, 910)
        for mode in ('live', 'video'):
            with self.subTest(mode=mode):
                m = self.evaluate(f"""(async () => {{
                  const modal = document.getElementById('configModal'); modal.style.bottom = '300px';
                  const out = await ({MEASURE})({json.dumps(mode)});
                  const L = modal.getBoundingClientRect(); modal.style.bottom = '';
                  return Object.assign(out, {{layer: [L.top, L.bottom]}});
                }})()""")
                top, bottom = m['layer']
                self.assertGreaterEqual(m['head'][0], top, m); self.assertLessEqual(m['actions'][1], bottom + .5, m)
                self.assertLessEqual(m['card'][1] - m['actions'][1], 2, m)
                self.assertTrue(m['bottomReached'], m); self.assertEqual(m['backToTop'], 0, m)


if __name__ == '__main__':
    unittest.main()
