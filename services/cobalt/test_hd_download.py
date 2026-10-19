"""Experimental HD-only validation. The installed working importer is unchanged.
No activation, browser login, account cookies or public provider instances.
"""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from importlib.metadata import version,PackageNotFoundError
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
WHEEL_NAME='bgutil_ytdlp_pot_provider-2.0.2-py3-none-any.whl'
WHEEL_URL='https://files.pythonhosted.org/packages/fa/ac/9da2e48eb58bbeb2c56739eed37c0e4c17b3c20c4c53a49c5a62c47a1148/'+WHEEL_NAME
WHEEL_SHA='4f488008d25a715837df79472aad06ea052d20e14ad3a02609bbb0fbd746b8be'
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


def install_plugin():
    try:
        if version('bgutil-ytdlp-pot-provider')=='2.0.2':return
        raise ValueError('PLUGIN_VERSION')
    except PackageNotFoundError:pass
    print('Preparando el complemento oficial BgUtils 2.0.2 en el entorno de la app...',flush=True)
    with urllib.request.urlopen(WHEEL_URL,timeout=30) as response:data=response.read(1000001)
    if len(data)>1000000 or hashlib.sha256(data).hexdigest()!=WHEEL_SHA:raise ValueError('PLUGIN_CHECKSUM')
    with tempfile.TemporaryDirectory() as tmp:
        wheel=Path(tmp)/WHEEL_NAME;wheel.write_bytes(data)
        subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps',str(wheel)],
            capture_output=True,text=True,timeout=120,check=True)


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


def download_one(ident,folder,base_url,details=None):
    import math
    import yt_dlp
    from youtube_import import javascript_options,MAX_BYTES
    from cobalt_import import _verify_media
    started=time.monotonic();last={};logger_codes=[]
    details={} if details is None else details
    details.update(phase="extract",warnings=logger_codes)
    class Logger:
        def debug(self,*args):pass
        def warning(self,text):
            # Preserve fixed categories only, never source URLs or tokens.
            lower=str(text).lower()
            for needle,label in [('po token','TOKEN_WARNING'),('javascript','JS_WARNING'),('403','HTTP_403')]:
                if needle in lower and label not in logger_codes:logger_codes.append(label)
        def error(self,text):self.warning(text)
    def progress(data):
        if time.monotonic()-started>7200:raise ValueError('DOWNLOAD_DEADLINE')
        downloaded=data.get('downloaded_bytes') or 0
        if downloaded>MAX_BYTES:raise ValueError('DOWNLOAD_SIZE')
        total=data.get('total_bytes') or data.get('total_bytes_estimate')
        if data.get('status')=='downloading' and total:
            percent=min(100,int(downloaded/total*100));step=percent//10
            track=str(data.get('info_dict',{}).get('format_id',''))[:30]
            if step>last.get(track,-1):
                print(f'{ident}: pista {track}, {percent}%',flush=True);last[track]=step
    def match(info,*,incomplete=False):
        duration=info.get('duration')
        if duration is not None and (type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=7200):return 'DURATION_LIMIT'
        if info.get('is_live') or info.get('live_status') in ('is_live','is_upcoming'):return 'LIVE_UNSUPPORTED'
    options={'noplaylist':True,'quiet':True,'logger':Logger(),'cachedir':False,
        'js_runtimes':javascript_options(),'socket_timeout':30,'retries':2,'fragment_retries':2,
        'concurrent_fragment_downloads':1,'http_chunk_size':1024*1024,'max_filesize':MAX_BYTES,
        'extractor_args':{'youtube':{'player_client':['mweb']},'youtubepot-bgutilhttp':{'base_url':[base_url]}},
        'format':'bestvideo[ext=mp4][vcodec^=avc1][height>=720][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height>=720][height<=1080]',
        'outtmpl':str(folder/'download.%(ext)s'),'merge_output_format':'mp4','match_filter':match,'progress_hooks':[progress]}
    with yt_dlp.YoutubeDL(options) as ydl:
        info=ydl.extract_info('https://www.youtube.com/watch?v='+ident,download=False)
        expected=info.get('duration') if isinstance(info,dict) else None
        if not info or info.get('id')!=ident or type(expected) not in (int,float) or not math.isfinite(expected) or not 0<expected<=7200:raise ValueError('SOURCE_METADATA')
        formats=info.get('requested_formats') or [info]
        announced=sum(item.get('filesize') or item.get('filesize_approx') or 0 for item in formats)
        if announced>MAX_BYTES:raise ValueError('DOWNLOAD_SIZE')
        details.update(phase='download',expected_duration=expected)
        print(f'{ident}: duración original {expected/60:.2f} minutos. Descargando completo...',flush=True)
        ydl.process_ie_result(info,download=True)
    path=folder/'download.mp4'
    details['phase']='verify'
    _verify_media(path,float(expected))
    measured=inspect_hd(path)
    return {'video_id':ident,'success':True,'expected_duration':expected,'bytes':path.stat().st_size,
        'path':str(path.relative_to(ROOT)),'warnings':logger_codes,**measured}


