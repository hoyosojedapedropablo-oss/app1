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

## Integración Cobalt preparada (17 de octubre)

Ver `docs/cobalt-service.md`. Existe un adaptador opcional, servicio Compose propio
y puente a BgUtils. Las imágenes oficiales fijadas se descargaron y los tres
componentes superaron sus comprobaciones de disponibilidad. Las pruebas de la app
(92) y del puente (2) pasan; incluyen transferencia de MP4 generado a registro real
del editor con transporte simulado. No confundirlo con acceso real a YouTube.

El intento real de `JCcuOv5y_9g` en modo rápido devolvió `error.api.fetch.fail` /
`YT-SERVICIO`. La comprobación HTTPS separada sigue fallando en el proxy con 403,
mientras PyPI responde 200. `manage.py activate` rechazó la validación incompleta;
`enabled` permanece falso. No se probó repetidamente el resto tras el primer fallo.
No hay descarga real validada ni nueva actualización que el usuario deba instalar.
El siguiente paso externo es disponer de un entorno de ejecución con acceso real
funcional a YouTube para completar las cuatro descargas y revisar los MP4.

La comprobación directa del proveedor anónimo devolvió HTTP 503; el puente reportó `attestation_ready:false`. Las instrucciones de arranque opcionales se guardaron en el borrador del entorno, sin cambiar la política de red ni publicar la configuración.

## Diagnóstico Windows posterior a la recuperación de bloques (18 de octubre)

El informe del usuario muestra la petición fallida real: HTTP 403 para
`15274496–15340031`, tras tres renovaciones de enlace, sin recibir cuerpo.
No confundirlo con un socket transitorio ni con el rechazo de red del entorno
cloud. El contador del cliente refleja 14 680 064 bytes entregados en bloques
HTTPX de 1 MiB; el lector interno había avanzado hasta 15 274 496. No son dos
fallos distintos. Los tres contenedores seguían activos, sin OOM.

La ruta rápida de Cobalt usa IOS y `useSession=false` para 1080p. Que el proveedor
esté sano no establece que esa petición use su atestación. El código vigente de
yt-dlp (`yt_dlp/extractor/youtube/_base.py`, cliente `ios`) declara POT requerido
para HTTPS, con excepción cuando se aporta token de player. Esto plantea una
hipótesis de compatibilidad de cliente/atestación, no prueba la causa exacta.
No adjuntar un token web a IOS ni cambiar clientes a ciegas.

`services/cobalt/diagnose_access.py` es una comparación de lectura, independiente
por proceso, entre la ruta IOS predeterminada y las rutas WEB_EMBEDDED/WEB con la
sesión anónima de la instancia. La separación evita contaminar el visitor_data
con la primera sesión cacheada de Cobalt. La calidad 2160 se usa únicamente como
selector del flujo de sesión del extractor fijado; no modifica la app ni habilita
calidades. Muestrea 64 KiB por pista al inicio, en el punto de corte observado y
a mitad del archivo; verifica rango, bytes y tipo de medio. No descarga el video
completo y ningún muestreo puede habilitar el servicio. Solo guarda presencia de
parámetros y datos numéricos/enumerados, nunca URLs, tokens o logs sin filtrar.
Resultado esperado: `DIAGNOSTICO_ACCESO.json`. Pendiente de ejecutarse en Windows.

## Comparación recibida y candidato nativo (18 de octubre)

`DIAGNOSTICO_ACCESO.json` confirma IOS: comienzo 206 con rango válido en ambas
pistas; punto 15 274 496 y mitad de ambas pistas 403, sin cuerpo; sin parámetros
`pot` ni `n` en las URLs. WEB_EMBEDDED devuelve `content.video.unavailable`;
WEB registra `extraction_ok:false` sin categoría adicional. No afirmar que se
ha probado un bloqueo de IP ni que el video realmente sea privado. Ningún método
comparado confirmó una transferencia completa.

El puente Cobalt solicita `/get_pot` con cuerpo vacío. La integración oficial
BgUtils para yt-dlp transmite en cambio challenge, content_binding e
innertube_context desde la solicitud. No es válido asumir que el token genérico
de Cobalt satisface la vinculación de un cliente diferente.

`services/cobalt/test_native_download.py` prepara una prueba experimental con
cliente mweb y complemento oficial 2.0.2, mismo proveedor ya instalado. Agrega
solo ese wheel a la venv actual si falta, fija y verifica SHA-256 del artefacto
PyPI antes de instalar sin dependencias. No actualiza yt-dlp ni cambia el backend
configurado de la app. Rechaza una versión de plugin diferente ya instalada.

No publica puertos de Docker ni modifica Compose: un relay HTTP temporal ligado
a loopback con ruta aleatoria rechaza Origin, rutas arbitrarias y desactivación
TLS. Pasa cuerpos JSON por stdin a `deno eval` del proveedor fijo mediante
`docker exec`. Conserva challenge/context/binding del complemento; tokens solo
en memoria, nunca en reportes o logs. El relay se cierra al terminar.

La prueba descarga ambos videos completos, uno a uno, hasta1080p H264/AAC; usa
la duración e identidad extraídas del original y `_verify_media` antes de aceptar
cada MP4. Elimina nuevos parciales al fallar y no activa el servicio. Registra
fases, categorías y contadores seguros en `RESULTADO_DESCARGA_NATIVA.json`.
No usa cuentas, cookies de navegador ni instancias públicas de terceros.

Comprobado localmente: wheel SHA/carga automática real del plugin, transporte
stdin/JSON en Deno de la imagen fijada sin red, seis pruebas de relay/protecciones,
identidad/duración, checksum y rechazo de parciales. La comprobación HTTPS directa
a YouTube desde cloud vuelve a fallar en el proxy con 403 antes de YouTube.
La descarga completa con este candidato queda pendiente en Windows; no llamarlo
solución ni habilitarlo sin el resultado real y revisión de los MP4.
