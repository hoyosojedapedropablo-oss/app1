# Continuar la reparación de YouTube

## Objetivo pendiente
Descargar videos públicos pegando la URL, sin extensiones, sin pedir cuentas de Google a los usuarios y sin navegadores automatizados para iniciar sesión. No presentar otra actualización como solución hasta completar una descarga real aceptada por YouTube e importar el MP4 en el editor.

## Estado comprobado
- El usuario confirmó que https://www.youtube.com/watch?v=JCcuOv5y_9g funcionó en una versión anterior. También falla https://www.youtube.com/watch?v=rcPWJKs5It4 en sus intentos recientes.
- Se comparó la configuración del importador original (commit 7dadcb8) con la actual, bajo el mismo yt-dlp 2026.8.19 del entorno. Ambas eligieron visionos/web y fallaron antes de obtener metadatos por el proxy del entorno. Esto no reproduce exactamente el PC del usuario ni prueba una regresión de código.
- Google rechazó el inicio de sesión automatizado de la versión 3.3. El lanzamiento usaba el valor predeterminado sin sandbox de Playwright. Ese método, su código de lanzamiento y su dependencia se retiraron. No volver a proponerlo, ocultar la automatización ni desactivar protecciones.
- El usuario revisó y publicó la configuración de red solicitada. La herramienta de lectura confirmó una nueva versión publicada, sin borrador pendiente, que incluye los dominios de YouTube, googlevideo y los destinos de atestación. No volver a pedir que publique lo mismo.
- Después de esa publicación se probaron www.youtube.com y jnn-pa.googleapis.com; el proxy siguió respondiendo Tunnel connection failed: 403 Forbidden. Se repitió el enlace JCcuOv5y_9g tras 30 segundos y persistió el rechazo. Los dominios guardados no demuestran que la sesión de ejecución haya adoptado los accesos.
- yt-dlp 2026.8.19, EJS 0.8.0 y Deno 2.9.7 están instalados y el chequeo local de componentes pasa. Eso no demuestra una descarga real.

## Próximos pasos
1. En una instancia nueva del entorno publicado, comprobar primero la conectividad a YouTube por la ruta de red proporcionada. No evitar el proxy ni interpretar su rechazo como un bloqueo de YouTube al PC del usuario.
2. Si permite acceder, repetir la comparación de metadatos con la configuración original y actual, y comprobar la versión de dependencias. No culpar a una regresión sin observarla.
3. Evaluar la atestación anónima descrita en docs/youtube-download-investigation.md y los clientes compatibles. Cobalt y MeTube sirven como referencias de arquitectura, no como APIs públicas de uso libre ni como prueba de que esos enlaces funcionan hoy.
4. La prueba aislada anterior de BgUtils POT Provider 2.0.2 pudo instalar y arrancar el componente, pero no obtener el desafío BotGuard. El checkout temporal en /tmp no sobrevivió a la publicación; restaurarlo desde la etiqueta oficial si hace falta. Conservar TLS, lockfiles y la ruta de red autorizada. No usar cuentas personales ni registrar cookies o tokens.
5. Validar descarga completa, video y audio, duración, resolución, limpieza de parciales e importación en Clip Studio. Las pruebas simuladas no sustituyen esa validación.

No se ha reparado todavía la descarga del usuario. No hay motivo demostrado para pedirle otra reinstalación de la app.
