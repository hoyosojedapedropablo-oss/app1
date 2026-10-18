"""Read-only, bounded access comparison. No import or service configuration changes."""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
VARIANTS=[{'name':'IOS_default_path','quality':'1080'},
    {'name':'WEB_EMBEDDED_with_session','quality':'2160','sessionClient':'WEB_EMBEDDED'},
    {'name':'WEB_with_session','quality':'2160','sessionClient':'WEB'}]
PROBE=r'''
console.log=console.warn=console.error=()=>{};
const report={schema:1,description:'Small byte samples only; not full downloads',session_ready:false,cases:[]};
let finished=false;
function finish(){if(finished)return;finished=true;process.stdout.write('CLIP_ACCESS_JSON:'+JSON.stringify(report)+'\n');process.exit(0);}
setTimeout(()=>{report.deadline_reached=true;finish();},95000).unref();
try {
  const {fetch,EnvHttpProxyAgent}=await import('undici');
  const {env}=await import('./src/config.js');
  const session=await import('./src/processing/helpers/youtube-session.js');
  const {default:extract}=await import('./src/processing/services/youtube.js');
  const {getHeaders}=await import('./src/stream/shared.js');
  const dispatcher=new EnvHttpProxyAgent();
  session.setup();
  for(let i=0;i<100&&!session.getYouTubeSession()?.potoken;i++)await new Promise(resolve=>setTimeout(resolve,100));
  report.session_ready=!!session.getYouTubeSession()?.potoken;
  const variants=__CLIP_VARIANTS__;
  for(const variant of variants){
    const record={name:variant.name,extraction_ok:false,tracks:[]};report.cases.push(record);
    if(variant.sessionClient&&!report.session_ready){record.error='SESSION_UNAVAILABLE';continue;}
    if(variant.sessionClient)env.ytSessionInnertubeClient=variant.sessionClient;
    // Pinned Cobalt enables its session path for quality>1080. H264 remains
    // the codec for both cases; this diagnostic never changes the user's quality.
    const media=await extract({id:'JCcuOv5y_9g',quality:variant.quality,codec:'h264',container:'mp4',
      innertubeClient:'IOS',isAudioOnly:false,youtubeHLS:false,dispatcher});
    if(media.error){record.error=/^[a-z0-9_.]{1,100}$/.test(media.error)?media.error:'EXTRACTION_FAILED';continue;}
    if(!Array.isArray(media.urls)||media.urls.length!==2){record.error='UNEXPECTED_TRACKS';continue;}
    record.extraction_ok=true;
    const duration=media.originalRequest?.expectedDuration;
    if(typeof duration==='number'&&Number.isFinite(duration)&&duration>0&&duration<=7200)record.expected_duration=duration;
    for(const [index,value]of media.urls.entries()){
      const track={kind:index===0?'video':'audio',samples:[]};record.tracks.push(track);
      const url=new URL(value);
      if(url.protocol!=='https:'||!(url.hostname==='googlevideo.com'||url.hostname.endsWith('.googlevideo.com'))||url.username||url.password){track.error='UNEXPECTED_MEDIA_HOST';continue;}
      // Presence only. Never expose query values, URL paths, signatures or IDs.
      track.has_pot=url.searchParams.has('pot');track.has_n=url.searchParams.has('n');
      for(const position of ['start','observed_cut','middle']){
        const total=track.total_bytes;
        if(position==='middle'&&!total)continue;
        const start=position==='start'?0:position==='observed_cut'?15274496:Math.floor(total/2);
        if(total&&start>=total)continue;
        const end=total?Math.min(total-1,start+65535):start+65535;
        const sample={position,start,end,received:0};track.samples.push(sample);
        let response;
        try {
          response=await fetch(url,{dispatcher,redirect:'error',signal:AbortSignal.timeout(12000),
            headers:{...getHeaders('youtube'),Range:`bytes=${start}-${end}`}});
          sample.http_status=response.status;
          const match=/^bytes ([0-9]+)-([0-9]+)\/([0-9]+)$/.exec(response.headers.get('content-range')||'');
          const valid=match&&Number(match[1])===start&&Number(match[2])===end&&Number(match[3])>end;
          if(valid){
            sample.total_bytes=Number(match[3]);
            if(!track.total_bytes)track.total_bytes=sample.total_bytes;
          }
          sample.range_valid=!!valid&&sample.total_bytes===track.total_bytes;
          const type=response.headers.get('content-type')||'';
          sample.media_type=type.startsWith('video/')?'video':type.startsWith('audio/')?'audio':'other';
          if(response.status===206&&sample.range_valid&&sample.media_type!=='other'){
            const reader=response.body.getReader();
            try{
              while(true){const {done,value:part}=await reader.read();if(done)break;sample.received+=part.length;if(sample.received>end-start+1)throw Error('OVERSIZED');}
            }finally{await reader.cancel().catch(()=>{});}
            sample.complete=sample.received===end-start+1;
          }else await response.body?.cancel();
        }catch{sample.error='NETWORK_TIMEOUT_OR_INVALID_BODY';await response?.body?.cancel().catch(()=>{});}
      }
    }
  }
}catch{report.error='PROBE_FAILED';}
finish();
'''


def parse_output(text):
    # Only our structured JSON is copied; raw extraction logs are never written.
    for line in text.splitlines():
        if line.startswith('CLIP_ACCESS_JSON:'):
            value=json.loads(line.removeprefix('CLIP_ACCESS_JSON:'))
            if isinstance(value,dict) and value.get('schema')==1:return value
    raise ValueError('missing report')


def main():
    print('Comparando accesos y bloques posteriores al corte. Puede tardar hasta seis minutos.',flush=True)
    print('No modifica la app ni activa el servicio. No descarga videos completos.',flush=True)
    try:
        report={'schema':1,'description':'Small byte samples only; not full downloads','cases':[]}
        for variant in VARIANTS:
            print('Comprobando '+variant['name']+'...',flush=True)
            # Separate processes prevent Cobalt's cached first-client session from
            # contaminating the visitor binding of the attested comparison.
            script=PROBE.replace('__CLIP_VARIANTS__',json.dumps([variant]))
            result=subprocess.run(['docker','exec','-i','clipstudio-download-cobalt-1','node',
                '--import','/bridge/head-fallback.mjs','--input-type=module'],input=script,
                capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=110,check=True)
            observed=parse_output(result.stdout)
            case={'name':variant['name'],'session_ready':observed.get('session_ready',False)}
            case.update(observed.get('cases',[{}])[0] if observed.get('cases') else {'error':'PROBE_FAILED'})
            if observed.get('deadline_reached'):case['deadline_reached']=True
            report['cases'].append(case)
        path=ROOT/'DIAGNOSTICO_ACCESO.json'
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        print('Informe guardado: DIAGNOSTICO_ACCESO.json. Envía ese archivo; no repitas la actualización.')
        return 0
    except (OSError,ValueError,subprocess.SubprocessError):
        print('No se pudo completar la comparación. No se muestran logs privados. Envía una captura de este resultado.')
        return 1


if __name__=='__main__':raise SystemExit(main())
