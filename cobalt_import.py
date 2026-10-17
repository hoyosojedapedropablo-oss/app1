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


def allowed_modes():
    # Environment-configured services are explicitly managed by their operator.
    if os.environ.get('CLIP_COBALT_URL','').strip():
        return {'fast','original'}
    try:
        saved=json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        modes=saved.get('enabled_modes',['fast','original'])
        if not isinstance(modes,list) or not modes or any(mode not in ('fast','original') for mode in modes):
            raise ValueError()
        return set(modes)
    except (OSError,ValueError,AttributeError):
        raise CobaltFailure('YT-SERVICIO-CONFIG','La configuración de calidades del servicio no es válida.') from None


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


def _source_metadata(payload,url):
    from math import isfinite
    ident=url.rsplit('=',1)[-1]
    duration=payload.get('expected_duration')
    size=payload.get('expected_media_bytes')
    if (payload.get('source_video_id')!=ident or type(duration) not in (int,float) or
        not isfinite(duration) or not 0<duration<=7200 or type(size) is not int or not 0<size<=MAX_BYTES):
        raise CobaltFailure('YT-SERVICIO-RESPUESTA','El servicio no confirmó la identidad, duración y tamaño del video original. No se aceptará una descarga sin esos datos.')
    return float(duration),size


def _receive_track(client,url,path,progress,state,expected_bytes,started):
    with client.stream('GET',url,headers={'Accept-Encoding':'identity'}) as response:
        _check_http(response)
        if any(t in response.headers.get('content-type','').lower() for t in ('text/','json')):
            raise CobaltFailure('YT-SERVICIO-RESPUESTA','La pista recibida no es un archivo de audio o video.')
        try:
            length=int(response.headers.get('content-length',0))
        except ValueError:length=0
        if length<=0:
            raise CobaltFailure('YT-SERVICIO-RESPUESTA','El servicio no confirmó el tamaño completo de una pista.')
        if state['bytes']+length>expected_bytes or state['bytes']+length>MAX_BYTES:
            raise CobaltFailure('YT-VALIDACION','El tamaño de las pistas no coincide con el original o supera 12 GB.')
        received=0
        with path.open('wb') as output:
            for chunk in response.iter_bytes(chunk_size=1024*1024):
                elapsed=time.monotonic()-started
                if elapsed>7200:raise CobaltFailure('YT-TIEMPO','La descarga superó el tiempo de espera.')
                received+=len(chunk)
                if received>length:raise CobaltFailure('YT-INCOMPLETO','La pista recibida no coincide con el tamaño anunciado.')
                output.write(chunk)
                total=state['bytes']+received
                progress(max(1,min(85,int(total/expected_bytes*85))),'Descargando las pistas completas…',
                    downloaded_bytes=total,total_bytes=expected_bytes,speed=total/max(elapsed,.001))
        if received!=length:
            raise CobaltFailure('YT-INCOMPLETO','Una pista se recibió incompleta. El archivo no se aceptó como video completo.')
        state['bytes']+=received


def _merge_tracks(tracks,target):
    import subprocess
    try:
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(tracks[0]),'-i',str(tracks[1]),
            '-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart',str(target)],
            capture_output=True,timeout=3600,check=True)
    except (OSError,subprocess.SubprocessError):
        raise CobaltFailure('YT-MEDIA','No se pudieron unir las pistas completas de audio y video.') from None


def _verify_media(path,expected_duration):
    import subprocess
    from math import isfinite
    try:
        process=subprocess.run(['ffprobe','-v','error','-count_packets','-show_format','-show_streams','-of','json',str(path)],
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300,check=True)
        media=json.loads(process.stdout)
        video=next(s for s in media['streams'] if s.get('codec_type')=='video')
        audio=next(s for s in media['streams'] if s.get('codec_type')=='audio')
        durations=[float(media['format']['duration']),float(video['duration']),float(audio['duration'])]
        tolerance=max(2.,expected_duration*.005)
        if (any(int(stream.get('nb_read_packets',0))<=0 for stream in (video,audio)) or
            any(not isfinite(value) or value<=0 or abs(value-expected_duration)>tolerance for value in durations)):
            raise ValueError()
        if not 0<path.stat().st_size<=MAX_BYTES:raise ValueError()
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,StopIteration,TypeError):
        raise CobaltFailure('YT-INCOMPLETO','El archivo no contiene audio y video completos con la duración original. La descarga fue descartada.') from None


