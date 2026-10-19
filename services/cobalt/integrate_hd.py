"""Install HD-only imports after rechecking both full 1080p proof videos."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
REVISION='1c6709c909b8a91362776bf111daf89998c22898'
BASE='https://raw.githubusercontent.com/hoyosojedapedropablo-oss/app1/'+REVISION+'/'
FILES={
    "native_import.py": "6e3ca14c1ca233df417889e8298e70c597b11543bd63181b0bf4ded43db3ebaa",
    "app.py": "89b167b9973428dfc3fa16615be55ec48a5e9f66dd3794aab21edba84ba4e4b4"
}
PREVIOUS={
    "native_import.py": [
        "27ed64ed946f1604ece2a3dc3ed0fe2c6f968ea92e5442177017f668916572de",
        "6e3ca14c1ca233df417889e8298e70c597b11543bd63181b0bf4ded43db3ebaa"
    ],
    "app.py": [
        "06f666ab807a348eb125d10826beb3d8e1fc8ac3cf4075f891e74b8f57f5cd34",
        "089f2580cdbcdeb57882e45297530745d44858c8d7a468facb33eb1a6750f838",
        "1b5bf191731e2e76a5cbf3413dd1bc48a93822eb187c55ae163057d89eb6a004",
        "21704a8bfbe2255fa8b83c0faa76399ef4121f2077a32e8d50fad2907b6a64d1",
        "226defb7e2baf3d32a885645c341c8a01380fb9b2f124bd7b4fc5b187ab094df",
        "3923e4710aa08067155c934dd3cba36b789ad6008df8cfb4b5a2395516d9595f",
        "3e8c50038417a28db253aa1914900f16feac8dc3e90292d9140504c7f9471669",
        "42a7c6151057f96ebb8dd330909c1de0ba8b13b6539e863a48f273336a5b3e8a",
        "45adbdc1967f3e41d117787593368fd3afba289406fc85315f0b274f1c16e4b2",
        "53d9278c6fb42cb677e5c87fba5e43ff8418c7938632640f2394d740be687892",
        "801af05f1032e2910b44a5ce56a5968070f79281175372775e9765f273c4f1ca",
        "89b167b9973428dfc3fa16615be55ec48a5e9f66dd3794aab21edba84ba4e4b4",
        "96e2697c2dfa7970a569c03782641b68e2b0b01452e9ac3eff6d8b30e333e49d",
        "9cc9dae4d183de0aacfcd69a62f605aa183a0880814e8aefb393c472d493ff53",
        "a31f8a2b837ce93bf2164afb4121260c2dbd69a6fdf54870aa8e1e08b2d189c1",
        "a477211762c6a3a3b5c20af5b9a560dc2c0a3accd59757cc1e539704f443c703",
        "b9c6f87644a729a9a5c8d957486d95c4fa39f2b987a903f905a49e7b30d6e251",
        "bde8a8d72150f7cf49eddf5968c66d53502841337de3a7b05c98a442c228be3e",
        "cb8d73aa748abb96be7b1f458cf75ae295cbada323c448cb8bd8cfb531963a30",
        "fe50a8cd6e33e32973afbf7004aecdcd2adfa455977e2ba951aea68520ca7395"
    ]
}


def digest(data):return hashlib.sha256(data).hexdigest()


def inspect_hd(path):
    import subprocess
    result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
        'stream=width,height','-of','json',str(path)],capture_output=True,
        text=True,encoding='utf-8',errors='replace',timeout=30,check=True)
    video=json.loads(result.stdout)['streams'][0]
    width=int(video['width']);height=int(video['height'])
    if min(width,height)<720:raise ValueError('El archivo no cumple el mínimo HD de 720p.')
    return {'measured_width':width,'measured_height':height}


def validated_config(root,verify):
    report=json.loads((root/'RESULTADO_DESCARGA_HD.json').read_text(encoding='utf-8'))
    if report.get('full_downloads_verified') is not True or report.get('versions')!={'yt_dlp':'2026.8.19','bgutil_plugin':'2.0.2'}:
        raise ValueError('El informe no confirma las dos descargas completas con las versiones probadas.')
    records=report.get('results')
    if not isinstance(records,list) or len(records)!=2 or {r.get('video_id') for r in records}!={'JCcuOv5y_9g','rcPWJKs5It4'}:
        raise ValueError('Faltan los dos videos de comprobación.')
    from math import isfinite
    safe=[]
    for record in records:
        duration=record.get('expected_duration')
        if record.get('success') is not True or type(duration) not in (int,float) or not isfinite(duration) or not 0<duration<=7200:
            raise ValueError('Un video no pasó la verificación de duración.')
        # Reports produced on Windows contain backslashes. Only proof files under
        # this app's dedicated validation folder can enable this integration.
        path=(root/record['path'].replace('\\','/')).resolve()
        path.relative_to((root/'data/cobalt/hd-validation').resolve())
        if path.name!='download.mp4' or path.stat().st_size!=record['bytes']:
            raise ValueError('Un archivo cambió o no está en la carpeta de comprobación.')
        verify(path,float(duration))
        measured=inspect_hd(path)
        if record.get('measured_width')!=measured['measured_width'] or record.get('measured_height')!=measured['measured_height']:
            raise ValueError('La resolución del archivo no coincide con el informe HD.')
        safe.append({'video_id':record['video_id'],'success':True,'expected_duration':duration,
            'bytes':path.stat().st_size,'path':path.relative_to(root.resolve()).as_posix(),**measured})
    return {'enabled':True,'verification_version':2,'enabled_modes':['fast'],'minimum_height':720,'quality_profile':'hd','verified_files':safe}


def fetch_files():
    result={}
    for name,expected in FILES.items():
        with urllib.request.urlopen(BASE+name,timeout=30) as response:content=response.read(262145)
        if len(content)>262144 or digest(content)!=expected:
            raise ValueError('La actualización no pasó la verificación SHA-256. No se aplicaron cambios.')
        result[name]=content
    return result


def atomic_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    import os
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as output:
        temporary=Path(output.name);output.write(data)
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def apply_files(root,files,config):
    if set(files)!=set(FILES) or any(digest(files[name])!=expected for name,expected in FILES.items()):
        raise ValueError('El paquete recibido está incompleto o cambió.')
    for name in files:
        path=root/name
        if path.exists() and digest(path.read_bytes()) not in set(PREVIOUS.get(name,[]))|{FILES[name]}:
            raise ValueError('Se conservaron cambios locales en '+name+'. La instalación se detuvo.')
    configpath=root/'data/youtube-native.json'
    backup=root/'data'/('hd-integration-backup-'+uuid.uuid4().hex);backup.mkdir(parents=True)
    previous={}
    for name in [*files,'data/youtube-native.json']:
        path=root/name;previous[name]=path.read_bytes() if path.exists() else None
        if path.exists():
            dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    try:
        # Native implementation first, routing second, server last. Configuration
        # becomes enabled only after every verified source file is installed.
        for name,content in files.items():atomic_write(root/name,content)
        atomic_write(configpath,json.dumps(config,indent=2).encode())
    except Exception:
        for name,data in previous.items():
            if data is None:(root/name).unlink(missing_ok=True)
            else:atomic_write(root/name,data)
        raise
    return backup


def main():
    try:
        if version('yt-dlp')!='2026.8.19' or version('bgutil-ytdlp-pot-provider')!='2.0.2':
            raise ValueError('Las versiones instaladas difieren de las que descargaron correctamente los videos.')
        from cobalt_import import _verify_media
        print('Revisando audio, duración y resolución de ambos videos HD. No se descargarán otra vez...',flush=True)
        config=validated_config(ROOT,_verify_media)
        print('Verificando e instalando la integración del botón de YouTube...',flush=True)
        files=fetch_files()
        apply_files(ROOT,files,config)
        print('HD instalado en el botón de YouTube: mínimo 720p y hasta 1080p. Original sigue pendiente.',flush=True)
        print('Cierra la ventana que ejecuta la app con Ctrl+C y abre INICIAR_WINDOWS de esta misma carpeta.',flush=True)
        print('Después pega uno de los enlaces y pulsa Importar video de YouTube. Se reutilizará el MP4 completo HD verificado; los archivos 360p quedan excluidos.',flush=True)
        return 0
    except ValueError as error:
        # These messages are generated locally, not from extractor/HTTP logs.
        print(str(error),flush=True)
    except Exception:
        print('No se completó la integración HD. Envía una captura; no repitas las actualizaciones anteriores.',flush=True)
    return 1


if __name__=='__main__':raise SystemExit(main())
