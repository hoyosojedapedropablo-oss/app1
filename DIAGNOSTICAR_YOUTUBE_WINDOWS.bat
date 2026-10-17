@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Copia estos dos archivos en la carpeta de la app que ya tiene .venv.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" diagnosticar_youtube.py
if errorlevel 1 echo No se pudo completar el informe. Conserva una captura del mensaje.
pause