def download(url,folder,progress,mode='fast'):
    from youtube_import import canonical_url
    url=canonical_url(url)
    config=configuration()
    if config is None:raise CobaltFailure('YT-SERVICIO-CONFIG','El servicio de descarga no está configurado.')
    if mode not in ('fast','original'):raise ValueError('Calidad de descarga inválida.')
    if mode not in allowed_modes():
        raise CobaltFailure('YT-SERVICIO-CALIDAD','Esta calidad no está habilitada. Elige Rápida · hasta 1080p; la calidad original sigue pendiente de validación.')
    endpoint,key=config
    headers={'Accept':'application/json'}
    if key:headers['Authorization']='Api-Key '+key
    request=dict(url=url,videoQuality='1080' if mode=='fast' else 'max',
        youtubeVideoCodec='h264' if mode=='fast' else 'vp9',youtubeVideoContainer='mp4',
        downloadMode='auto',alwaysProxy=True,localProcessing='forced')
    target=Path(folder)/'download.mp4'
    tracks=[Path(folder)/('track-'+str(i)+'.bin') for i in range(2)]
    complete=False
    started=time.monotonic()
    progress(0,'Preparando el video en el servicio de descarga…',access_mode='service',download_engine='cobalt')
    try:
        with httpx.Client(timeout=httpx.Timeout(60,connect=10),follow_redirects=False) as client:
            with client.stream('POST',endpoint,json=request,headers=headers) as response:payload=_read_json(response)
            duration,expected_bytes=_source_metadata(payload,url)
            tunnels=payload.get('tunnel')
            if (payload.get('status')!='local-processing' or payload.get('type')!='merge' or payload.get('isHLS') or
                not isinstance(tunnels,list) or len(tunnels)!=2):
                raise CobaltFailure('YT-SERVICIO-RESPUESTA','El servicio debe entregar las pistas completas de audio y video por separado.')
            tunnels=[_tunnel_url(value,endpoint) for value in tunnels]
            output=payload.get('output')
            name=output.get('filename') if isinstance(output,dict) else None
            name=re.split(r'[/\\]',str(name or 'Video de YouTube.mp4'))[-1]
            name=''.join(c for c in name if c.isprintable()).strip()[:180] or 'Video de YouTube.mp4'
            progress(1,'Recibiendo audio y video completos…',title=Path(name).stem,
                quality='Hasta 1080p' if mode=='fast' else 'Máxima disponible',source_duration=duration,source_video_id=url.rsplit('=',1)[-1],source_expected_bytes=expected_bytes)
            state={'bytes':0}
            for tunnel,path in zip(tunnels,tracks):_receive_track(client,tunnel,path,progress,state,expected_bytes,started)
            if state['bytes']!=expected_bytes:
                raise CobaltFailure('YT-INCOMPLETO','Las pistas recibidas no coinciden con el tamaño del video original.')
        progress(90,'Uniendo las pistas completas…')
        _merge_tracks(tracks,target)
        progress(95,'Comprobando duración completa de audio y video…')
        _verify_media(target,duration)
        complete=True
        progress(98,'Video completo verificado.',source_duration=duration,verification_version=2)
        return target,name
    except CobaltFailure:raise
    except httpx.TimeoutException:
        raise CobaltFailure('YT-TIEMPO','El servicio de descarga agotó el tiempo de espera.') from None
    except httpx.HTTPError:
        raise CobaltFailure('YT-SERVICIO-RED','La transferencia de una pista se interrumpió. No se aceptó un archivo incompleto.') from None
    except OSError as error:
        code='YT-DISCO' if error.errno==28 else 'YT-SERVICIO-ARCHIVO'
        raise CobaltFailure(code,'No se pudo guardar el video. Revisa espacio y permisos de la carpeta de datos.') from None
    finally:
        for path in tracks+([] if complete else [target]):
            try:path.unlink(missing_ok=True)
            except OSError:pass
