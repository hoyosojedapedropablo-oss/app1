# Formato de clips: zoom con franjas, seguimiento facial, títulos y subtítulos

## Configura tus clips

Es una sección de la pantalla de análisis, antes de «Encontrar momentos». Se guarda por proyecto (`job.json → clip_settings`) y se puede cambiar después en el editor sin repetir el análisis.

| Opción | Valores | Predeterminado en proyectos nuevos |
|---|---|---|
| Encuadre | Zoom vertical con franjas negras · Pantalla completa 9:16 (y en el editor también «Video completo con bandas grandes») | Zoom con franjas |
| Intensidad del zoom | Suave (50 % del alto) · Equilibrado (60 %) · Cercano (72 %) | Equilibrado |
| Seguimiento facial | activado / desactivado · movimiento Suave · Equilibrado · Rápido | Activado, Equilibrado |
| Subtítulos | Con · Sin | Con |
| Fondo del título | Esquinas redondeadas · cuadradas | Redondeadas |

- **Proyectos guardados antes** de este cambio no tienen `clip_settings` y conservan su comportamiento: pantalla completa, esquinas cuadradas, sin seguimiento automático y con subtítulos.
- **Los momentos del clipping en vivo** que se abren en el editor reciben los valores nuevos.
- **Sin subtítulos**, la transcripción se sigue usando para encontrar los momentos; solo no se dibuja en el video. Los títulos son independientes.

## Zoom con franjas

Para un video de 1920×1080 con zoom equilibrado:

- la franja de video mide 1080×1152 y deja 384 px negros arriba y abajo;
- se ve ~53 % del ancho original y la imagen apenas se amplía (×1,07), así que no pierde nitidez ni se deforma;
- coincide con la imagen de referencia del usuario: el video ocupa ~59 % del alto.

La vista previa usa la misma geometría que la exportación: `object-fit: cover` con `object-position` dentro de la franja, frente a `scale … increase, crop, pad` en FFmpeg.

## Seguimiento facial v2 (`tracking.py`)

| | v1 | v2 |
|---|---|---|
| Detector | Haar (frontal y perfil) | YuNet (ojos, nariz y boca); no detecta manos ni objetos; descarta caras < 6 % del alto |
| Muestras | 4 por segundo | 8 por segundo |
| Exportación | posición 12 veces por segundo, en escalones | una posición por fotograma de salida |
| Movimiento | saltos de hasta 20 % del ancho | zona muerta, encuadre fijo si la persona cabe, suavizado sin retraso, velocidad máxima según modo, aceleración progresiva |
| Cortes de escena | paneo lento entre tomas | reposición instantánea en el fotograma del corte (FFmpeg `scdet`) y movimiento suave dentro de cada toma |
| Personas | — | «Automático · quien habla» o una persona concreta, ordenadas de izquierda a derecha; une los rastros del mismo rostro |
| Vista previa | se actualizaba unas 4 veces por segundo | se dibuja en cada fotograma con el mismo recorrido que la exportación, redondeado igual (píxeles pares) |

El modelo `models/face_detection_yunet_2023mar.onnx` (232 KB) viene del repositorio oficial `opencv/opencv_zoo` y tiene licencia MIT. SHA-256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`. Si falta, se usa Haar.

### Mediciones (clips reales de 45 s, RTX 5060 Ti / Ryzen 7 5700X)

| Clip | Análisis v1 | Análisis v2 | Salto máximo v1 | Saltos v2 fuera de cortes |
|---|---|---|---|---|
| Westcol (pantalla dividida, 2 personas) | 29,6 s | 10,8 s | 156 px | 0 |
| Podcast, 1 persona | 25,6 s | 8,6 s | 30 px | 0 |
| Podcast, grupo de 3 con cortes | — | 7,5 s | — | 0 |
| Spreen (Kick) | 38,9 s | 8,9 s | 36 px | 0 |

Las pruebas unitarias comprueban:

- velocidad máxima por modo;
- que el encuadre llegue a su velocidad en ≥ 0,5 s (sin saltos);
- zona muerta;
- encuadre fijo;
- salto instantáneo en un corte;
- persona elegida;
- una posición por fotograma, idéntica en la vista previa y en la exportación.

### Equivalencia entre vista previa y exportación

En cuatro instantes de cada clip, cada fotograma exportado se comparó con el recorte que muestra la vista previa (mismo recorrido, misma geometría):

- SSIM de 0,972 a 0,990;
- una referencia sin recortar, recodificada con NVENC, da 0,972, que es el máximo alcanzable por el códec;
- desplazar el recorte 1–2 px baja el SSIM a 0,90.

Así se detectó y corrigió una diferencia de 1 px: FFmpeg recorta `yuv420p` solo en posiciones pares, y ahora la vista previa redondea igual.

## Títulos

`styling.title_bitmap(..., corners='rounded')` dibuja el fondo con radio `min(alto/2, 14 + 0,18·alto)`. Es el mismo PNG en la vista previa y en el MP4. Se conservan los controles de colores, fuente, tamaño, márgenes y posición.

## Límites

- En videos editados con cortes, las «personas» son posiciones de cara a lo largo de las tomas: una misma persona vista desde dos cámaras puede aparecer dos veces.
- «Automático · quien habla» estima al hablante por el movimiento de la boca y la voz; no identifica voces.
- En pantallas divididas (dos paneles en un mismo video), el recorte puede mostrar el borde entre paneles.
- El navegador no dibuja fotogramas mientras su pestaña está oculta; la vista previa fluida se aprecia con la app visible.
