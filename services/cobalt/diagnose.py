"""Bounded media-path diagnostic; never records keys, tokens or tunnel URLs."""
import json
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import httpx
from cobalt_import import CobaltFailure, _read_json, _tunnel_url


def sample(client, url, endpoint):
    url = _tunnel_url(url, endpoint)
    with client.stream('GET', url, headers={'Accept-Encoding':'identity'}) as response:
        result = {'http_status':response.status_code,
                  'content_type':response.headers.get('content-type','')[:80],
                  'sample_bytes':0}
        for header in ('content-length','estimated-content-length'):
            value = response.headers.get(header)
            if value and value.isdigit():result[header.replace('-','_')]=int(value)
        # A prefix establishes whether media starts flowing, not completeness.
        for chunk in response.iter_bytes(chunk_size=65536):
            result['sample_bytes'] += len(chunk)
            if result['sample_bytes'] >= 65536:break
        return result


def inspect_paths(client, endpoint, key):
    results = []
    request = {'url':'https://www.youtube.com/watch?v=JCcuOv5y_9g',
               'videoQuality':'1080','youtubeVideoCodec':'h264',
               'youtubeVideoContainer':'mp4','downloadMode':'auto','alwaysProxy':True}
    for processing in ('disabled','forced'):
        record = {'processing':processing}
        try:
            with client.stream('POST',endpoint,json={**request,'localProcessing':processing},
                               headers={'Accept':'application/json','Authorization':'Api-Key '+key}) as response:
                payload = _read_json(response)
            for field in ('expected_duration','expected_media_bytes'):
                value=payload.get(field)
                if type(value) in (int,float) and 0<value<=12*1024**3:record[field]=value
            status = payload.get('status')
            record['response_type'] = status if status in ('tunnel','local-processing','redirect','picker') else 'unexpected'
            if status == 'tunnel':
                record['streams'] = [sample(client,payload.get('url'),endpoint)]
            elif status == 'local-processing':
                tunnels = payload.get('tunnel')
                if not isinstance(tunnels,list) or not 1 <= len(tunnels) <= 3:
                    raise CobaltFailure('YT-SERVICIO-RESPUESTA','Cantidad de pistas no válida.')
                record['streams'] = [sample(client,url,endpoint) for url in tunnels]
        except CobaltFailure as error:
            record['error_code']=error.code
            record['message']=error.safe_message
        except httpx.HTTPError:
            record['error_code']='DIAGNOSTICO-RED-TIEMPO'
        except Exception:
            record['error_code']='DIAGNOSTICO-FALLO'
        results.append(record)
    return results



