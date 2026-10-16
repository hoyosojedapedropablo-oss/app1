# Investigación de la importación de YouTube

Fecha: 2026-10-16. Estado: investigación y prueba aislada; no es una descarga resuelta.

## Resultado

La experiencia «pegar enlace → obtener video» es viable sin exigir una extensión o una cuenta de Google a cada usuario. Hay implementaciones públicas de esa arquitectura. La instalación y el mantenimiento de sus motores pertenecen al operador del servicio.

Esto no prueba que el enlace `rcPWJKs5It4` funcione actualmente en esas páginas. No se realizó una descarga aceptada por YouTube durante esta investigación. Tampoco conocemos la implementación interna de páginas comerciales sin código público.

El rechazo «confirma que no eres un bot» no demuestra que la única solución sea autenticar al usuario. La autenticación con Brave/Chrome y el navegador automatizado fueron vías fallidas en este PC. La segunda ya se retiró.

## Implementaciones revisadas

### Cobalt

- [Proyecto y arquitectura](https://github.com/imputnet/cobalt): interfaz web separada de la API de procesamiento; funciona como un proxy de medios.
- [Motor de YouTube](https://github.com/imputnet/cobalt/blob/main/api/src/processing/services/youtube.js): usa YouTube.js/Innertube, selecciona formatos, resuelve el reproductor y contempla clientes y sesiones técnicas. También comprueba disponibilidad, directos y duración.
- [Configuración del servicio](https://github.com/imputnet/cobalt/blob/main/docs/api-env-variables.md): `YOUTUBE_SESSION_SERVER` permite obtener automáticamente PO Token y visitor data. `DURATION_LIMIT` permite imponer 7200 segundos. Estas son opciones del operador, no pasos para cada usuario final.
- [Actualización de sesiones](https://github.com/imputnet/cobalt/blob/main/api/src/processing/helpers/youtube-session.js): consulta el proveedor, valida la respuesta y contempla renovación periódica y distribución a los procesos.
- [API documentada](https://github.com/imputnet/cobalt/blob/main/docs/api.md): recibe una URL y calidad; devuelve un túnel de descarga, un enlace o un error. La instancia pública no autoriza su uso como backend de proyectos ajenos sin permiso. Corresponde alojar una instancia propia o contratar/obtener acceso autorizado.

No se usó su instancia pública, no se solicitaron claves ni se intentó sortear su protección.

### MeTube

- [Proyecto](https://github.com/alexta69/metube): interfaz web para yt-dlp. El usuario pega un enlace y el servidor hace la descarga.
- Permite configurar globalmente opciones y plugins del motor. También documenta casos en que las verificaciones o restricciones requieren cookies: su arquitectura no garantiza acceso universal.

Su ejemplo confirma que yt-dlp puede formar parte de una experiencia sencilla. No basta con envolverlo en un botón para resolver todos los bloqueos.

## Alternativa técnica que falta evaluar en Clip Studio

La [documentación de yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#youtube) recomienda evaluar un cliente `mweb` con proveedor de PO Token cuando los clientes predeterminados fallan.

[BgUtils](https://github.com/LuanRT/BgUtils) implementa partes de la atestación del reproductor y distingue tokens vinculados a contenido y sesión. No necesita, por definición, una cuenta de Google del usuario. El entorno tiene que satisfacer las comprobaciones de Google.

[BgUtils POT Provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider/tree/2.0.2) ofrece una integración mantenida para yt-dlp, con servicio HTTP o script. Advierte expresamente que un PO Token no garantiza superar una restricción de acceso o un bloqueo de la IP.

No se recomienda copiar tokens estáticos, inventar una sesión, instalar un navegador sin sandbox ni prometer que mover la descarga a un servidor la resolverá automáticamente.

## Prueba ejecutada

Preparación aislada, fuera del código de producción:

1. Se obtuvo el proveedor oficial en la etiqueta `2.0.2`, commit `26475e9d3665b972c4aeb83b4dbaafcf64b88438`.
2. Se instalaron sus dependencias con Deno 2.9.7 y `--frozen`, conservando el lockfile y la comprobación TLS. No se alteraron las dependencias de Clip Studio.
3. El script arrancó y respondió `2.0.2` a la comprobación de versión.
4. Se solicitó un token anónimo para el video, usando explícitamente el proxy de red configurado en este entorno. No se usaron cuentas, cookies de navegador ni contraseñas.
5. No se generó un token: falló el acceso a la página inicial tras tres reintentos; la alternativa `/att/get` tampoco proporcionó el desafío BotGuard. El proceso terminó con código 1 y `Could not get BotGuard challenge`.

Las pruebas anteriores del acceso directo a YouTube desde este entorno devolvieron un rechazo 403 del proxy. No se evitó ese proxy. Este resultado impide validar aquí la descarga; no demuestra que el PC del usuario ni un servidor distinto tengan ese mismo bloqueo.

No se añadió este proveedor a producción como una solución supuestamente verificada. No hay nueva versión que el usuario deba instalar como resultado de esta investigación.

## Diseño recomendado y criterio de aceptación

Mantener el flujo de producto: URL → portada/progreso → video listo para analizar.

El operador administra un servicio de descarga que mantiene el extractor, genera y renueva la atestación anónima cuando sea necesaria, controla concurrencia y límites de solicitudes, y entrega el archivo con audio. Puede evaluarse localmente primero o alojarse como servicio; un servidor externo añade costes de operación y transferencia. No se necesita una API de IA de pago para esta función.

Antes de integrarlo o anunciarlo como solución:

1. Ejecutar la prueba del proveedor y del extractor en una máquina con acceso permitido a YouTube, mediante su ruta de red autorizada.
2. Descargar realmente el enlace problemático y varios videos públicos independientes sin cuenta ni extensión.
3. Verificar que el archivo corresponde al video esperado; comprobar video, audio, duración y resolución con FFprobe e importar el MP4 en Clip Studio.
4. Repetir tras reiniciar y renovar los tokens; medir tiempos reales y comprobar fallos sin bucles de reintentos.
5. Comprobar 1080p/original cuando existan, límite de 120 minutos, límite de tamaño, limpieza de parciales y comportamiento ante contenido privado, restringido o no disponible.

**Bloqueo pendiente:** falta una descarga real aceptada por YouTube en la ruta de ejecución prevista. Añadir infraestructura, un adaptador de API o pruebas simuladas no satisface ese criterio por sí solo.
