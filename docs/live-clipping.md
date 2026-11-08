# Clipping en vivo (prototipo)

Sigue un directo **público** de YouTube Live o Kick y propone clips mientras la transmisión continúa.

## Cómo funciona

| Etapa | Qué hace |
|---|---|
| Captura | yt-dlp obtiene la señal HLS pública; FFmpeg la copia, sin recodificar, en fragmentos de 10 s. YouTube envía audio y video por separado; Kick, juntos. |
| Supervisor | Si se corta la conexión, vuelve a pedir el directo (las URL de YouTube caducan) con espera progresiva de 2 a 60 s. Los reinicios se marcan como huecos y ningún momento los cruza. Si el directo termina, la sesión se cierra sola. |
| Procesamiento | Cada fragmento se transcribe y se mide su volumen. Los tiempos son los de la sesión. |
| Detección | Cada ~2 min de directo, la IA local revisa los últimos ~5 min con el mismo analista que los videos. Sin IA, usa picos de volumen sostenidos, con etiquetas neutras y sin títulos inventados. |
| Momentos | Cada momento se recorta enseguida a su propio MP4, con 3 s de margen. «Abrir en el editor» lo convierte en un trabajo normal con transcripción y un clip, así que tiene subtítulos, título, 9:16, vista ampliada y exportación. |
| Persistencia | El estado se guarda en `data/live/<id>/state.json` cada 30 s. Si la app se cierra, la sesión queda como «Interrumpida», con sus momentos y la opción de reanudar. |

Solo hay una sesión en vivo a la vez.

## Diferencias con el análisis de videos

En vivo, el filtro de propuestas usa `repair=True`:

- Una cita casi literal, con al menos un 85 % de coincidencia sobre el mismo número de palabras, cuenta como respaldada. Una paráfrasis o una cita inventada siguen rechazándose.
- Si la cita existe en la ventana pero queda justo fuera del clip, el clip se amplía para incluirla, siempre que no supere la duración máxima.
- Una duración fuera del rango se ajusta con frases completas, en lugar de descartar el momento.

El análisis de videos no usa estos ajustes; hay una prueba que lo verifica.

## Mediciones (RTX 5060 Ti 8 GB, Ryzen 7 5700X, 8 de noviembre de 2026)

| | YouTube Live (DW Español) | Kick (destiny) |
|---|---|---|
| Primer fragmento | 2,5–5 s | 6 s |
| 90 s capturados | 0 huecos | 0 huecos |
| Disco en 720p | ~0,4–0,5 GB/h | ~1,6 GB/h |
| Transcripción de 10 s | 0,4 s en GPU, ~1,2 s en CPU | 0,5 s en GPU, 3,5 s en CPU |

**Prueba de 8 minutos con DW Español**, después de las correcciones de detección:

- 3 momentos, propuestos entre 1,5 y 3,5 min después de ocurrir.
- 0 reconexiones.
- Al detener se conservaron los 3 clips, se borraron los fragmentos temporales y no quedó ningún FFmpeg activo.

La primera prueba, antes de las correcciones, detectó 0 momentos. Al repetir el análisis sobre esa misma transcripción, la tasa de propuestas aceptadas pasó de 2 a 6 en 6 rondas.

En vivo, la transcripción usa la CPU mientras la IA local ocupa la GPU, porque los dos modelos juntos no caben con margen en 8 GB.

## Límites conocidos

- **No hay latencia cero.** Un momento necesita su contexto posterior más una ronda de análisis, así que llega entre 1,5 y 5 min después de ocurrir.
- **El retraso frente al directo no se midió de forma fiable:** las marcas de tiempo de las plataformas dieron valores imposibles.
- **Solo se admiten directos públicos.** Directos con inicio de sesión, solo para miembros, con restricción de edad o región, o con DRM se rechazan. No se intenta evitarlos.
- **La exportación automática aún no está:** los momentos quedan como borradores para revisar.
- **Todavía no hay pruebas largas.** Las sesiones de varias horas, los cortes de red reales y los cambios de resolución están cubiertos por la lógica del supervisor y por pruebas simuladas, pero falta una prueba real de varias horas.
- **Solo hay detección por audio y transcripción.** No hay análisis visual ni del chat.
- **La responsabilidad es del usuario:** debe respetar los derechos del creador y las normas de cada plataforma. La interfaz lo indica.
