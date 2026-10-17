"""Client for an operator-owned Cobalt service. No public instance discovery."""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx

MAX_BYTES = 12 * 1024**3
CONFIG_PATH = Path(__file__).parent/'data'/'cobalt'/'client.json'


class CobaltFailure(Exception):
    def __init__(self, code, message):
        self.code = code
        self.safe_message = message
        super().__init__(message)


def configuration():
    endpoint = os.environ.get('CLIP_COBALT_URL', '').strip()
    key = os.environ.get('CLIP_COBALT_KEY', '')
    if not endpoint:
        if not CONFIG_PATH.exists():
            return None
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
            if saved.get('enabled') is not True:
                return None
            endpoint, key = saved['endpoint'], saved['api_key']
            if not isinstance(endpoint,str) or not isinstance(key,str):
                raise ValueError()
        except (OSError, ValueError, KeyError, AttributeError):
            raise CobaltFailure('YT-SERVICIO-CONFIG', 'La configuración local del servicio no es válida.') from None
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
        local = parsed.hostname in ('127.0.0.1', 'localhost', '::1')
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            (parsed.scheme != 'https' and not local)):
            raise ValueError()
        if parsed.hostname in ('api.cobalt.tools', 'cobalt.tools'):
            raise ValueError()  # No permission to use the hosted public instance.
    except ValueError:
        raise CobaltFailure('YT-SERVICIO-CONFIG', 'La dirección del servicio de descarga no es válida. El administrador debe configurar una instancia propia con HTTPS (o localhost para pruebas).') from None
    if not local and not key:
        raise CobaltFailure('YT-SERVICIO-CONFIG', 'Falta configurar la clave del servicio de descarga en el servidor de Clip Studio.')
    return endpoint.rstrip('/')+'/', key


def _origin(parsed):
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)


def _tunnel_url(value, endpoint):
    try:
        if not isinstance(value,str):
            raise ValueError()
        parsed, base = urlsplit(value), urlsplit(endpoint)
        if (parsed.username or parsed.password or parsed.fragment or
            _origin(parsed) != _origin(base) or
            parsed.path != base.path.rstrip('/')+'/tunnel'):
            raise ValueError()
    except (ValueError, TypeError):
        raise CobaltFailure('YT-SERVICIO-RESPUESTA', 'El servicio no entregó un túnel de descarga válido de su propia instancia.') from None
    return value


def _check_http(response):
    if response.status_code in (401, 403):
        raise CobaltFailure('YT-SERVICIO-AUTH', 'El servicio de descarga rechazó la conexión. El administrador debe revisar su clave y permisos.')
    if response.status_code == 429:
        raise CobaltFailure('YT-LIMITE', 'El servicio alcanzó su límite temporal de descargas. Inténtalo más tarde.')
    if not 200 <= response.status_code < 300:
        raise CobaltFailure('YT-SERVICIO', 'El servicio de descarga no pudo completar la solicitud.')


