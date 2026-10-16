# Clip Studio · Editor 2.2 · GPU

Aplicación personal para transformar videos largos en clips verticales. FastAPI, FFmpeg, Whisper para transcripción y análisis editorial local con GPU (Ollama/Qwen2.5), CPU opcional o API en nube. El modo GPU no requiere una clave ni genera cargos de API.

## Windows

1. Instala Python **3.12 de 64 bits** y FFmpeg (`winget install --id Gyan.FFmpeg -e`).
2. Extrae el ZIP de este repositorio y ejecuta **INICIAR_WINDOWS.bat**.
3. Deja abierta la ventana de comandos. El navegador se abre cuando el servidor responde.

### GPU local en Windows (RTX 5060 Ti / 8 GB)

1. Mantén actualizado el driver NVIDIA.
2. Ejecuta **INSTALAR_GPU_WINDOWS.bat**. Instala Ollama y descarga `qwen2.5:7b` (~4,7 GB). El ayudante verifica memoria GPU usada por el modelo: tener instalado Ollama no basta.
3. Opcional, para acelerar también la transcripción: ejecuta **INSTALAR_TRANSCRIPCION_GPU_WINDOWS.bat**. Instala PyTorch CUDA 12.8 (2.7 o posterior) y openai-whisper, y realiza una operación real en CUDA. Descarga varios GB una sola vez.
4. Ejecuta **INICIAR_WINDOWS.bat**, elige **Local GPU**, y pulsa **Comprobar GPU**. Debe indicar GPU activa y memoria asignada.
5. Activa **Transcribir también con GPU** si instalaste ese componente. Cuando ya existe una transcripción completa se reutiliza sin repetir el audio.

