@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo Instala Python 3.12 de 64 bits primero.
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
 py -3.12 -m venv .venv
 if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
 pause
 exit /b 1
)
rem cuBLAS 12 lets faster-whisper transcribe on the NVIDIA GPU (about 20x real time instead of 3x on CPU).
".venv\Scripts\python.exe" -m pip install "nvidia-cublas-cu12>=12.4,<13"
if errorlevel 1 echo No se instalo cuBLAS: la transcripcion seguira en CPU.
rem Whisper large-v3-turbo (~1.6 GB, once): more accurate live subtitles on the GPU. ClipStudio never downloads it by itself.
set "HF_HOME=%CD%\data\models"
".venv\Scripts\python.exe" -c "from faster_whisper.utils import download_model; download_model('large-v3-turbo')"
if errorlevel 1 echo No se descargo large-v3-turbo: el clipping en vivo usara el modelo small.
if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
 where ollama >nul 2>nul
 if errorlevel 1 (
  winget install --id Ollama.Ollama -e --source winget
  if errorlevel 1 (
   echo Instala Ollama desde https://ollama.com/download/windows y vuelve a ejecutar este archivo.
   pause
   exit /b 1
  )
 )
)
".venv\Scripts\python.exe" preparar_gpu.py
if errorlevel 1 (
 echo No se verifico la GPU. Actualiza el driver NVIDIA y Ollama antes de analizar.
 pause
 exit /b 1
)
echo Abre INICIAR_WINDOWS. ClipStudio detecta la GPU automaticamente; revisa el boton Rendimiento.
pause
