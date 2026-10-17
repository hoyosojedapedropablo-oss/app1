# Diagnóstico puntual desde el PC del usuario

La política de arranque de este entorno (`/etc/codex/network-policy.json`, versión 1) incluye `youtube.com`, `www.youtube.com` y `*.youtube.com`. Aun así, una conexión HTTPS a www.youtube.com devuelve 403 del proxy Envoy antes de completar CONNECT; una petición HTTP devuelve `Domain forbidden`. PyPI devuelve 200 por la misma ruta. La herramienta `cloud_environment.environment_status` no está disponible en esta sesión, por lo que no se afirma un estado actual `enforced` a partir del archivo de arranque. Este acceso necesita investigación de la plataforma; repetir publicaciones o abrir tareas no ha probado resolverlo.

Para obtener evidencia del PC donde ocurre `YT-SESION`, se preparó `diagnostico-youtube-windows.zip` con dos archivos:

- `diagnosticar_youtube.py`
- `DIAGNOSTICAR_YOUTUBE_WINDOWS.bat`

## Ejecución

1. Extraer el ZIP.
2. Copiar ambos archivos en la carpeta de la instalación actual, junto a `INICIAR_WINDOWS.bat` y la carpeta `.venv` existente.
3. Abrir `DIAGNOSTICAR_YOUTUBE_WINDOWS.bat`. Se puede conservar la app abierta.
4. Compartir el archivo generado `DIAGNOSTICO_YOUTUBE_<id>.json` o una captura del resumen de la ventana.

La prueba no instala paquetes, no cambia versiones, no modifica el importador, no abre navegadores y no lee sesiones personales. Compara solo metadatos públicos, bajo la versión instalada, con las opciones básicas anteriores y las actuales de JavaScript/calidad. No reconstruye la versión histórica de las dependencias ni valida una descarga completa.

Se ejecutan cuatro procesos aislados: dos videos conocidos por dos perfiles. Cada proceso tiene un máximo de 35 segundos. Los registros originales del proveedor y los mensajes de excepciones no se incorporan al informe; tampoco cookies, valores de proxy, URLs firmadas ni rutas personales. El informe contiene versiones, IDs públicos, fase, tiempo, presencia de metadatos y códigos de error. Los informes locales se excluyen de Git.

## Validación realizada

Cuatro pruebas verifican ausencia de acceso a sesiones/descargas, exclusión de información sensible, clasificación de errores y límites de proceso. La herramienta completa también se ejecutó en el entorno de desarrollo: generó el JSON y clasificó las cuatro consultas como `YT-RED`. Ese resultado no diagnostica el PC del usuario.

El script y el BAT se incluyeron en un ZIP cuya integridad se comprobó. El BAT no se ejecutó en Windows desde este entorno Linux. El paquete es una herramienta de diagnóstico, no una corrección de la descarga.