La documentación oficial de [Ollama v0.12 sobre GPUs](https://github.com/ollama/ollama/blob/v0.12.0/docs/gpu.md) enumera la RTX 5060 Ti. Se usa Ollama actualizado, no el antiguo wheel CPU de llama-cpp-python. El modelo se guarda normalmente en `%USERPROFILE%\.ollama\models`; no se copia automáticamente desde los GGUF del motor CPU anterior. Los pesos PyTorch Whisper están en `data/models/whisper-torch` y se verifican con el mecanismo original de Whisper.

Ollama atiende únicamente la conexión local `127.0.0.1:11434` de esta app. Los textos no se envían a OpenAI en este modo. Se procesa un bloque por vez para evitar varias copias del contexto en una tarjeta de 8 GB. Las respuestas se leen en streaming para cerrar la solicitud al cancelar. Si el modelo solo está en CPU, la comprobación devuelve un error en lugar de iniciar silenciosamente otro análisis lento.

La transcripción CUDA corre en un proceso separado. La app descarga el modelo de Ollama de la GPU antes de transcribir y lo carga de nuevo cuando termina; al salir el proceso de transcripción se libera su VRAM. Así Whisper y Qwen no se mantienen juntos en la tarjeta. La transcripción CPU optimizada sigue disponible si no instalas el componente CUDA.

**Validación pendiente en hardware del usuario:** este entorno no dispone de una RTX 5060 Ti ni Windows. Las pruebas de integración con Ollama usan respuestas simuladas y comprueban el protocolo, la memoria reportada, el aislamiento del modo local y la cancelación. No prueban velocidad ni kernels CUDA reales. El instalador de transcripción comprueba CUDA en tu PC y Comprobar GPU verifica el modelo en Ollama; después hay que medir un video real. No se promete un tiempo fijo.

### Alternativas

**Local CPU:** INSTALAR_IA_LOCAL.bat instala el motor opcional. Preciso usa Qwen 7B y puede ser muy lento; Ligero usa Qwen 3B con menor calidad. No necesita API.

**Nube:** se conserva como opción explícita. Configurar IA rápida permite introducir una clave en memoria; necesita saldo de API independiente de ChatGPT Plus y envía transcripción/contexto a OpenAI. `CLIP_AI_KEY` o una `OPENAI_API_KEY` existente también son compatibles. El modo GPU nunca usa estas claves ni hace solicitudes al proveedor.

Los videos y trabajos se recuperan tras reiniciar desde **Reutilizar un video guardado**. Copia tu carpeta `data` al actualizar para conservar la transcripción de tu intento anterior.

## Usar

- Carga un video de hasta **120 minutos / 12 GB**.
- Escribe el contexto de ese video, identifica al hablante si lo conoces y elige el rango de duración.
- Guarda criterios y ejemplos de tu canal si quieres orientar el estilo editorial.
- El analista evalúa el contexto y compara posibles historias, exige evidencia literal, puntúa gancho, remate, novedad, emoción y conversación. Identifica los destacados y busca cubrir el 75% de los segundos únicos con conversaciones completas. Prioriza no mezclar temas ni cerrar en una pregunta sin respuesta; si el rango lo impide, muestra una cobertura menor en vez de forzar el porcentaje. La cantidad se calcula automáticamente, respetando el rango. Todos reciben títulos; Mayor potencial distingue los destacados. Puede haber solapamientos en los bordes para respetar el mínimo, pero no cuentan doble en la cobertura. Un video más corto que el mínimo requiere reducir ese mínimo.
- En el editor, cambia entre **Título, Subtítulos, Logo y Encuadre**. La descarga queda visible en escritorio. Arrastra las capas o usa sus controles de posición/tamaño.
- Los títulos automáticos tienen hasta 80 caracteres y 14 palabras. Los manuales aceptan hasta 96 caracteres y se ajustan a un máximo de dos líneas. Fondo y texto editables; permanecen durante todo el clip.
- Los subtítulos comparten la misma lista de frases con tiempos relativos al clip en la vista previa y el MP4. Se dividen en frases cortas, respetan silencios y permiten editar texto y tiempos. Si cambias mucho la transcripción, revisa el ajuste de las palabras nuevas.
- Carga cualquier logo PNG/JPG/WebP de hasta 5 MB. Ajusta ancho, posición y segundos de aparición, por ejemplo 2→final o 10→20. El PNG transparente es preferible. Las opciones Kick/Roobet/Rainbet requieren tus archivos; no se incluyen logos oficiales.
- Las fuentes Montserrat, Poppins, Anton, Bebas Neue, Oswald y Barlow Condensed están incluidas con sus licencias SIL OFL. Título y subtítulos tienen fuentes independientes. Los contornos de título y subtítulos admiten color y grosor; el título permite cambiar color y margen del fondo.
- Exportación MP4 **1080×1920**, H.264 CRF18, AAC192k y 24–60 fps según la fuente. Se conserva el detalle disponible, sin recuperar información ausente. El encuadre por defecto llena 9:16, con posición ajustable. Las bandas son opcionales.

## Linux / entorno de nube

Se necesitan Python 3.12, FFmpeg/ffprobe, acceso a PyPI y Hugging Face para la transcripción, y Ollama con un modelo instalado para el modo GPU; api.openai.com se necesita únicamente para la opción en nube. El motor local es opcional: necesita GCC/G++ para compilar llama-cpp-python desde requirements-local.txt en este entorno glibc.

```bash
cd /workspace/app1
python -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
HF_HOME=/workspace/app1/data/models .venv/bin/python iniciar.py
```

`iniciar.py` escucha solo en 127.0.0.1. Para uso en el entorno aislado de nube puede iniciarse con `.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000`. Esta aplicación **no tiene autenticación**; no debe exponerse a Internet sin protección.

`WHISPER_MODEL` permite cambiar el modelo de transcripción. `EDITORIAL_MODEL_PATH` permite usar tu propio GGUF compatible en lugar de los modelos fijados; en ese caso tú eres responsable de verificar su origen e integridad. Los modelos y datos no se suben a GitHub.

## Validación

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Las pruebas en nube usan transporte HTTP simulado: comprueban paralelismo, datos enviados, cancelación y manejo de saldo/límites; no prueban acceso a una cuenta real ni latencia del proveedor. Las pruebas GPU usan un transporte Ollama simulado y no establecen rendimiento de hardware real. Las pruebas de video ejercitan exportaciones reales, duración máxima y mínima, subtítulos a lo largo del clip, ausencia de solapamientos, posición/intervalo del logo, composición tipográfica y verificación de evidencia/títulos. No descargan el modelo editorial durante la suite rápida.

Validación editorial LOCAL opcional, con requirements-local.txt y los modelos instalados (puede tardar varios minutos):

```bash
HF_HOME=/workspace/app1/data/models .venv/bin/python tests/validate_local_ai.py
```

Esta usa transcripciones sintéticas, no se presenta como una prueba de viralidad. La transcripción de audio hablado real y la interfaz se validaron por separado en el entorno de desarrollo. No se ha validado el video real del usuario de 18 minutos porque no está disponible en este entorno.

## Límites

La IA analiza texto y contexto proporcionado: no interpreta gestos visuales ni conoce métricas de engagement del público. Puede equivocarse en interpretación, puntuación y títulos. Las puntuaciones son estimaciones editoriales, **no probabilidades de viralidad**; revisa antes de publicar. El encuadre incluye seguimiento asistido de rostros y movimiento de boca; requiere revisión. Los trabajos y videos se recuperan desde metadatos o archivos fuente al reiniciar; transcripciones completas, logos, criterios y exportaciones permanecen en `data/` hasta que los elimines. Reanalizar el mismo trabajo reutiliza la transcripción completa. Las exportaciones son síncronas, para uso personal, no para muchos usuarios concurrentes.

## Actualizar sin perder tus datos

Cierra la app con Ctrl+C. Conserva tu carpeta anterior. Descarga el ZIP nuevo en una carpeta nueva y ejecuta INICIAR_WINDOWS.bat. Si necesitas conservar logos/modelos, copia la carpeta `data` anterior a la nueva con la app cerrada. No copies la `.venv` antigua: el iniciador instalará el entorno adecuado.

Los logos pueden ocupar del 5% al 100% del ancho, conservando su proporción y una altura máxima del 75% del cuadro. La generación de títulos para más clips requiere más inferencias; no se garantiza una duración fija.

### Importar videos

Puedes ingresar un archivo descargado o abrir «O pegar enlace de YouTube» y pulsar «Descargar y agregar video». La descarga sucede en el equipo donde corre la app, conserva video y audio y registra el resultado en los videos guardados para analizarlo o editarlo. Se admite un video individual público por descarga, hasta 120 minutos y 12 GB; se elimina el parámetro de playlist. Los directos en curso no se importan. El progreso se consulta sin bloquear la interfaz. Los archivos parciales se eliminan si falla.

La función utiliza yt-dlp y FFmpeg, instalados por INICIAR_WINDOWS. YouTube puede bloquear videos o requerir inicio de sesión; en ese caso se muestra un error y se conserva la alternativa de archivo. Las sesiones del navegador solo se usan si el usuario elige expresamente esa opción; la descarga pública es la predeterminada. Si YouTube cambia su acceso, actualiza yt-dlp en la venv con `python -m pip install --upgrade "yt-dlp[default,deno]"`. El recorrido de importación se verifica con un proveedor simulado y un MP4 real; la red del entorno de desarrollo bloqueó la prueba directa de YouTube con HTTP 403.

La importación de YouTube ofrece «Rápida · hasta 1080p» por defecto y «Máxima disponible» para conservar la resolución superior de origen. La descarga usa hasta ocho fragmentos simultáneos cuando el formato lo permite y peticiones HTTP de 10 MiB; no se recodifica el video al importar. Se muestra una tarjeta con portada, título, canal, duración, progreso y velocidad. Los videos ya guardados se reutilizan al solicitar el mismo enlace y calidad. La mejora de velocidad real depende del formato, YouTube y la conexión; no se ha medido contra YouTube desde el entorno bloqueado.

### Títulos narrativos y seguimiento del hablante

El título cuenta lo que el hablante explica, revela, aclara o promete, con contexto y un detalle concreto. El tono puede ser fuerte; las afirmaciones deben estar respaldadas por el clip. «Mejorar títulos de este clip con IA» genera propuestas desde la transcripción del fragmento y el contexto guardado, sin repetir el análisis completo. Usa el motor elegido en el análisis; por defecto GPU local, sin API. Los títulos se equilibran en dos líneas (si hay dos o más palabras) y se reduce la fuente cuando hace falta; los subtítulos conservan sus propios saltos y tiempos.

En el editor, abre Encuadre y activa «Seguir a quien habla». Se analizan solo los segundos del clip: detección frontal y de perfil, asociación de rostros, movimiento relativo de boca y presencia de voz con Silero VAD. La cámara favorece un cambio sostenido, suaviza el movimiento y mantiene el último encuadre si no hay una señal clara. No es identificación de voces ni diarización; los perfiles difíciles, oclusiones, música y conversaciones simultáneas requieren revisión. Si no encuentra rostros, muestra un error y permite el encuadre manual. No se garantiza la identificación correcta de cada hablante.

El recorrido se guarda en `data/<video>/tracking-<rango>.json`, se reutiliza para el mismo rango y se aplica tanto a la vista previa como al MP4 mediante comandos temporizados de FFmpeg. Cambiar inicio/final requiere calcular otro recorrido. Al exportar varios clips con seguimiento se preparan los recorridos necesarios antes de renderizar. El seguimiento usa CPU con OpenCV headless y no descarga modelos adicionales de reconocimiento de identidad. Las pruebas incluyen un MP4 real con recorte móvil, un rostro de muestra real y una secuencia controlada de movimiento de boca con etiquetas de voz simuladas; no equivalen a validar todos los podcasts.

Si una descarga de YouTube falla, el mensaje incluye un código que diferencia problemas de red/proxy, JavaScript, acceso 403, sesión, edad, región, formatos, FFmpeg y espacio en disco. No se muestran URLs firmadas ni datos de autenticación del proveedor. La instalación usa `yt-dlp[default,deno]`, con EJS y Deno compatibles; la ruta del runtime se pasa explícitamente a yt-dlp, por lo que no depende del PATH de Windows. `REPARAR_YOUTUBE_WINDOWS.bat` actualiza ese conjunto en la venv y verifica versiones, compatibilidad del runtime y presencia de FFmpeg, sin tocar videos ni modelos. Cierra la app antes de ejecutarlo y vuelve a abrir INICIAR_WINDOWS después. El uso de una sesión de navegador es opcional y explícito; no elude restricciones de cuenta o edad. La red de este entorno bloqueó también la comprobación del enlace JCcuOv5y_9g con un error de proxy 403; no se ha confirmado su descarga desde Windows.

### Fondo ajustable, títulos humanos y cortes por tema

En Título → Fondo del título hay dos márgenes medidos en píxeles del archivo exportado: lados (0–100) y arriba/abajo (0–70). Los controles aceptan deslizador y rueda del ratón. El margen cero se mide desde los píxeles reales de las letras, incluyendo el contorno. La misma capa PNG a resolución completa se usa en la vista previa y en el MP4, evitando diferencias de fuente o de tamaño del rectángulo. La paleta incluye blanco, negro, amarillo, amarillo anaranjado, naranja, rosado, fucsia y rojo, además de colores personalizados de fondo y texto. Elegir negro cambia el texto a blanco automáticamente en el editor.

La guía editorial evita la fórmula repetida «X explica/revela», busca una duda concreta, tensión, identificación humana o contraste presente en TODO el clip, y permite que el título se refiera al tema más interesante del final. No debe inventar hechos ni conflictos. El análisis de GPU/API pide un mapa de temas dentro de la misma solicitud de selección; una pregunta y su respuesta del mismo asunto van juntas. Los cortes de cobertura se realizan dentro de esos temas y en finales de frases completas. Si la IA no devuelve mapa, se utilizan pausas y cambios explícitos de conversación como ayuda; esto no garantiza detectar toda transición semántica. Un tema menor que el mínimo o una respuesta que exceda el máximo puede requerir ajustar el rango. No se unen asuntos diferentes para completar a la fuerza el 75%.

Para reducir trabajo, se genera un título principal por clip en lotes de hasta seis (limitados también por longitud del texto); el botón del editor conserva las tres alternativas bajo demanda. Las respuestas válidas se guardan en `data/<video>/analysis-cache` con huella del motor, entrada completa y versión editorial. Identificadores de clip estables permiten reutilizar también títulos al repetir exactamente el análisis. Cambiar contexto, criterios, rango o transcripción invalida las entradas afectadas. Las pruebas comprueban el ahorro de llamadas (14 títulos en tres lotes y una repetición de análisis sin nuevas inferencias), no establecen una duración en hardware NVIDIA real ni validan la calidad editorial de todos los videos.

### Estado de la conexión de YouTube

La conexión propia de la versión 3.3 fue retirada después de que Google rechazara el inicio de sesión en el PC del usuario. La captura también mostró `--no-sandbox`, añadido por el lanzamiento predeterminado de Playwright. Se eliminó todo el código de lanzamiento automatizado, la dependencia Playwright y el puente de cookies de ese método; no se intenta ocultar la automatización ni eludir el rechazo de Google.

La interfaz vuelve a la descarga pública y no ofrece Conectar YouTube. Los clientes antiguos que intentan conectarse o importar con `managed` reciben HTTP 410. Consultar el estado no abre navegadores ni lee cookies. Si existe el perfil propio anterior, «Eliminar conexión anterior» retira su autorización y elimina solo `data/youtube-session/profile`; cierra antes la ventana antigua. Si Windows impide borrarlo, se informa el fallo y se permite reintentar. Los videos y el perfil habitual del navegador no se eliminan.

**La descarga por enlace de los videos rechazados por YouTube sigue sin resolverse.** Las pruebas anteriores con cookies sintéticas no verificaban la aceptación de Google. No se recomienda volver a intentar ese inicio de sesión ni cambiar de navegador como solución comprobada.
