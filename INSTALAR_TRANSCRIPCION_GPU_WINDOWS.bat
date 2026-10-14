@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Ejecuta INSTALAR_GPU_WINDOWS primero.
 pause
 exit /b 1
)
echo Instalando PyTorch CUDA 12.8 para RTX serie 50. Puede descargar varios GB.
".venv\Scripts\python.exe" -m pip install "torch>=2.7,<3" --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 (
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m pip install "openai-whisper==20250625"
if errorlevel 1 (
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -c "import torch; assert torch.cuda.is_available(), 'CUDA no detectada'; x=torch.ones((8,8),device='cuda'); y=x@x; torch.cuda.synchronize(); print('CUDA verificada:', torch.cuda.get_device_name(0)); import pathlib,json; pathlib.Path('data').mkdir(exist_ok=True); pathlib.Path('data/cuda-transcription-ready.json').write_text(json.dumps({'device':torch.cuda.get_device_name(0),'torch':torch.__version__}))"
if errorlevel 1 (
 echo Actualiza el driver NVIDIA. Si faltan DLL, instala Microsoft Visual C++ Runtime.
 pause
 exit /b 1
)
echo Transcripcion GPU preparada. Reinicia la app y activa Transcribir con GPU.
pause
