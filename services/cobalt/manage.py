"""Operator commands. Does not enable the provider until real validation passes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
STATE = ROOT/'data'/'cobalt'
CLIENT = STATE/'client.json'
VALIDATION = STATE/'validation.json'
EXPECTED = {(ident, mode) for ident in ('JCcuOv5y_9g', 'rcPWJKs5It4') for mode in ('fast', 'original')}


def write_json(path, value, mode=0o600):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(value, output, indent=2)
    temporary.chmod(mode)
    temporary.replace(path)


def initialize():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    keys = STATE/'keys.json'
    if not CLIENT.exists() and not keys.exists():
        key = str(uuid.uuid4())
        # File readable in the non-root container; parent directory is owner-only.
        write_json(keys, {key: {'name':'Clip Studio', 'limit':12, 'allowedServices':['youtube']}}, 0o444)
        write_json(CLIENT, dict(enabled=False, endpoint='http://127.0.0.1:9000/', api_key=key))
    if not CLIENT.exists() or not keys.is_file():
        raise ValueError('Faltan archivos del servicio. Revisa su configuración sin sobrescribir claves existentes.')


def identity(config):
    return hashlib.sha256((config['endpoint']+'\n'+config['api_key']).encode()).hexdigest()


def compose(action):
    initialize()
    env = os.environ.copy()
    args = ['docker']
    cert = env.get('CODEX_PROXY_CERT')
    if cert:
        if not Path(cert).is_file():
            raise ValueError('No se encontró el certificado del proxy; no se desactivará TLS.')
        for name in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
            env.pop(name, None)
        args += ['--host=unix:///var/run/docker.sock']
    args += ['compose', '-f', str(ROOT/'services/cobalt/compose.yaml')]
    if cert:
        # Docker supplies reachable proxy defaults. Only mount CA trust here;
        # never copy proxy credentials into images, compose files, or logs.
        services = {}
        for service in ('cobalt','pot-provider','session-bridge'):
            services[service] = dict(volumes=[dict(type='bind', source=cert,
                target='/run/proxy-ca.pem', read_only=True)],
                environment={'NODE_EXTRA_CA_CERTS':'/run/proxy-ca.pem','DENO_CERT':'/run/proxy-ca.pem'})
        override = STATE/'cloud-ca.compose.json'
        write_json(override, {'services':services})
        args += ['-f', str(override)]
    args += ['up', '-d', '--wait', '--wait-timeout', '120'] if action == 'start' else ['down']
    subprocess.run(args, env=env, cwd=ROOT, check=True)


def validate():
    initialize()
    from cobalt_import import download, CobaltFailure
    config = json.loads(CLIENT.read_text())
    os.environ['CLIP_COBALT_URL'] = config['endpoint']
    os.environ['CLIP_COBALT_KEY'] = config['api_key']
    results = []
    for ident, mode in sorted(EXPECTED):
        folder = STATE/'validation'/uuid.uuid4().hex
        folder.mkdir(parents=True)
        record = dict(video_id=ident, mode=mode, success=False)
        try:
            path, _ = download('https://www.youtube.com/watch?v='+ident, folder, lambda *a,**k:None, mode=mode)
            process = subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)], capture_output=True, text=True, check=True)
            media = json.loads(process.stdout)
            video = next(s for s in media['streams'] if s['codec_type']=='video')
            audio = next(s for s in media['streams'] if s['codec_type']=='audio')
            duration = float(media['format']['duration'])
            if not 0 < duration <= 7200:
                raise ValueError('Duración no admitida')
            if mode == 'fast' and video['height'] > 1080:
                raise ValueError('Resolución no admitida para el modo rápido')
            record.update(success=True, bytes=path.stat().st_size, duration=duration,
                width=video['width'], height=video['height'], video_codec=video['codec_name'], audio_codec=audio['codec_name'])
        except CobaltFailure as error:
            record['error_code'] = error.code
            record['message'] = error.safe_message
        except Exception:
            record['error_code'] = 'VALIDACION-MEDIA'
        results.append(record)
        print(ident, mode, 'OK' if record['success'] else record['error_code'], flush=True)
        if record.get('message'):
            print(record['message'], flush=True)
        if not record['success']:
            break  # No repeated upstream requests after a failed access check.
    write_json(VALIDATION, dict(config_identity=identity(config), results=results))
    return len(results)==len(EXPECTED) and all(r['success'] for r in results)


def activate():
    config = json.loads(CLIENT.read_text())
    check = json.loads(VALIDATION.read_text())
    results = check.get('results', [])
    if (check.get('config_identity') != identity(config) or
        {(r.get('video_id'),r.get('mode')) for r in results if r.get('success') is True} != EXPECTED):
        raise ValueError('El servicio no superó las cuatro descargas reales requeridas. Permanece desactivado.')
    config['enabled'] = True
    write_json(CLIENT, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init','start','stop','validate','activate','disable'])
    action = parser.parse_args().action
    try:
        if action in ('start','stop'):
            compose(action)
        elif action == 'init':
            initialize()
        elif action == 'validate':
            if not validate():
                return 1
        elif action == 'activate':
            activate()
        elif action == 'disable':
            config = json.loads(CLIENT.read_text());config['enabled']=False;write_json(CLIENT,config)
        print('Operación completada. Las claves no se muestran ni se incluyen en el repositorio.')
        return 0
    except ValueError as error:
        print(str(error))
    except Exception:
        print('La operación falló. El servicio no se activó automáticamente; revisa su configuración y estado.')
    return 1


if __name__=='__main__':
    raise SystemExit(main())
