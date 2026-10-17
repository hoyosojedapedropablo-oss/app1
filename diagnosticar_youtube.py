"""Public metadata-only A/B probe. Never reads browser sessions or raw logs."""
import argparse
import contextlib
import io
import json
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

VIDEOS = ('JCcuOv5y_9g', 'rcPWJKs5It4')


class SafeLogger:
    def __init__(self):
        self.phase = 'inicio'

    def debug(self, message):
        if 'Downloading webpage' in message:
            self.phase = 'pagina'
        elif 'player API JSON' in message:
            self.phase = 'reproductor'
        elif 'm3u8 information' in message or 'MPD manifest' in message:
            self.phase = 'formatos'

    def warning(self, *args):
        pass

    def error(self, *args):
        pass


def probe(ident, profile):
    import yt_dlp
    from youtube_import import diagnose_error, javascript_options
    logger = SafeLogger()
    options = dict(noplaylist=True, quiet=True, logger=logger, cachedir=False,
                   socket_timeout=10, retries=0, extractor_retries=0,
                   format='bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best')
    started = time.monotonic()
    result = dict(video_id=ident, profile=profile, download_validated=False)
    # Do not expose signed media URLs, headers, proxy values or provider logs.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            if profile == 'actual':
                options.update(js_runtimes=javascript_options(),
                               concurrent_fragment_downloads=8, http_chunk_size=10*1024*1024,
                               format='bestvideo[ext=mp4][vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/bestvideo[height<=1080]+bestaudio/best[height<=1080]')
            with yt_dlp.YoutubeDL(options) as engine:
                info = engine.extract_info('https://www.youtube.com/watch?v='+ident, download=False)
            result.update(metadata_ok=bool(info), error_code=None if info else 'YT-SIN-METADATOS',
                          formats=len(info.get('formats', [])) if info else 0)
        except Exception as error:
            result.update(metadata_ok=False, error_code=diagnose_error(error)[0])
    result.update(phase=logger.phase, seconds=round(time.monotonic()-started, 1))
    return result


def run_probe(ident, profile):
    base = dict(video_id=ident, profile=profile, metadata_ok=False, download_validated=False)
    try:
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--probe', ident,
                                '--profile', profile], capture_output=True, text=True,
                               encoding='utf-8', timeout=35)
        if child.returncode:
            return dict(base, error_code='DIAGNOSTICO-PROCESO')
        return json.loads(child.stdout)
    except subprocess.TimeoutExpired:
        return dict(base, error_code='YT-TIEMPO', phase='limite_global')
    except (OSError, ValueError):
        return dict(base, error_code='DIAGNOSTICO-PROCESO')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', choices=VIDEOS)
    parser.add_argument('--profile', choices=('anterior', 'actual'), default='actual')
    args = parser.parse_args()
    if args.probe:
        print(json.dumps(probe(args.probe, args.profile)))
        return
    dependencies = {}
    for name in ('yt-dlp', 'yt-dlp-ejs', 'deno'):
        try: dependencies[name] = version(name)
        except PackageNotFoundError: dependencies[name] = 'no instalado'
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                  system=platform.system(), python=platform.python_version(),
                  dependencies=dependencies, results=[],
                  scope='Solo metadatos publicos; no valida descarga ni reproduce la version historica de las dependencias.')
    print('Prueba publica: sin leer sesiones, instalar componentes ni cambiar la app.')
    print('Son cuatro consultas. Cada una tiene un limite de 35 segundos.')
    for ident in VIDEOS:
        for profile in ('anterior', 'actual'):
            print('Comprobando '+ident+' / '+profile+'...', flush=True)
            result = run_probe(ident, profile)
            report['results'].append(result)
            print('  '+('Metadatos recibidos (descarga aun no validada)' if result['metadata_ok'] else result['error_code']))
    path = Path(__file__).resolve().parent / ('DIAGNOSTICO_YOUTUBE_'+uuid.uuid4().hex[:8]+'.json')
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='utf-8')
    print('Informe guardado: '+path.name)
    print('Puedes compartir ese informe. No contiene cookies, contrasenas ni registros originales del proveedor.')


if __name__ == '__main__':
    main()