UPSTREAM_PROBE = r"""
// Runs in the pinned Cobalt container; never emits media URLs or provider errors.
console.log = console.warn = console.error = () => {};
const report = {schema:1, client:"IOS", isolated_extractor:true, shared_session_loaded:false, tracks:[]};
let finished = false;
function finish() {
  if (finished) return;
  finished = true;
  process.stdout.write('CLIP_PROBE_JSON:'+JSON.stringify(report)+'\n');
  process.exit(0);
}
setTimeout(()=>{report.deadline_reached=true;finish();},95000).unref();
try {
  const {fetch,EnvHttpProxyAgent} = await import('undici');
  const {default:extract} = await import('./src/processing/services/youtube.js');
  const {getHeaders} = await import('./src/stream/shared.js');
  const dispatcher = new EnvHttpProxyAgent();
  const media = await extract({id:'JCcuOv5y_9g',quality:'1080',codec:'h264',container:'mp4',isAudioOnly:false,youtubeHLS:false,dispatcher});
  const expected=media.originalRequest?.expectedDuration;
  if(typeof expected==='number' && Number.isFinite(expected) && expected>0 && expected<=7200)report.source_duration=expected;
  if (media.error) {
    report.extraction_error = typeof media.error==='string' && /^[a-z0-9_.]{1,100}$/.test(media.error) ? media.error : 'EXTRACTION_FAILED';
  } else if (!Array.isArray(media.urls) || media.urls.length !== 2) {
    report.extraction_error = 'UNEXPECTED_TRACKS';
  } else {
    for (const [index, value] of media.urls.entries()) {
      const track = {kind:index===0?'video':'audio'};
      report.tracks.push(track);
      const url = new URL(value);
      if (url.protocol!=='https:' || !(url.hostname==='googlevideo.com' || url.hostname.endsWith('.googlevideo.com')) || url.username || url.password) {
        track.error='UNEXPECTED_MEDIA_HOST';continue;
      }
      for (const method of ['HEAD','GET_ONE','GET']) {
        const result={};track[method.toLowerCase()]=result;
        try {
          const response = await fetch(url, {method:method==='HEAD'?'HEAD':'GET',dispatcher,redirect:'follow',
            headers:{...getHeaders('youtube'),...(method!=='HEAD'?{Range:method==='GET_ONE'?'bytes=0-0':'bytes=0-65535'}:{})},
            signal:AbortSignal.timeout(20000)});
          result.http_status=response.status;
          const range=response.headers.get('content-range');
          if(range && /^bytes [0-9]+-[0-9]+\/[0-9]+$/.test(range))result.content_range=range;
          const length=response.headers.get('content-length');
          if (length && /^\d+$/.test(length))result.content_length=Number(length);
          const type=response.headers.get('content-type')||'';
          result.content_category=type.startsWith('video/')?'video':type.startsWith('audio/')?'audio':type.startsWith('text/')?'text':type.includes('json')?'json':'other';
          if (method!=='HEAD') {
            result.sample_bytes=0;
            if (response.ok && response.body) {
              const reader=response.body.getReader();
              try {
                while(result.sample_bytes<65536) {
                  const {done,value:chunk}=await reader.read();if(done)break;
                  result.sample_bytes+=Math.min(chunk.byteLength,65536-result.sample_bytes);
                }
              } finally {await reader.cancel().catch(()=>{});}
            } else await response.body?.cancel();
          } else await response.body?.cancel();
        } catch {result.error='NETWORK_OR_TIMEOUT';}
      }
    }
    // Exercise the installed stream code with the same URLs used above.
    try {
      for(const value of media.urls){const u=new URL(value);if(u.protocol!=='https:'||!(u.hostname==='googlevideo.com'||u.hostname.endsWith('.googlevideo.com'))||u.username||u.password)throw Error('UNEXPECTED_MEDIA_HOST');}
      const http=await import('node:http');
      const {channel}=await import('node:diagnostics_channel');
      const {Readable}=await import('node:stream');
      const {internalStream}=await import('./src/stream/internal.js');
      const events=[];report.stream_events=events;
      const category=error=>/maxRedirections/.test(String(error?.message))?'REDIRECT_OPTION':
        /abort/i.test(String(error?.message))?'ABORTED':
        /^UND_ERR_[A-Z_]+$/.test(error?.code||'')?error.code:'STREAM_ERROR';
      const safeRequest=request=>{
        try {
          const host=new URL(String(request.origin)).hostname;
          return host==='googlevideo.com'||host.endsWith('.googlevideo.com');
        } catch {return false;}
      };
      const safeRange=request=>{
        const headers=request.headers;
        let value='';
        if(typeof headers==='string')value=/^range:\s*(bytes=[0-9]+-[0-9]*)\s*$/im.exec(headers)?.[1]||'';
        else if(Array.isArray(headers))for(let i=0;i<headers.length-1;i+=2)if(String(headers[i]).toLowerCase()==='range')value=String(headers[i+1]);
        return /^bytes=[0-9]+-[0-9]*$/.test(value)?{range:value}:{};
      };
      channel('undici:request:headers').subscribe(({request,response})=>{
        if(safeRequest(request)&&events.length<24)events.push({method:request.method,status:response.statusCode,...safeRange(request)});
      });
      channel('undici:request:error').subscribe(({request,error})=>{
        if(safeRequest(request)&&events.length<24)events.push({method:request.method,error:category(error),...safeRange(request)});
      });
      const originalFrom=Readable.from;
      Readable.from=(...args)=>{
        const readable=originalFrom(...args);
        readable.on('error',error=>{if(events.length<24)events.push({stage:'read_chunks',error:category(error)});});
        return readable;
      };
      const server=http.createServer((req,res)=>{
        const index=req.url==='/video'?0:1;
        const streamInfo={url:media.urls[index],service:'youtube',controller:new AbortController(),dispatcher};
        internalStream(streamInfo,res);
      });
      await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
      report.installed_pipeline=[];
      try {
        for(const kind of ['video','audio']) {
          const result={kind,sample_bytes:0};report.installed_pipeline.push(result);
          try {
            const response=await fetch(`http://127.0.0.1:${server.address().port}/${kind}`,{signal:AbortSignal.timeout(20000)});
            result.http_status=response.status;
            const reader=response.body.getReader();
            try {
              while(result.sample_bytes<65536){const {done,value}=await reader.read();if(done)break;result.sample_bytes+=Math.min(value.length,65536-result.sample_bytes);}
            } finally {await reader.cancel().catch(()=>{});}
          } catch(error){result.error=category(error);}
        }
      } finally {server.closeAllConnections();server.close();Readable.from=originalFrom;}
    } catch {report.pipeline_error='PIPELINE_PROBE_UNAVAILABLE';}
  }
} catch {report.error='PROBE_FAILED';}
finish();
"""

