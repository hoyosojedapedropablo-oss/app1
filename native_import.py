"""Verified public mweb imports using the configuration exercised on Windows."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from importlib.metadata import version
import json
import math
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
from cobalt_import import CobaltFailure,_verify_media

ROOT=Path(__file__).resolve().parent
CONFIG_PATH=ROOT/'data/youtube-native.json'


def configuration():
    if not CONFIG_PATH.exists():return None
    try:
        config=json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        if config.get('enabled') is not True:return None
        if config.get('verification_version')!=2 or config.get('enabled_modes')!=['fast']:raise ValueError()
        if config.get('minimum_height',0) not in (0,720):raise ValueError()
        return config
    except (OSError,ValueError,AttributeError):
        raise CobaltFailure('YT-SERVICIO-CONFIG','La configuración del descargador verificado no es válida.') from None


def cached_source(record,ident,minimum_height=0):
    try:
        if record.get('video_id')!=ident or record.get('success') is not True: return None
        duration=record['expected_duration']
        if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=7200:return None
        path=(ROOT/record['path']).resolve()
        proof_dir='hd-validation' if minimum_height else 'native-validation'
        path.relative_to((ROOT/'data/cobalt'/proof_dir).resolve())
        if path.name!='download.mp4' or path.stat().st_size!=record['bytes']:return None
        _verify_media(path,float(duration))
        if minimum_height:inspect_resolution(path,minimum_height)
        return path,float(duration)
    except (OSError,ValueError,KeyError,TypeError,CobaltFailure):return None


RELAY=r'''
const input=JSON.parse(await new Response(Deno.stdin.readable).text());
if(!['/ping','/get_pot'].includes(input.path))Deno.exit(2);
if(input.body?.disable_tls_verification)Deno.exit(2);
const response=await fetch('http://127.0.0.1:4416'+input.path,{
 method:input.path==='/ping'?'GET':'POST',headers:{'Content-Type':'application/json'},
 ...(input.path==='/get_pot'?{body:JSON.stringify(input.body)}:{}),signal:AbortSignal.timeout(50000)});
const text=await response.text();if(text.length>262144)Deno.exit(2);
console.log(JSON.stringify({status:response.status,body:JSON.parse(text)}));
'''


def relay_request(path,body):
    if path not in ('/ping','/get_pot') or not isinstance(body,dict) or body.get('disable_tls_verification'):
        raise ValueError('INVALID_PROVIDER_REQUEST')
    result=subprocess.run(['docker','exec','-i','clipstudio-download-pot-provider-1',
        'deno','eval',RELAY],input=json.dumps({'path':path,'body':body}),
        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,check=True)
    if len(result.stdout)>262144:raise ValueError('PROVIDER_RESPONSE_SIZE')
    response=json.loads(result.stdout)
    status=response.get('status')
    if type(status) is not int or not 200<=status<300:
        # Do not return raw upstream messages to the caller or logs.
        return 503,{'error':'PROVIDER_UNAVAILABLE'}
    payload=response.get('body')
    if not isinstance(payload,dict):raise ValueError('PROVIDER_RESPONSE')
    if path=='/ping':return 200,{'version':str(payload.get('version',''))[:30]}
    token=payload.get('poToken')
    if not isinstance(token,str) or not 100<=len(token)<=10000:return 503,{'error':'PROVIDER_UNAVAILABLE'}
    return 200,{'poToken':token}


def provider_server(relay=relay_request):
    secret=secrets.token_hex(24)
    counters={'requests':0,'tokens':0,'failures':0}
    lock=threading.BoundedSemaphore(2)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):self.handle_provider()
        def do_POST(self):self.handle_provider()
        def handle_provider(self):
            route=self.path.removeprefix('/'+secret)
            if (self.headers.get('Origin') or not self.path.startswith('/'+secret+'/') or
                (self.command,route) not in (('GET','/ping'),('POST','/get_pot'))):
                self.send_error(403);return
            acquired=False
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<=length<=262144:raise ValueError()
                self.connection.settimeout(10)
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError()
                body=json.loads(raw) if raw else {}
                if not isinstance(body,dict) or body.get('disable_tls_verification'):raise ValueError()
                acquired=lock.acquire(blocking=False)
                if not acquired:raise ValueError()
                counters['requests']+=1
                status,payload=relay(route,body)
                if route=='/get_pot':counters['tokens' if status==200 else 'failures']+=1
                data=json.dumps(payload).encode()
                self.send_response(status);self.send_header('Content-Type','application/json')
                self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except Exception:
                counters['failures']+=1
                try:self.send_error(503)
                except OSError:pass
            finally:
                if acquired:lock.release()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server,f'http://127.0.0.1:{server.server_port}/{secret}',counters


def inspect_resolution(path,minimum_height=720):
    try:
        result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
            'stream=width,height','-of','json',str(path)],capture_output=True,
            text=True,encoding='utf-8',errors='replace',timeout=30,check=True)
        video=json.loads(result.stdout)['streams'][0]
        width=int(video['width']);height=int(video['height'])
        if min(width,height)<minimum_height:raise ValueError()
        return {'video_width':width,'video_height':height}
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,IndexError,TypeError):
        raise CobaltFailure('YT-CALIDAD','El archivo no tiene la resolución HD mínima de 720p. No se aceptó una descarga de menor calidad.') from None


def reusable_job(job,config):
    if job.get('youtube_verification_version')!=2:return False
    minimum=config.get('minimum_height',0)
    if not minimum:return True
    meta=job.get('youtube') or {}
    width=meta.get('video_width');height=meta.get('video_height')
    return type(width) is int and type(height) is int and min(width,height)>=minimum


def download(url,folder,progress,mode='fast'):
    from youtube_import import canonical_url,javascript_options,MAX_BYTES
    url=canonical_url(url);ident=url.rsplit('=',1)[-1]
    config=configuration()
    if config is None:raise CobaltFailure('YT-SERVICIO-CONFIG','El método de descarga verificado no está habilitado.')
    if mode!='fast':raise CobaltFailure('YT-SERVICIO-CALIDAD','La calidad original sigue pendiente de validación. Elige Rápida; se descargará la mejor calidad disponible hasta 1080p.')
    minimum=config.get('minimum_height',0)
    folder=Path(folder);target=folder/'download.mp4';server=None;complete=False
    progress(0,'Consultando video de YouTube…',access_mode='none',download_engine='yt-dlp-mweb',verification_version=0)
    try:
        for record in config.get('verified_files',[]):
            progress(1,'Comprobando si el video completo ya está guardado…')
            cached=cached_source(record,ident,minimum)
            if cached:
                path,duration=cached
                shutil.copyfile(path,target)
                _verify_media(target,duration)
                measured=inspect_resolution(target,minimum) if minimum else {}
                progress(99,'Video completo recuperado y verificado.',access_mode='cached',duration=duration,
                    title='Video de YouTube · '+ident,thumbnail=f'https://i.ytimg.com/vi/{ident}/hqdefault.jpg',
                    verification_version=2,quality=(str(measured['video_height'])+'p · HD verificado') if measured else 'Archivo completo verificado',**measured)
                complete=True
                return target,ident+'.mp4'
        import yt_dlp
        if version('bgutil-ytdlp-pot-provider')!='2.0.2':raise CobaltFailure('YT-SERVICIO-CONFIG','El complemento de descarga requiere revisión de versión.')
        server,base_url,counters=provider_server()
        status,payload=relay_request('/ping',{})
        if status!=200 or payload.get('version')!='2.0.2':raise CobaltFailure('YT-SERVICIO-CONFIG','Abre Docker Desktop y comprueba que el servicio de descarga esté iniciado.')
        started=time.monotonic()
        class Logger:
            def debug(self,*args):pass
            def warning(self,*args):pass
            def error(self,*args):pass
        def hook(data):
            if time.monotonic()-started>7200:raise CobaltFailure('YT-TIEMPO','La descarga superó el tiempo de espera.')
            received=data.get('downloaded_bytes') or 0
            if received>MAX_BYTES:raise CobaltFailure('YT-VALIDACION','El video supera 12 GB.')
            total=data.get('total_bytes') or data.get('total_bytes_estimate')
            if data.get('status')=='downloading':
                value=min(90,int(received/total*90)) if total else 1
                progress(value,'Descargando video completo…',downloaded_bytes=received,total_bytes=total,
                    speed=data.get('speed'),eta=data.get('eta'))
        def match(info,*,incomplete=False):
            duration=info.get('duration')
            if duration is not None and (type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=7200):return 'La duración máxima es 120 minutos.'
            if info.get('is_live') or info.get('live_status') in ('is_live','is_upcoming'):return 'Los directos deben haber terminado antes de descargarlos.'
        options={'noplaylist':True,'quiet':True,'logger':Logger(),'cachedir':False,
            'js_runtimes':javascript_options(),'socket_timeout':30,'retries':2,'fragment_retries':2,
            'concurrent_fragment_downloads':1,'http_chunk_size':1024*1024,'max_filesize':MAX_BYTES,
            'extractor_args':{'youtube':{'player_client':['mweb']},'youtubepot-bgutilhttp':{'base_url':[base_url]}},
            'format':'bestvideo[ext=mp4][vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]',
            'outtmpl':str(folder/'download.%(ext)s'),'merge_output_format':'mp4','match_filter':match,'progress_hooks':[hook]}
        if minimum:
            options['format']=options['format'].replace('[height<=1080]','[height>=720][height<=1080]')
        with yt_dlp.YoutubeDL(options) as ydl:
            info=ydl.extract_info(url,download=False)
            expected=info.get('duration') if isinstance(info,dict) else None
            if not info or info.get('id')!=ident or type(expected) not in (int,float) or not math.isfinite(expected) or not 0<expected<=7200:
                raise CobaltFailure('YT-SERVICIO-RESPUESTA','No se pudo confirmar la identidad y duración del video original.')
            formats=info.get('requested_formats') or [info]
            announced=sum(item.get('filesize') or item.get('filesize_approx') or 0 for item in formats)
            if announced>MAX_BYTES:raise CobaltFailure('YT-VALIDACION','El video supera 12 GB.')
            height=info.get('height') or max((f.get('height') or 0 for f in formats),default=0)
            if minimum and height<minimum:raise CobaltFailure('YT-CALIDAD','No hay acceso a una pista de al menos 720p para este video. No se descargó en 360p.')
            progress(1,'Descargando video completo…',title=info.get('title') or 'Video de YouTube',
                channel=info.get('channel') or info.get('uploader') or '',duration=expected,
                thumbnail=f'https://i.ytimg.com/vi/{ident}/hqdefault.jpg',
                quality=f'{height}p · calidad disponible' if height else 'Mejor calidad disponible hasta 1080p')
            ydl.process_ie_result(info,download=True)
        progress(95,'Verificando audio, video y duración completa…')
        _verify_media(target,float(expected))
        measured=inspect_resolution(target,minimum) if minimum else {}
        progress(99,'Video completo verificado.',verification_version=2,
            **({'quality':str(measured['video_height'])+'p · HD verificado',**measured} if measured else {}))
        complete=True
        return target,(info.get('title') or 'Video de YouTube')+'.mp4'
    except Exception as error:
        if minimum and 'requested format is not available' in str(error).lower():
            raise CobaltFailure('YT-CALIDAD','YouTube no ofreció un formato HD accesible para este video. No se descargó en una calidad inferior.') from None
        raise
    finally:
        if server:server.shutdown();server.server_close()
        if not complete:
            for path in folder.glob('download.*'):
                if path.is_file():path.unlink(missing_ok=True)
