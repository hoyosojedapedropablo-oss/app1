import json
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import diagnosticar_youtube as diagnostic


class DiagnosticTests(unittest.TestCase):
    def test_public_probes_never_use_sessions_download_or_expose_media_urls(self):
        options=[];calls=[]
        class Engine:
            def __init__(self, opts):options.append(opts)
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def extract_info(self,url,download):
                calls.append(download)
                print('sensitive-provider-output')
                return dict(formats=[{'url':'https://media.invalid/?token=private'}])
        with patch('yt_dlp.YoutubeDL',Engine),patch('youtube_import.javascript_options',return_value={'deno':{}}):
            reports=[diagnostic.probe('JCcuOv5y_9g',p) for p in ('anterior','actual')]
        self.assertEqual(calls,[False,False])
        for opts in options:
            self.assertNotIn('cookiesfrombrowser',opts)
            self.assertNotIn('cookiefile',opts)
            self.assertFalse(opts['cachedir'])
        self.assertNotIn('js_runtimes',options[0])
        self.assertIn('js_runtimes',options[1])
        self.assertNotIn('private',json.dumps(reports))
        self.assertTrue(all(r['metadata_ok'] and not r['download_validated'] for r in reports))

    def test_errors_are_categorized_without_provider_content(self):
        with patch('yt_dlp.YoutubeDL',side_effect=RuntimeError('Sign in https://host/?token=private')):
            report=diagnostic.probe('JCcuOv5y_9g','anterior')
        self.assertEqual(report['error_code'],'YT-SESION')
        self.assertNotIn('private',json.dumps(report))

    def test_subprocess_timeout_and_stderr_are_not_leaked(self):
        with patch('subprocess.run',side_effect=subprocess.TimeoutExpired('private-command',35)):
            self.assertEqual(diagnostic.run_probe('JCcuOv5y_9g','actual')['error_code'],'YT-TIEMPO')
        with patch('subprocess.run',return_value=SimpleNamespace(returncode=1,stderr='private',stdout='private')):
            report=diagnostic.run_probe('JCcuOv5y_9g','actual')
        self.assertNotIn('private',json.dumps(report))

    def test_logger_only_keeps_fixed_stage_names(self):
        logger=diagnostic.SafeLogger()
        logger.debug('Downloading webpage private-token')
        self.assertEqual(logger.phase,'pagina')
        logger.warning('private-token')
        logger.error('private-token')
        self.assertNotIn('private-token',str(vars(logger)))
