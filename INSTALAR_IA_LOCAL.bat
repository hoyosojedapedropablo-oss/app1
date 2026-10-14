@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Abre INICIAR_WINDOWS primero para crear el entorno.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m pip install "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.2/llama_cpp_python-0.3.2-cp312-cp312-win_amd64.whl"
if errorlevel 1 (
 echo No se pudo instalar el motor local. Revisa el error anterior.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -c "from llama_cpp import Llama"
if errorlevel 1 (
 echo Puede faltar Microsoft Visual C++ Runtime.
 echo En PowerShell: winget install --id Microsoft.VCRedist.2015+.x64 -e
)
pause
