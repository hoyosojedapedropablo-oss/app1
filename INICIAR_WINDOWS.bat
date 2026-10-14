@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo Instala Python 3.12 desde https://www.python.org/downloads/windows/ y vuelve a abrir este archivo.
 pause
 exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
 echo Falta FFmpeg. Abre PowerShell y ejecuta: winget install --id Gyan.FFmpeg -e
 echo Despues cierra y vuelve a abrir este archivo.
 pause
 exit /b 1
)
where ffprobe >nul 2>nul
if errorlevel 1 (
 echo Falta ffprobe. Revisa la instalacion de FFmpeg.
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
 py -3.12 -m venv .venv
 if errorlevel 1 (
 echo Se necesita Python 3.12. Instala esa version y vuelve a intentarlo.
 pause
 exit /b 1
 )
)
echo Instalando el motor local de analisis para Windows...
".venv\Scripts\python.exe" -m pip install "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.2/llama_cpp_python-0.3.2-cp312-cp312-win_amd64.whl"
if errorlevel 1 (
 echo No se pudo instalar el motor local. Necesita Python 3.12 de 64 bits y acceso a GitHub.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
 echo No se pudieron instalar las dependencias. Revisa el error de arriba y tu conexion.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -c "from llama_cpp import Llama"
if errorlevel 1 (
 echo El motor local no se puede cargar. Puede faltar Microsoft Visual C++ Runtime.
 echo En PowerShell: winget install --id Microsoft.VCRedist.2015+.x64 -e
 echo Despues vuelve a abrir este archivo. Conserva el mensaje de error si persiste.
 pause
 exit /b 1
)
set "HF_HOME=%CD%\data\models"
".venv\Scripts\python.exe" iniciar.py
pause
