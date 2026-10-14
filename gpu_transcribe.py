"""Optional CUDA transcription in an isolated process, releasing VRAM on exit."""
import importlib.util,json,os,subprocess,sys,time
from pathlib import Path


def installed():
    return importlib.util.find_spec('torch') is not None and importlib.util.find_spec('whisper') is not None


def transcribe(source,folder,cancel,on_progress):
    from cloud_ai import AnalysisCancelled
    if not installed():raise ValueError('La transcripción GPU requiere INSTALAR_TRANSCRIPCION_GPU_WINDOWS. Puedes desmarcar esa opción y conservar la transcripción CPU.')
    state=folder/'gpu-transcription-state.json';state.unlink(missing_ok=True)
    output=folder/'gpu-transcript.json';output.unlink(missing_ok=True)
    log_path=folder/'gpu-transcription.log'
    with log_path.open('wb') as log:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker',str(source),str(folder)],stdout=log,stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if cancel.is_set():raise AnalysisCancelled()
                try:
                    info=json.loads(state.read_text(encoding='utf-8'))
                    if info['stage']=='transcribing':
                        import re
                        with log_path.open('rb') as progress_log:
                            progress_log.seek(info.get('log_offset',0));tail=progress_log.read()[-3000:].decode('utf-8',errors='replace')
                        matches=re.findall(r'(\d+)%',tail)
                        on_progress(int(matches[-1]) if matches else 0,'Transcribiendo con CUDA')
                    else:on_progress(0,'Cargando Whisper en GPU (primera descarga ~460 MB)')
                except (OSError,ValueError,KeyError):pass
                time.sleep(.5)
            if process.returncode:
                try:reason=json.loads(state.read_text(encoding='utf-8')).get('error','Revisa gpu-transcription.log')
                except (OSError,ValueError):reason='Revisa gpu-transcription.log'
                raise ValueError('La transcripción CUDA falló: '+reason)
            return json.loads(output.read_text(encoding='utf-8'))
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()


def worker(source,folder):
    folder=Path(folder);state=folder/'gpu-transcription-state.json'
    def save(info):
        temp=state.with_suffix('.tmp');temp.write_text(json.dumps(info),encoding='utf-8');temp.replace(state)
    try:
        import torch,whisper
        if not torch.cuda.is_available():raise ValueError('PyTorch no detecta CUDA. Actualiza el driver NVIDIA e instala PyTorch CUDA 12.8.')
        save({'stage':'loading'})
        model=whisper.load_model('small',device='cuda',download_root=str(folder.parent/'models/whisper-torch'))
        log=folder/'gpu-transcription.log'
        save({'stage':'transcribing','log_offset':log.stat().st_size if log.exists() else 0})
        result=model.transcribe(str(source),word_timestamps=True,verbose=False,fp16=True)
        transcript=[dict(start=float(s['start']),end=float(s['end']),text=s['text'],words=[dict(start=float(w['start']),end=float(w['end']),text=w['word']) for w in s.get('words',[])]) for s in result['segments']]
        (folder/'gpu-transcript.json').write_text(json.dumps(transcript,ensure_ascii=False),encoding='utf-8')
        save({'stage':'done'})
    except Exception as e:
        save({'stage':'error','error':str(e)[:1500]});raise SystemExit(1)

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--worker':worker(sys.argv[2],sys.argv[3])
