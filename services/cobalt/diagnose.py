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


def main():
    try:
        config=json.loads((ROOT/'data/cobalt/client.json').read_text(encoding='utf-8'))
        endpoint=config['endpoint']
        from urllib.parse import urlsplit
        parsed=urlsplit(endpoint)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.port!=9000 or parsed.username or parsed.password:
            raise ValueError('Solo se diagnostica el servicio local instalado.')
        report={'description':'Media prefixes only; not a successful full download','containers':{}}
        for name in ('cobalt','pot-provider','session-bridge'):
            try:
                output=subprocess.run(['docker','inspect','--format','{{json .State}}','clipstudio-download-'+name+'-1'],capture_output=True,text=True,timeout=10,check=True)
                state=json.loads(output.stdout)
                report['containers'][name]={'running':state.get('Running'),'oom_killed':state.get('OOMKilled'),'exit_code':state.get('ExitCode')}
            except Exception:
                report['containers'][name]={'inspection':'unavailable'}
        print('Comprobando transferencia y pistas por separado. Puede tardar unos minutos.',flush=True)
        with httpx.Client(timeout=httpx.Timeout(35,connect=10),follow_redirects=False) as client:
            report['paths']=inspect_paths(client,endpoint,config['api_key'])
        path=ROOT/'DIAGNOSTICO_COBALT.json'
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        print('Informe guardado: DIAGNOSTICO_COBALT.json. No contiene claves ni URLs de descarga.')
        return 0
    except Exception:
        print('No se pudo preparar el diagnóstico local. No se muestran datos privados.')
        return 1


if __name__=='__main__':raise SystemExit(main())