def inspect_hd(path):
    result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
        'stream=width,height,codec_name','-of','json',str(path)],capture_output=True,
        text=True,encoding='utf-8',errors='replace',timeout=30,check=True)
    streams=json.loads(result.stdout)['streams']
    video=streams[0];width=int(video['width']);height=int(video['height'])
    if min(width,height)<720:raise ValueError('HD_RESOLUTION_NOT_MET')
    return {'measured_width':width,'measured_height':height,'measured_codec':video.get('codec_name','')}


def main():
    from youtube_import import diagnose_error
    state=ROOT/'data/cobalt/hd-validation';state.mkdir(parents=True,exist_ok=True)
    report={'engine':'HD validation with lowercase provider route','full_downloads_verified':False,'results':[]}
    server=None
    try:
        print('Prueba HD de al menos 720p. No modifica el descargador instalado ni acepta 360p.',flush=True)
        install_plugin()
        report['versions']={'yt_dlp':version('yt-dlp'),'bgutil_plugin':version('bgutil-ytdlp-pot-provider')}
        server,base,counters=provider_server()
        status,payload=relay_request('/ping',{})
        if status!=200 or payload.get('version')!='2.0.2':raise ValueError('PROVIDER_VERSION')
        for ident in ('JCcuOv5y_9g','rcPWJKs5It4'):
            folder=state/(ident+'_'+uuid.uuid4().hex);folder.mkdir()
            details={}
            try:record=download_one(ident,folder,base,details)
            except Exception as error:
                code,_=diagnose_error(error)
                record={'video_id':ident,'success':False,'error_code':code,'error_type':type(error).__name__,**details}
                # Failed candidate outputs never appear in the verified folder.
                for file in folder.iterdir():
                    if file.is_file():file.unlink()
            report['results'].append(record)
            print(ident+(': HD COMPLETO Y VERIFICADO' if record['success'] else ': no se completó; revisaremos el informe.'),flush=True)
            if not record['success']:break
        report['provider_counters']=dict(counters)
        report['full_downloads_verified']=len(report['results'])==2 and all(r['success'] for r in report['results'])
    except Exception as error:
        report['setup_error']=type(error).__name__
        print('La prueba no se completó. Se guardará el informe sin mensajes privados.',flush=True)
    finally:
        if server:server.shutdown();server.server_close()
        (ROOT/'RESULTADO_DESCARGA_HD.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Envía RESULTADO_DESCARGA_HD.json. No repitas las actualizaciones anteriores.',flush=True)
    if report['full_downloads_verified'] and os.name=='nt':os.startfile(str(state))
    return 0 if report['full_downloads_verified'] else 1


if __name__=='__main__':raise SystemExit(main())
