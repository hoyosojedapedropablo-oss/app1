"""Windows helper to install/load Ollama's model and verify actual GPU residency."""
import os,shutil,subprocess,time
from pathlib import Path
import gpu_ai


def executable():
    discovered=shutil.which('ollama')
    if discovered:return discovered
    path=Path(os.getenv('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'
    return str(path) if path.exists() else None

if __name__=='__main__':
    cli=executable()
    if not cli:raise SystemExit('Ollama no está instalado. Instálalo con winget install --id Ollama.Ollama -e --source winget y vuelve a ejecutar el instalador.')
    if not gpu_ai.status()['available']:
        Path('data').mkdir(exist_ok=True)
        with open('data/ollama-startup.log','ab') as log:subprocess.Popen([cli,'serve'],stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if gpu_ai.status()['available']:break
            time.sleep(.5)
        else:raise SystemExit('Ollama no arrancó. Ábrelo desde Inicio y vuelve a intentarlo.')
    version=(gpu_ai.status().get('version') or '0.0.0').split('.')
    if tuple(int(v.split('-')[0]) for v in version[:2])<(0,12):raise SystemExit('Actualiza Ollama para RTX serie 50: winget upgrade --id Ollama.Ollama -e --source winget')
    if not gpu_ai.status()['model_ready']:
        free=shutil.disk_usage(Path.home()).free
        if free<10*1024**3:raise SystemExit('Libera al menos 10 GB en la unidad que guarda los modelos antes de descargar.')
        print('Descargando qwen2.5:7b (~4,7 GB), solo la primera vez...',flush=True)
        subprocess.run([cli,'pull',gpu_ai.MODEL],check=True)
    try:
        info=gpu_ai.warmup()
        print('GPU VERIFICADA:',round(info['gpu_bytes']/1024**3,2),'GB del modelo en memoria GPU. No necesita clave de API.',flush=True)
    except ValueError as e:raise SystemExit(str(e))
