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
echo Abre INICIAR_WINDOWS. Usa Local GPU y pulsa Comprobar GPU.
pause
