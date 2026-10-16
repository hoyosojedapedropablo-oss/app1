import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import app as backend
from youtube_session import YouTubeSession, SessionUnavailable


class WithdrawnSessionTests(unittest.TestCase):
    def test_old_clients_cannot_launch_connection_or_import_using_it(self):
        client=TestClient(backend.app)
        with patch('youtube_session.session.connect',side_effect=AssertionError('Must not launch')),patch.object(backend.import_pool,'submit',side_effect=AssertionError('Must not import')):
            self.assertEqual(client.post('/api/youtube-session/connect').status_code,410)
            response=client.post('/api/youtube',json={'url':'https://youtu.be/rcPWJKs5It4','browser':'managed'})
            self.assertEqual(response.status_code,410)
            self.assertIn('Google',response.json()['detail'])

    def test_status_does_not_read_stored_cookie_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=YouTubeSession(tmp);manager.marker.touch()
            profile=Path(tmp)/'profile';profile.mkdir()
            (profile/'Cookies').write_text('synthetic-private-value')
            status=manager.status()
            self.assertFalse(status['connected'])
            self.assertTrue(status['cleanup_pending'])
            self.assertNotIn('synthetic-private-value',str(status))
            for operation in (manager.connect,manager.cookies,manager.download_context):
                with self.assertRaises(SessionUnavailable):operation()

    def test_cleanup_removes_only_app_owned_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manager=YouTubeSession(root/'connection')
            manager.directory.mkdir();manager.marker.touch()
            profile=manager.directory/'profile';profile.mkdir()
            (profile/'Cookies').write_text('synthetic')
            personal=root/'personal-profile';personal.mkdir()
            result=manager.disconnect()
            self.assertFalse(result['cleanup_pending'])
            self.assertFalse(manager.marker.exists())
            self.assertTrue(personal.exists())

    def test_locked_profile_is_reported_and_remains_available_for_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=YouTubeSession(tmp);manager.marker.touch()
            profile=Path(tmp)/'profile';profile.mkdir()
            with patch('youtube_session.shutil.rmtree',side_effect=PermissionError('locked')):
                with self.assertRaises(SessionUnavailable):manager.disconnect()
            self.assertFalse(manager.marker.exists())
            self.assertTrue(manager.status()['cleanup_pending'])
            manager.disconnect()
            self.assertFalse(profile.exists())

    def test_connection_endpoints_reject_remote_and_cross_origin_requests(self):
        paths=['/api/youtube-session','/api/youtube-session/connect','/api/youtube-session/disconnect']
        for path in paths:
            method='get' if path==paths[0] else 'post'
            for client in [TestClient(backend.app,client=('192.168.1.2',123)),TestClient(backend.app)]:
                self.assertEqual(getattr(client,method)(path,headers={'Origin':'https://evil.example'}).status_code,403)

    def test_internal_managed_attempt_cannot_reach_downloader(self):
        import youtube_import
        with patch('yt_dlp.YoutubeDL',side_effect=AssertionError('Must not download')):
            with self.assertRaises(SessionUnavailable) as caught:
                youtube_import._download_attempt('url',None,lambda *a,**k:None,browser='managed')
        code,message=youtube_import.diagnose_error(caught.exception)
        self.assertEqual(code,'YT-CONEXION')
        self.assertNotIn('inicia sesión',message)

    def test_public_remains_default_for_new_requests(self):
        self.assertEqual(backend.YouTubeInput(url='https://youtu.be/rcPWJKs5It4').browser,'none')
