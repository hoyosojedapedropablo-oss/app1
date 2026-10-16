"""App-owned browser session. Never open or decrypt a user's browser profile.

All Playwright operations live on one worker thread. Only YouTube cookies are
passed to the downloader, in memory; HTTP endpoints expose status only.
"""
import atexit
import json
import os
import queue
import shutil
import threading
from concurrent.futures import Future
from pathlib import Path

AUTH_NAMES = {'SID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID',
              '__Secure-1PAPISID', '__Secure-3PAPISID', 'LOGIN_INFO'}


class SessionUnavailable(ValueError):
    pass


def find_browser():
    """Reuse installed software, never its regular profile or remote debugger."""
    candidates = []
    if os.name == 'nt':
        for root in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(root)
            if base:
                candidates.extend(Path(base) / suffix for suffix in (
                    'BraveSoftware/Brave-Browser/Application/brave.exe',
                    'Microsoft/Edge/Application/msedge.exe',
                    'Google/Chrome/Application/chrome.exe'))
    for name in ('brave-browser', 'brave', 'microsoft-edge', 'google-chrome', 'chromium', 'chromium-browser'):
        executable = shutil.which(name)
        if executable:
            candidates.append(Path(executable))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise SessionUnavailable('No se encontró un navegador compatible instalado para conectar YouTube.')


def youtube_cookies(cookies):
    # Domain boundary check: youtube.com.evil.example must never be accepted.
    return [c for c in cookies if c['domain'].lstrip('.') == 'youtube.com'
            or c['domain'].endswith('.youtube.com')]


class YouTubeSession:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.marker = self.directory / 'authorized'
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._thread = None
        self._context = None
        self._playwright = None
        self._visible = False

    def _call(self, operation):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()
        future = Future()
        self._queue.put((operation, future))
        try:
            return future.result(timeout=50)
        except TimeoutError:
            raise SessionUnavailable('La conexión de YouTube no respondió a tiempo.') from None

    def _worker(self):
        while True:
            operation, future = self._queue.get()
            try:
                result = self._perform(operation)
            except SessionUnavailable as error:
                future.set_exception(error)
            except Exception:
                # Playwright errors can include paths, URLs and browser output.
                future.set_exception(SessionUnavailable(
                    'No se pudo abrir la conexión propia de YouTube. Cierra solo la ventana de conexión de Clip Studio y vuelve a conectar.'))
            else:
                future.set_result(result)
            if operation == 'shutdown':
                return

    def _open(self, visible=False):
        if self._context is not None:
            try:
                self._context.cookies('https://www.youtube.com')
            except Exception:
                self._context = None
        if self._context is not None and visible and not self._visible:
            self._context.close()
            self._context = None
        if self._context is None:
            from playwright.sync_api import sync_playwright
            executable = find_browser()
            if self._playwright is None:
                self._playwright = sync_playwright().start()
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            options = {}
            if not visible and self.marker.exists():
                try:
                    agent = json.loads(self.marker.read_text()).get('user_agent')
                    if isinstance(agent, str) and agent:
                        options['user_agent'] = agent
                except (ValueError, OSError):
                    pass
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self.directory / 'profile'), executable_path=executable,
                headless=not visible, accept_downloads=False, timeout=30000, **options)
            self._visible = visible
        return self._context

    def _perform(self, operation):
        if operation == 'connect':
            if not self.marker.exists() and (self.directory / 'profile').exists():
                raise SessionUnavailable('Hay un perfil propio pendiente de borrar. Pulsa Desconectar antes de crear una conexión nueva.')
            context = self._open(visible=True)
            # Consent is persisted separately from browser data, never inferred
            # from the existence of any browser installed on the computer.
            self.marker.touch(mode=0o600, exist_ok=True)
            page = next((p for p in context.pages if not p.is_closed()), None) or context.new_page()
            # Keep the same browser identity when later resuming without a window.
            # The marker contains consent + User-Agent only, never cookie values.
            self.marker.write_text(json.dumps({'user_agent': page.evaluate('navigator.userAgent')}))
            page.goto('https://www.youtube.com/', wait_until='domcontentloaded', timeout=30000)
            page.bring_to_front()
        elif operation in ('disconnect', 'shutdown'):
            if self._context is not None:
                context, self._context = self._context, None
                try:
                    if operation == 'disconnect':
                        context.clear_cookies()
                except Exception:
                    pass  # The user may already have closed the browser window.
                try:
                    context.close()
                except Exception:
                    pass
            if self._playwright is not None:
                driver, self._playwright = self._playwright, None
                try:
                    driver.stop()
                except Exception:
                    pass
            if operation == 'disconnect':
                self.marker.unlink(missing_ok=True)
                try:
                    shutil.rmtree(self.directory / 'profile')
                except FileNotFoundError:
                    pass
                except OSError:
                    raise SessionUnavailable('La autorización se retiró, pero no se pudo borrar el perfil propio. Cierra la ventana de conexión de Clip Studio y pulsa Desconectar otra vez.') from None
            return {'authorized': False, 'connected': False}
        if not self.marker.exists():
            if operation in ('cookies','download_context'):
                raise SessionUnavailable('Conecta YouTube desde Clip Studio para autorizar una sesión propia.')
            if (self.directory / 'profile').exists():
                return {'authorized': False, 'connected': False, 'cleanup_pending': True,
                        'message': 'La conexión no está autorizada. Pulsa Desconectar para borrar el perfil propio pendiente.'}
            return {'authorized': False, 'connected': False}
        cookies = youtube_cookies(self._open().cookies('https://www.youtube.com'))
        connected = any(c['name'] in AUTH_NAMES for c in cookies)
        if operation in ('cookies','download_context'):
            if not connected:
                raise SessionUnavailable('Abre Conectar YouTube e inicia sesión en la ventana de Clip Studio.')
            if operation == 'download_context':
                context = self._open()
                page = next((p for p in context.pages if not p.is_closed()), None) or context.new_page()
                return {'cookies': cookies, 'user_agent': page.evaluate('navigator.userAgent')}
            return cookies
        return {'authorized': True, 'connected': connected}

    def status(self):
        return self._call('status')

    def connect(self):
        return self._call('connect')

    def cookies(self):
        return self._call('cookies')

    def download_context(self):
        return self._call('download_context')

    def disconnect(self):
        return self._call('disconnect')

    def shutdown(self):
        if self._thread and self._thread.is_alive():
            self._call('shutdown')


session = YouTubeSession(Path(__file__).parent / 'data' / 'youtube-session')
atexit.register(session.shutdown)