def upstream_probe():
    try:
        process = subprocess.run(["docker","exec","-i","clipstudio-download-cobalt-1",
            "node","--import","/bridge/head-fallback.mjs","--input-type=module"], input=UPSTREAM_PROBE, capture_output=True,
            text=True, timeout=110, check=True)
        for line in process.stdout.splitlines():
            if line.startswith("CLIP_PROBE_JSON:"):
                return json.loads(line.removeprefix("CLIP_PROBE_JSON:"))
    except Exception:
        pass
    return {"error":"PROBE_UNAVAILABLE"}


def validation_summary():
    try:
        records=json.loads((ROOT/'data/cobalt/validation.json').read_text(encoding='utf-8')).get('results',[])
        if not isinstance(records,list):return []
        allowed=('video_id','mode','success','duration','expected_duration','bytes','verification_version','error_code','message')
        summary=[]
        for record in records:
            if not isinstance(record,dict):continue
            value={key:record[key] for key in allowed if key in record}
            transfer=record.get('transfer')
            if isinstance(transfer,dict):
                value['transfer']={key:transfer[key] for key in ('source_duration','source_expected_bytes','downloaded_bytes','total_bytes') if key in transfer}
            summary.append(value)
        return summary
    except (OSError,ValueError,AttributeError):return []


def main():
    try:
        config=json.loads((ROOT/'data/cobalt/client.json').read_text(encoding='utf-8'))
        endpoint=config['endpoint']
        from urllib.parse import urlsplit
        parsed=urlsplit(endpoint)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.port!=9000 or parsed.username or parsed.password:
            raise ValueError('Solo se diagnostica el servicio local instalado.')
        report={'description':'Media prefixes only; not a successful full download','containers':{},'validation_results':validation_summary()}
        for name in ('cobalt','pot-provider','session-bridge'):
            try:
                output=subprocess.run(['docker','inspect','--format','{{json .State}}','clipstudio-download-'+name+'-1'],capture_output=True,text=True,timeout=10,check=True)
                state=json.loads(output.stdout)
                report['containers'][name]={'running':state.get('Running'),'oom_killed':state.get('OOMKilled'),'exit_code':state.get('ExitCode')}
                if name=='cobalt':
                    command=subprocess.run(['docker','inspect','--format','{{json .Config.Cmd}}','clipstudio-download-cobalt-1'],capture_output=True,text=True,timeout=10,check=True)
                    args=json.loads(command.stdout)
                    report['containers'][name]['compatibility_preload_configured']=isinstance(args,list) and '/bridge/head-fallback.mjs' in args
            except Exception:
                report['containers'][name]={'inspection':'unavailable'}
        print('Comprobando transferencia y pistas por separado. Puede tardar unos minutos.',flush=True)
        with httpx.Client(timeout=httpx.Timeout(35,connect=10),follow_redirects=False) as client:
            report['paths']=inspect_paths(client,endpoint,config['api_key'])
        print('Comprobando acceso a las pistas dentro del servicio. Espera hasta dos minutos.',flush=True)
        report['upstream']=upstream_probe()
        path=ROOT/'DIAGNOSTICO_COBALT.json'
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        print('Informe guardado: DIAGNOSTICO_COBALT.json. No contiene claves ni URLs de descarga.')
        return 0
    except Exception:
        print('No se pudo preparar el diagnóstico local. No se muestran datos privados.')
        return 1


if __name__=='__main__':raise SystemExit(main())
