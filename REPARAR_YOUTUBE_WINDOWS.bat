@echo off
setlocal
cd /d "%~dp0"
echo Cierra la ventana de Clip Studio antes de continuar.
echo Se actualizaran yt-dlp, EJS y Deno dentro de la app.
if not exist ".venv\Scripts\python.exe" (
 echo Primero abre INICIAR_WINDOWS para instalar la app.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade "yt-dlp[default,deno]>=2026.8.19"
if errorlevel 1 (
 echo No se pudo actualizar. Revisa el error anterior y tu conexion.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" youtube_import.py --check
if errorlevel 1 (
 echo No se pudieron verificar los componentes. Conserva una captura de este mensaje.
 pause
 exit /b 1
)
echo Abre INICIAR_WINDOWS y vuelve a probar el enlace.
pause
