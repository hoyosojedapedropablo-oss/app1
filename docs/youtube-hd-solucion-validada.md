# Descarga completa en HD: resultado validado y activación

La prueba Windows de `services/cobalt/test_hd_download.py` terminó correctamente.
El usuario aportó `RESULTADO_DESCARGA_HD.json` y confirmó imagen y sonido correctos
al inicio, en la mitad y cerca del final de ambos videos.

| Video | Duración original | Resolución medida | Códec | Bytes del MP4 |
| --- | --- | --- | --- | --- |
| JCcuOv5y_9g | 3624 s (1:00:24) | 1920 × 1080 | H264 | 978 302 002 |
| rcPWJKs5It4 | 752 s (12:32) | 1920 × 1080 | H264 | 551 524 562 |

Ambos resultados no tienen advertencias. El relay registró cuatro solicitudes,
dos tokens entregados y cero fallos. Versiones: yt-dlp 2026.8.19 y plugin oficial
BgUtils 2.0.2. Los tokens y videos no se guardan en el repositorio.

## Corrección comprobada

BgUtilsHTTP convierte `base_url` a minúsculas al leer su configuración. La ruta
anterior generada por `secrets.token_urlsafe(24)` podía contener mayúsculas; el
servidor la rechazaba antes de invocar al proveedor. La ruta hexadecimal generada
por `secrets.token_hex(24)` conserva 192 bits de aleatoriedad, es compatible con
esa transformación y mantiene el servicio ligado a loopback con rechazo de Origin.

La prueba HD conserva el cliente mweb, EJS/Deno, fragmentos de 1 MiB y selección
H264/MP4 + M4A, pero exige altura 720–1080 sin alternativa progresiva 360p. Después
se comprueban duración completa, audio y paquetes de video, y se mide el MP4
con ffprobe. Ambas dimensiones deben ser al menos 720; no se reescala el archivo.

## Integración de la app

`services/cobalt/integrate_hd.py` vuelve a comprobar ambos archivos del informe
en el PC. Confirma rutas bajo `data/cobalt/hd-validation`, bytes, duración y
resolución real frente al informe. Solo después instala las fuentes fijadas por
commit y SHA-256 y activa `minimum_height:720` en `data/youtube-native.json`.
Conserva los modos existentes: la opción Rápida pasa a exigir HD; original/4K
continúa sin validarse y no se habilita automáticamente.

El instalador respalda fuentes y configuración en `data/hd-integration-backup-*`
y restaura el estado anterior si falla una escritura. No borra MP4 anteriores.
Las modificaciones locales desconocidas se conservan y detienen la actualización.
Tras instalar, hay que reiniciar el servidor con `INICIAR_WINDOWS` para cargar
el código nuevo. El resultado del botón en Windows debe comprobarse después.

`native_import.py` aplica la ruta corregida y el mínimo HD cuando esa configuración
está habilitada. La calidad final mostrada se obtiene de las dimensiones medidas,
no solo del extractor. Si no hay formato accesible de al menos 720p, falla con
mensaje de calidad; no presenta un archivo 360p como HD.

Los dos MP4 HD ya descargados pueden reutilizarse con verificaciones completas.
Los trabajos 360p anteriores no satisfacen la nueva política de caché. La app
persiste `video_width` y `video_height` junto a la marca de descarga completa y
solo reutiliza trabajos que cumplan el mínimo. No modifica ni borra trabajos viejos.

## Respaldo

La etiqueta anterior `youtube-descarga-completa-validada` y el ZIP de 360p se
conservan como referencia de recuperación. La mejora HD se guarda aparte; no se
sobrescribe ese respaldo. Un ZIP de código no incluye datos privados: conservar
en el PC `data`, `RESULTADO_DESCARGA_HD.json` y las dependencias del entorno.

Pruebas locales incluyen reproducción del fallo de ruta con el plugin real,
petición de token a un proveedor de prueba, rechazo de 360p aunque los metadatos
digan 1080p, importación de MP4 720p real al editor, y exclusión de caché 360p.
La evidencia remota válida de HD es el informe Windows y la revisión del usuario;
las pruebas locales no sustituyen esa descarga real.
