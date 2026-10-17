"""Install the source-verified media compatibility fix without replacing the app."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2]
REVISION='11009339f41d3bcefef1b58d8badcf2b4c4f28c9'
BASE='https://raw.githubusercontent.com/hoyosojedapedropablo-oss/app1/'+REVISION+'/services/cobalt/'
FILES={
    'head-fallback.mjs':'146f6b8d82e1e227bbd8bf05aa7a61865bf016fcc00c834bad68a96708cb2d30',
    'media-probe.mjs':'40f28d578f502255e38b21251ac7f2d832a6aaa243cc229eba283b2d7cc2b101',
    'compose.yaml':'bc5e45205bbd33e4517c1b93c21a458fcc457e83e77b5171ac278008e45d4161',
}
ORIGINAL_COMPOSE='b208f10567f8429d6a21738800ba2ebffddbd3256d931deb06f24110c390c9ab'


def digest(data):return hashlib.sha256(data).hexdigest()


def fetch_files():
    files={}
    for name,expected in FILES.items():
        with urllib.request.urlopen(BASE+name,timeout=30) as response:
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
        path=service/name
        allowed={expected,ORIGINAL_COMPOSE} if name=='compose.yaml' else {expected}
        if path.exists() and digest(path.read_bytes()) not in allowed:
            raise ValueError('Hay cambios locales en '+name+'. Se conservaron; la actualización se detuvo.')
    backup=root/'data/cobalt'/('compat-backup-'+uuid.uuid4().hex)
    backup.mkdir(parents=True)
    previous={}
    for name in FILES:
        path=service/name
        previous[name]=path.exists()
        if path.exists():shutil.copy2(path,backup/name)
    try:
        for name,content in files.items():
            destination=service/name
            with tempfile.NamedTemporaryFile(dir=service,delete=False) as output:
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
        target=root/'services/cobalt'/name
        if existed:shutil.copy2(backup/name,target)
        else:target.unlink(missing_ok=True)


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
        print('Reiniciando el servicio con la corrección...',flush=True)
        result=subprocess.run([str(python),str(manage),'start'],cwd=ROOT)
        if result.returncode:
            restore_files(ROOT,backup,previous)
            print('El servicio corregido no arrancó. Se restauraron los archivos anteriores.',flush=True)
            subprocess.run([str(python),str(manage),'start'],cwd=ROOT)
            return 1
        print('Corrección aplicada. Probando descargas completas de los dos videos en ambas calidades; espera el resultado.',flush=True)
        result=subprocess.run([str(python),str(manage),'validate'],cwd=ROOT)
        if result.returncode:
            print('La corrección se instaló, pero la prueba real no pasó. Envía una captura del resultado; no repitas la instalación.')
        else:
            print('Las cuatro descargas pasaron. Falta revisar los MP4 antes de activar el servicio en la app.')
        return result.returncode
    except ValueError as error:
        print(str(error))
    except Exception:
        print('La actualización no pudo completarse. Envía una captura; no se muestran datos privados.')
    return 1


if __name__=='__main__':raise SystemExit(main())