def _read_json(response):
    # Cobalt uses HTTP 400 for structured extraction errors.
    if response.status_code != 400:
        _check_http(response)
    data = bytearray()
    for chunk in response.iter_bytes(chunk_size=8192):
        data.extend(chunk)
        if len(data) > 65536:
            raise CobaltFailure('YT-SERVICIO-RESPUESTA', 'La respuesta del servicio no tiene el formato esperado.')
    try:
        payload = json.loads(data)
        if not isinstance(payload, dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise CobaltFailure('YT-SERVICIO-RESPUESTA', 'La respuesta del servicio no tiene el formato esperado.') from None
    if payload.get('status') == 'error':
        code = payload.get('error', {}).get('code') if isinstance(payload.get('error'), dict) else None
        if isinstance(code, str):
            code = code.removeprefix('error.api.')
        if code == 'content.too_long':
            raise CobaltFailure('YT-VALIDACION', 'La duración máxima es 120 minutos.')
        if code in ('content.video.private', 'content.video.age', 'content.video.unavailable', 'content.video.region', 'content.video.live'):
            raise CobaltFailure('YT-RESTRINGIDO', 'El servicio no puede descargar este video por su disponibilidad o restricciones de acceso.')
        if code in ('youtube.no_session_tokens', 'youtube.token_expired'):
            raise CobaltFailure('YT-SERVICIO-TOKEN', 'El servicio no dispone de una atestación anónima válida. Requiere revisión del administrador.')
        if code == 'youtube.login':
            raise CobaltFailure('YT-SERVICIO-ACCESO', 'YouTube rechazó el acceso del servicio a este video. La descarga no se completó.')
        raise CobaltFailure('YT-SERVICIO', 'El servicio de descarga no pudo obtener este video.')
    _check_http(response)
    return payload


def download(url, folder, progress, mode='fast'):
    from youtube_import import canonical_url
    url = canonical_url(url)
    config = configuration()
    if config is None:
        raise CobaltFailure('YT-SERVICIO-CONFIG', 'El servicio de descarga no está configurado.')
    if mode not in ('fast', 'original'):
        raise ValueError('Calidad de descarga inválida.')
    endpoint, key = config
    headers = {'Accept': 'application/json'}
    if key:
        headers['Authorization'] = 'Api-Key '+key
    request = dict(url=url, videoQuality='1080' if mode == 'fast' else 'max',
                   youtubeVideoCodec='h264' if mode == 'fast' else 'vp9',
                   youtubeVideoContainer='mp4', downloadMode='auto',
                   alwaysProxy=True, localProcessing='disabled')
    target = Path(folder)/'download.mp4'
    complete = False
    started = time.monotonic()
    progress(0, 'Preparando el video en el servicio de descarga…', access_mode='service', download_engine='cobalt')
    try:
        # Trust the inherited proxy/CA. Never forward API authentication to the tunnel.
        with httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=False) as client:
            with client.stream('POST', endpoint, json=request, headers=headers) as response:
                payload = _read_json(response)
            if payload.get('status') != 'tunnel':
                raise CobaltFailure('YT-SERVICIO-RESPUESTA', 'El servicio debe entregar el video completo mediante su túnel, con audio incluido.')
            tunnel = _tunnel_url(payload.get('url'), endpoint)
            name = re.split(r'[/\\]', str(payload.get('filename') or 'Video de YouTube.mp4'))[-1]
            name = ''.join(c for c in name if c.isprintable()).strip()[:180] or 'Video de YouTube.mp4'
            progress(1, 'Recibiendo el video preparado…', title=Path(name).stem,
                     quality='Hasta 1080p' if mode == 'fast' else 'Máxima disponible')
            with client.stream('GET', tunnel, headers={'Accept-Encoding':'identity'}) as response:
                _check_http(response)
                if any(t in response.headers.get('Content-Type', '').lower() for t in ('text/', 'json')):
                    raise CobaltFailure('YT-SERVICIO-RESPUESTA', 'El túnel devolvió una respuesta que no es un archivo de video.')
                try:
                    total = int(response.headers.get('Content-Length', 0))
                    if total < 0:
                        raise ValueError()
                except ValueError:
                    raise CobaltFailure('YT-SERVICIO-RESPUESTA', 'El servicio indicó un tamaño de archivo inválido.') from None
                if total > MAX_BYTES:
                    raise CobaltFailure('YT-VALIDACION', 'El video supera 12 GB.')
                received = 0
                with target.open('wb') as output:
                    for chunk in response.iter_bytes(chunk_size=1024*1024):
                        elapsed = time.monotonic()-started
                        if elapsed > 7200:
                            raise CobaltFailure('YT-TIEMPO', 'La descarga superó el tiempo de espera.')
                        received += len(chunk)
                        if received > MAX_BYTES:
                            raise CobaltFailure('YT-VALIDACION', 'El video supera 12 GB.')
                        output.write(chunk)
                        speed = received/max(elapsed, .001)
                        progress(min(95, int(received/total*95)) if total else 0,
                                 'Descargando video…', downloaded_bytes=received, total_bytes=total,
                                 speed=speed, eta=max(0, (total-received)/speed) if total else None)
                if not received or (total and received != total):
                    raise CobaltFailure('YT-SERVICIO-RESPUESTA', 'El archivo recibido está vacío o incompleto.')
        complete = True
        return target, name
    except CobaltFailure:
        raise
    except httpx.TimeoutException:
        raise CobaltFailure('YT-TIEMPO', 'El servicio de descarga agotó el tiempo de espera.') from None
    except httpx.HTTPError:
        raise CobaltFailure('YT-SERVICIO-RED', 'No se pudo recibir el video desde el servicio de descarga.') from None
    except OSError as error:
        code = 'YT-DISCO' if error.errno == 28 else 'YT-SERVICIO-ARCHIVO'
        raise CobaltFailure(code, 'No se pudo guardar el video. Revisa el espacio y los permisos de la carpeta de datos.') from None
    finally:
        if not complete:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
