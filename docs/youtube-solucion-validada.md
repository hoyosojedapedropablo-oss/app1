# Solución de descarga completa de YouTube conservada

## Qué quedó comprobado

La versión guardada es el commit `498ecc4dae2c1430b088fc9ec31e412f51dfa26d`.
La etiqueta `youtube-descarga-completa-validada` identifica ese código para poder
recuperarlo sin depender del último cambio del proyecto.

En Windows, el usuario descargó y revisó dos archivos completos:

| Video | Duración original verificada | Tamaño del MP4 |
| --- | --- | --- |
| JCcuOv5y_9g | 3624 segundos: 1:00:24 | 247 025 061 bytes |
| rcPWJKs5It4 | 752 segundos: 12:32 | 68 933 234 bytes |

El usuario confirmó el audio y pudo importar el video en el editor desde la página.
Posteriormente informó que otro video nuevo descargaba en 360p. Esa limitación de
resolución es real: no se ha validado todavía una descarga completa en 720p/1080p.

## Configuración que funcionó

- yt-dlp `2026.8.19`, complemento oficial BgUtils `2.0.2`, EJS/Deno y FFmpeg/ffprobe.
- Cliente de extracción `mweb`, sin cookies ni cuentas de Google.
- Una descarga por vez, fragmentos de 1 MiB, dos reintentos, dos reintentos de fragmentos.
- H264/MP4 y audio M4A; mejor calidad disponible hasta 1080p con alternativa progresiva.
- Máximo 120 minutos y 12 GiB; control de duración/identidad del original.
- La integración conserva el relay local al proveedor Docker que estaba presente en
  la prueba. **Los informes registraron cero solicitudes de tokens**: el éxito de
  360p no demuestra que funcionase la atestación ni que Docker fuera necesario.

Selector exacto de formatos:

```text
bestvideo[ext=mp4][vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]
```

El último término permite terminar en 360p cuando los formatos separados no son
accesibles. Eso conserva una descarga completa, pero no equivale a obtener HD.

## Archivos y funciones importantes

- `native_import.py`: implementación activa cuando `data/youtube-native.json`
  contiene `enabled:true`, `verification_version:2` y `enabled_modes:["fast"]`.
- `youtube_import.py`: elige el método nativo antes que Cobalt cuando está activado.
- `cobalt_import.py`, `_verify_media`: usa ffprobe para exigir paquetes y duración
  de video, audio y contenedor dentro de max(2 s, 0,5 %) del original.
- `app.py`: registra la descarga en el editor solo después de verificarla y marca
  `youtube_verification_version:2`. Los trabajos antiguos sin esa marca no se
  reutilizan cuando el método nativo está activo.
- `services/cobalt/test_native_download.py`: prueba que produjo los dos MP4 correctos.
- `services/cobalt/integrate_native.py`: instalador fijado a fuentes y SHA-256,
  comprueba el informe y ambos MP4, respalda fuentes/configuración y activa al final.
- `docs/youtube-handoff.md`: investigación, pruebas fallidas, límites y seguimiento.

Los dos MP4 de prueba pueden reutilizarse desde `data/cobalt/native-validation`
solo tras comprobar ruta, tamaño y duración; la copia se vuelve a verificar.

## Qué no se debe repetir

Los primeros archivos de unos 64 segundos eran incompletos. Sus antiguos mensajes
OK quedaron invalidados: no prueban funcionamiento ni sirven para activar nada.
Cobalt/IOS permitió leer el inicio y rechazó rangos posteriores con HTTP 403,
incluso tras tres renovaciones. No basta recibir 64 KiB, una miniatura o estado
HTTP 200 para considerar descargado un video completo.

No volver a lanzar navegadores automatizados para iniciar sesión en Google,
extraer cookies sin autorización, desactivar TLS o usar instancias públicas ajenas.
No atribuir al PC del usuario los rechazos del proxy del entorno de desarrollo.

## Respaldo y recuperación

El archivo `ClipStudio-descarga-completa-validada.zip` contiene el código de la
versión indicada, esta guía y un manifiesto SHA-256 de archivos clave. No incluye
videos, modelos, la venv, claves ni datos privados. Se genera desde Git, no copiando
carpetas de credenciales. No es necesario instalarlo para continuar usando la app.

Para recuperar el estado de funcionamiento del PC también hay que conservar,
en un respaldo privado del propio usuario:

- La carpeta `data`, especialmente `data/youtube-native.json` y los MP4 verificados.
- `RESULTADO_DESCARGA_NATIVA.json`, usado por el instalador para validar la activación.
- El entorno `.venv` o las dependencias instaladas desde `requirements.txt`.

Restaurar solo el ZIP en una carpeta vacía no recupera esos datos. No borrar ni
reemplazar `data` al recuperar el código. Después de restaurar fuentes, reiniciar
el servidor con `INICIAR_WINDOWS` desde la misma carpeta. Mantener Docker y sus
servicios disponibles mientras se use esta versión, hasta validar su retirada.

## Mejora de calidad en curso

La calidad de imagen influye en la experiencia del espectador, pero no determina
por sí sola las recomendaciones de redes sociales. Para recortar y ampliar clips,
conviene partir de 720p/1080p reales; aumentar artificialmente los píxeles de un
archivo 360p no recupera el detalle que falta.

Se encontró una incompatibilidad local reproducible: BgUtils HTTP 2.0.2 convierte
`base_url` a minúsculas. El relay original usa una ruta aleatoria con posibles
mayúsculas, por lo que no coincide y devuelve 403 antes de invocar al proveedor.
La prueba HD separada usa una ruta aleatoria hexadecimal en minúsculas. Las
pruebas con el complemento real confirman que ahora alcanza el relay y conserva
la vinculación de la solicitud.

`services/cobalt/test_hd_download.py` exige al menos 720p tanto en la selección
como en la resolución medida del MP4; verifica además audio y duración completos.
Guarda los resultados aparte (`data/cobalt/hd-validation` y
`RESULTADO_DESCARGA_HD.json`). No activa HD ni modifica el importador instalado.
Una prueba local del relay no demuestra aceptación remota de YouTube; esta mejora
solo podrá integrarse después de descargar y revisar un archivo HD completo real.
