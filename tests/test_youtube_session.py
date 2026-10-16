import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import app as backend
from youtube_session import YouTubeSession, SessionUnavailable, youtube_cookies


def cookie(domain='.youtube.com', name='SID'):
    return dict(domain=domain, name=name, value='synthetic-private-value', path='/',
                secure=True, httpOnly=True, expires=2000000000)


class ManagedSessionTests(unittest.TestCase):
    def test_no_authorization_never_opens_browser_or_exposes_cookies(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=YouTubeSession(tmp)
            try:
                with patch.object(manager,'_open',side_effect=AssertionError('No consent')):
                    self.assertEqual(manager.status(),dict(authorized=False,connected=False))
                    with self.assertRaises(SessionUnavailable):manager.cookies()
            finally:manager.shutdown()

    def test_domain_filter_does_not_accept_lookalikes(self):
        cookies=[cookie(),cookie('youtube.com'),cookie('www.youtube.com'),
                 cookie('youtube.com.evil.example'),cookie('accounts.google.com')]
        self.assertEqual(len(youtube_cookies(cookies)),3)

    def test_status_only_exposes_booleans_but_download_gets_youtube_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=YouTubeSession(tmp);manager.marker.touch()
            context=SimpleNamespace(cookies=lambda *args:[cookie(),cookie('.example.com')])
            try:
                with patch.object(manager,'_open',return_value=context):
                    status=manager.status()
                    self.assertEqual(status,dict(authorized=True,connected=True))
                    self.assertNotIn('synthetic-private',str(status))
                    self.assertEqual(manager.cookies(),[cookie()])
            finally:manager.shutdown()

    def test_launch_uses_app_profile_and_never_regular_browser_profile(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp:
            manager=YouTubeSession(tmp);driver=MagicMock()
            with patch('playwright.sync_api.sync_playwright') as start,patch('youtube_session.find_browser',return_value='brave.exe'):
                start.return_value.start.return_value=driver
                manager._open(visible=True)
                args,kwargs=driver.chromium.launch_persistent_context.call_args
                self.assertEqual(args,(str(Path(tmp)/'profile'),))
                self.assertEqual(kwargs['executable_path'],'brave.exe')
                self.assertFalse(kwargs['headless'])
                self.assertNotIn('ignore_default_args',kwargs)
                manager._perform('shutdown')

    def test_resuming_connection_preserves_original_browser_identity(self):
        import json
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp:
            manager=YouTubeSession(tmp);manager.marker.write_text(json.dumps({'user_agent':'original-browser-agent'}))
            driver=MagicMock()
            with patch('playwright.sync_api.sync_playwright') as start,patch('youtube_session.find_browser',return_value='brave.exe'):
                start.return_value.start.return_value=driver
                manager._open()
                options=driver.chromium.launch_persistent_context.call_args.kwargs
                self.assertTrue(options['headless'])
                self.assertEqual(options['user_agent'],'original-browser-agent')
                manager._perform('shutdown')

    def test_session_errors_have_specific_safe_diagnostic(self):
        from youtube_import import diagnose_error
        code,message=diagnose_error(SessionUnavailable('synthetic-private-value'))
        self.assertEqual(code,'YT-CONEXION')
        self.assertNotIn('synthetic-private-value',message)

    def test_disconnect_removes_only_dedicated_profile_and_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manager=YouTubeSession(root/'connection')
            manager.directory.mkdir();manager.marker.touch()
            profile=manager.directory/'profile';profile.mkdir();(profile/'Cookies').write_text('synthetic')
            unrelated=root/'personal-profile';unrelated.mkdir()
            try:
                manager.disconnect()
                self.assertFalse(profile.exists());self.assertFalse(manager.marker.exists())
                self.assertTrue(unrelated.exists())
            finally:manager.shutdown()

    def test_disconnect_also_works_after_user_closed_connection_window(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp:
            manager=YouTubeSession(tmp);manager.marker.touch()
            (Path(tmp)/'profile').mkdir()
            context=MagicMock()
            context.clear_cookies.side_effect=RuntimeError('Target closed')
            context.close.side_effect=RuntimeError('Target closed')
            manager._context=context
            try:
                manager.disconnect()
                self.assertFalse(manager.marker.exists())
                self.assertFalse((Path(tmp)/'profile').exists())
            finally:manager.shutdown()

    def test_connection_endpoints_reject_remote_and_cross_origin_requests(self):
        paths=['/api/youtube-session','/api/youtube-session/connect','/api/youtube-session/disconnect']
        with patch('youtube_session.session.status',side_effect=AssertionError('Must reject before session access')):
            for path in paths:
                method='get' if path==paths[0] else 'post'
                for client in [TestClient(backend.app,client=('192.168.1.2',123)),TestClient(backend.app)]:
                    response=getattr(client,method)(path,headers={'Origin':'https://evil.example'})
                    self.assertEqual(response.status_code,403)
        with patch('youtube_session.session.status',return_value=dict(authorized=True,connected=True)):
            response=TestClient(backend.app).get(paths[0])
            self.assertEqual(response.json(),dict(authorized=True,connected=True))

    def test_downloader_uses_memory_jar_without_windows_cookie_decryption(self):
        import youtube_import
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);options={};jar=[]
            class YDL:
                cookiejar=SimpleNamespace(set_cookie=jar.append)
                def __init__(self,opts):options.update(opts)
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def extract_info(self,*args,**kwargs):return dict(title='Video',duration=20)
                def process_ie_result(self,info,**kwargs):
                    (folder/'download.mp4').write_bytes(b'video');return info
            with patch('youtube_session.session.download_context',return_value={'cookies':[cookie()],'user_agent':'browser-agent'}),patch('yt_dlp.YoutubeDL',YDL):
                youtube_import._download_attempt('https://www.youtube.com/watch?v=rcPWJKs5It4',folder,lambda *args,**kwargs:None,browser='managed')
            self.assertNotIn('cookiesfrombrowser',options)
            self.assertNotIn('cookiefile',options)
            self.assertFalse(options['cachedir'])
            self.assertEqual(options['user_agent'],'browser-agent')
            self.assertEqual(len(jar),1)
            self.assertEqual(jar[0].value,'synthetic-private-value')
            self.assertEqual(jar[0].domain,'.youtube.com')

    def test_public_success_does_not_launch_managed_browser(self):
        import youtube_import
        with patch('youtube_import._download_attempt',return_value=('file','name')) as attempt,patch('youtube_session.session.download_context',side_effect=AssertionError('Not needed')):
            youtube_import.download('url',None,lambda *a,**k:None,browser='managed')
        self.assertEqual(attempt.call_count,1)
        self.assertEqual(attempt.call_args.kwargs['browser'],'none')

    def test_public_rejection_can_recover_through_managed_session_once(self):
        import youtube_import
        with patch('youtube_import._download_attempt',side_effect=[RuntimeError('Sign in'),('file','name')]) as attempt:
            self.assertEqual(youtube_import.download('url',None,lambda *a,**k:None,browser='managed'),('file','name'))
        self.assertEqual([c.kwargs['browser'] for c in attempt.call_args_list],['none','managed'])
