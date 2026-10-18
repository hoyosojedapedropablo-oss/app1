"""Install the source-verified media compatibility fix without replacing the app."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2]
REVISION='13b513ff78042416c1588fcc99fb0575ccd91b32'
SOURCE_ROOT='https://raw.githubusercontent.com/hoyosojedapedropablo-oss/app1/'+REVISION+'/'
BASE=SOURCE_ROOT+'services/cobalt/'
ROOT_FILES={'cobalt_import.py'}

def target(root,name):return root/name if name in ROOT_FILES else root/'services/cobalt'/name

FILES={
    "head-fallback.mjs": "d522dd8baafd9411896d4c6110e1cdad235e169c3d1b7480382e48c5f6aad929",
    "media-probe.mjs": "40f28d578f502255e38b21251ac7f2d832a6aaa243cc229eba283b2d7cc2b101",
    "media-chunks.mjs": "05d4e41f437bc0e58fde68846d387e0744ad569afd10bf2dfb5419581a7ed868",
    "compose.yaml": "d4c3dce196a5718d26c846146205a12dcda49fc29ba3d37151e8792df4b3cbe2",
    "manage.py": "9e893d330ca7124e47ae6b83ca58deb361f355e61bbac7e6b29896b9117063b6",
    "diagnose.py": "ab0e42bd55390975258b50dd75b9b9942913d374e2c8cd0fe6fb04769ab109da",
    "cobalt_import.py": "d878265c0474e78d47ff69d3be100d6a292d878402b80de4b06296d33eec5fce"
}
PREVIOUS_FILES={
    "head-fallback.mjs": [
        "146f6b8d82e1e227bbd8bf05aa7a61865bf016fcc00c834bad68a96708cb2d30",
        "d1b76b4f98d8803b6838fed1a36ec7db9e7022ccf6108f9956289fd1f515ed4a",
        "d522dd8baafd9411896d4c6110e1cdad235e169c3d1b7480382e48c5f6aad929"
    ],
    "media-probe.mjs": [
        "40f28d578f502255e38b21251ac7f2d832a6aaa243cc229eba283b2d7cc2b101"
    ],
    "media-chunks.mjs": [
        "b1223b6219b76b7bb51b00f8175c18e9a2c4e9d46b388d2c92eb0e4d2c85390c"
    ],
    "compose.yaml": [
        "b208f10567f8429d6a21738800ba2ebffddbd3256d931deb06f24110c390c9ab",
        "bc5e45205bbd33e4517c1b93c21a458fcc457e83e77b5171ac278008e45d4161",
        "d4c3dce196a5718d26c846146205a12dcda49fc29ba3d37151e8792df4b3cbe2",
        "e2be59d69479735bac1dc9a262d9d63898eaf242bc293afb1d6c3aece50b2583"
    ],
    "manage.py": [
        "6a2092f593c88f8ff96adb41ce1146b4cc6f86369f349cc8e3e94f12bc6dfcf2",
        "983e25bf426ce6b516a37ab439eea3129dab303b64d33c1444df084623939c16",
        "9e893d330ca7124e47ae6b83ca58deb361f355e61bbac7e6b29896b9117063b6",
        "c7e1c65039fa29f863536349c48762ce17be291390ea91e6c521f55b08562cca",
        "e843c6058298fd963aee5e747838fe36cb33be2046da732c1301f83fa84e1ad2"
    ],
    "diagnose.py": [
        "187c55579cffd0aa3bf4603fbfbf954c66ce65a1fe829f48538f15d655768bfd",
        "764a8f9b5ca64185df69a75d51d395536eb0423337cd16f4fb365373cd9e3a87",
        "79b0302fa58e48939e86a39321c0085084c7aff9c53d6ccff0d4753e93ae7b2b",
        "96f74fc2cf183d9fad73c0cadbd51ba3886a035e7001e89b4990521a6a2bc0bb",
        "a0ca6dae708d6054915d3c0b56ef1261e6d9bda5f81bfdc3451359a637167a1d",
        "a586c76300a392263a315382955db0bc2b3399b80391565d1ef9079e8680710c"
    ],
    "cobalt_import.py": [
        "0fccac59dd73fbc060e064cd2d1c35da7cce3704369dd243759408c65439109e",
        "59f3d8b832005d9ace7e792b555997ffc20c15264ad9ae805359376beda41e01",
        "b7701fef025bea15254c4c43dd7a4d74f3ef1bb8abbab51bb1f5d440c94cefe8",
        "d878265c0474e78d47ff69d3be100d6a292d878402b80de4b06296d33eec5fce"
    ]
}
ORIGINAL_COMPOSE='b208f10567f8429d6a21738800ba2ebffddbd3256d931deb06f24110c390c9ab'


def digest(data):return hashlib.sha256(data).hexdigest()


def fetch_files():
    files={}
    for name,expected in FILES.items():
        with urllib.request.urlopen((SOURCE_ROOT if name in ROOT_FILES else BASE)+name,timeout=30) as response:
            content=response.read(262145)
        if len(content)>262144 or digest(content)!=expected:
            raise ValueError('La verificación del archivo descargado falló. No se aplicaron cambios.')
        files[name]=content
    return files


def apply_files(root,files):
    if set(files)!=set(FILES) or any(digest(files[name])!=expected for name,expected in FILES.items()):
        raise ValueError('El paquete de actualización no pasó la verificación.')
    service=root/'services/cobalt'
    for name,expected in FILES.items():
        path=target(root,name)
        allowed=set(PREVIOUS_FILES.get(name,[]))|{expected}
        if path.exists() and digest(path.read_bytes()) not in allowed:
            raise ValueError('Hay cambios locales en '+name+'. Se conservaron; la actualización se detuvo.')
    backup=root/'data/cobalt'/('compat-backup-'+uuid.uuid4().hex)
    backup.mkdir(parents=True)
    previous={}
    for name in FILES:
        path=target(root,name)
        previous[name]=path.exists()
        if path.exists():shutil.copy2(path,backup/name)
    try:
        for name,content in files.items():
            destination=target(root,name)
            with tempfile.NamedTemporaryFile(dir=destination.parent,delete=False) as output:
                temporary=Path(output.name)
                output.write(content)
            try:os.replace(temporary,destination)
            finally:temporary.unlink(missing_ok=True)
    except Exception:
        restore_files(root,backup,previous)
        raise
    return backup,previous


def restore_files(root,backup,previous):
    for name,existed in previous.items():
        destination=target(root,name)
        if existed:shutil.copy2(backup/name,destination)
        else:destination.unlink(missing_ok=True)


def main():
    python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    manage=ROOT/'services/cobalt/manage.py'
    if not python.is_file() or not manage.is_file():
        print('Ejecuta esta herramienta desde la carpeta de la app ya preparada con INICIAR_WINDOWS.')
        return 1
    try:
        print('Descargando y verificando la corrección. No reemplaza videos ni claves.',flush=True)
        files=fetch_files()
        backup,previous=apply_files(ROOT,files)
        subprocess.run([str(python),str(manage),'disable'],cwd=ROOT,check=True)
        print('Reiniciando el servicio con la corrección...',flush=True)
        result=subprocess.run([str(python),str(manage),'start'],cwd=ROOT)
        if result.returncode:
            restore_files(ROOT,backup,previous)
            print('El servicio corregido no arrancó. Se restauraron los archivos anteriores.',flush=True)
            subprocess.run([str(python),str(manage),'start'],cwd=ROOT)
            return 1
        print('Actualización aplicada. Verificando pistas completas y duración original, con recuperación limitada de cortes. Los archivos antiguos de 64 segundos no se reutilizarán.',flush=True)
        result=subprocess.run([str(python),str(manage),'validate','--quality','fast','--reuse'],cwd=ROOT)
        if result.returncode:
            print('La actualización se instaló, pero la prueba real no pasó. Generando el diagnóstico; espera...',flush=True)
            subprocess.run([str(python),str(ROOT/'services/cobalt/diagnose.py')],cwd=ROOT)
            print('Envía DIAGNOSTICO_COBALT.json y una captura del resultado; no repitas la instalación.')
        else:
            print('Los dos videos pasaron las comprobaciones de pistas completas y duración original. Revisa los MP4 antes de habilitar calidad rápida.')
            records=json.loads((ROOT/'data/cobalt/validation.json').read_text(encoding='utf-8')).get('results',[])
            for record in records:
                if record.get('mode')=='fast' and record.get('verification_version')==2 and record.get('success') is True:
                    expected=int(round(record['expected_duration']));actual=int(round(record['duration']))
                    print(f"{record['video_id']}: original {expected//60}:{expected%60:02d} · archivo {actual//60}:{actual%60:02d}")
            review=ROOT/'data/cobalt/validation/VERIFICADOS'
            print('Videos para revisar: data/cobalt/validation/VERIFICADOS')
            if os.name=='nt' and review.is_dir():os.startfile(str(review))
        return result.returncode
    except ValueError as error:
        print(str(error))
    except Exception:
        print('La actualización no pudo completarse. Envía una captura; no se muestran datos privados.')
    return 1


if __name__=='__main__':raise SystemExit(main())
