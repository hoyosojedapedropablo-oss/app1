# Clip Studio · Editor 2.1

Aplicación personal para transformar videos largos en clips verticales. FastAPI, FFmpeg, Whisper para transcripción y análisis editorial en nube (OpenAI) o local (Qwen2.5). El modo rápido requiere clave de API y saldo.

## Windows

1. Instala Python **3.12 de 64 bits** y FFmpeg (`winget install --id Gyan.FFmpeg -e`).
2. Extrae el ZIP de este repositorio y ejecuta **INICIAR_WINDOWS.bat**.
3. Deja abierta la ventana de comandos. El navegador se abre cuando el servidor responde.

El inicio normal no instala ni descarga un modelo editorial local. Para el modo rápido abre **Configurar IA rápida**, introduce tu clave en la app y verifica la conexión. ChatGPT Plus no incluye saldo de API. La clave introducida queda únicamente en memoria y hay que volver a conectarla tras cerrar la app. También se admite la variable `CLIP_AI_KEY` (o una `OPENAI_API_KEY` existente) del proceso.

En modo nube se envían únicamente la transcripción y el contexto a OpenAI, usando `gpt-4.1-mini`. El video, la transcripción de audio con Whisper y las exportaciones siguen en tu equipo. Los bloques de texto de unos seis minutos se procesan con hasta tres solicitudes concurrentes, sin repetir 16 versiones del mismo texto en cada solicitud ni añadir una segunda pasada editorial por cada clip. Cada solicitud tiene tiempos de espera limitados y no reintenta automáticamente cobros. La velocidad real necesita medirse con tu conexión y cuenta; no se garantiza una duración fija. La transcripción local y la exportación aún dependen de tu hardware.

Para modo local ejecuta **INSTALAR_IA_LOCAL.bat** una vez. Preciso descarga Qwen 7B (~4,68 GB), requiere aproximadamente 16 GB de RAM y puede ser muy lento en CPU. Ligero descarga Qwen 3B (~1,93 GB), con menor precisión. Ambos conservan revisión y SHA-256 fijados. La transcripción usa Whisper small (~460 MB) y reutiliza transcripciones completas guardadas.

Puedes cancelar el análisis en nube; una solicitud ya enviada puede terminar y consumir saldo aunque canceles. Para detener inmediatamente el modelo local, cierra su ventana de comandos. Los videos se recuperan tras reiniciar desde **Reutilizar un video guardado**. Copia tu carpeta `data` anterior al actualizar para conservar el video y su transcripción y evitar repetir trabajo.

## Usar

- Carga un video de hasta **120 minutos / 12 GB**.
- Escribe el contexto de ese video, identifica al hablante si lo conoces y elige el rango de duración.
- Guarda criterios y ejemplos de tu canal si quieres orientar el estilo editorial.
- El analista evalúa el contexto y compara posibles historias, exige evidencia literal, puntúa gancho, remate, novedad, emoción y conversación. Selecciona sin solapamientos, reduce duplicados, limita la cobertura y puede devolver cero clips. Luego revisa los límites y redacta títulos específicos.
- En el editor, cambia entre **Título, Subtítulos, Logo y Encuadre**. La descarga queda visible en escritorio. Arrastra las capas o usa sus controles de posición/tamaño.
- Los títulos automáticos tienen hasta 64 caracteres y 10 palabras. Los manuales aceptan hasta 96 caracteres y se ajustan a un máximo de dos líneas. Fondo blanco y texto negro; aparecen los primeros seis segundos.
- Los subtítulos comparten la misma lista de frases con tiempos relativos al clip en la vista previa y el MP4. Se dividen en frases cortas, respetan silencios y permiten editar texto y tiempos. Si cambias mucho la transcripción, revisa el ajuste de las palabras nuevas.
- Carga cualquier logo PNG/JPG/WebP de hasta 5 MB. Ajusta ancho, posición y segundos de aparición, por ejemplo 2→final o 10→20. El PNG transparente es preferible. Las opciones Kick/Roobet/Rainbet requieren tus archivos; no se incluyen logos oficiales.
- Las fuentes Montserrat, Poppins, Anton, Bebas Neue, Oswald y Barlow Condensed están incluidas con sus licencias SIL OFL. Título y subtítulos tienen fuentes independientes. Los contornos de título y subtítulos admiten color y grosor; el título conserva el fondo blanco.
- Exportación MP4 **1080×1920**, H.264 CRF18, AAC192k y 24–60 fps según la fuente. Se conserva el detalle disponible, sin recuperar información ausente. El encuadre por defecto llena 9:16, con posición ajustable. Las bandas son opcionales.

## Linux / entorno de nube

Se necesitan Python 3.12, FFmpeg/ffprobe, acceso a PyPI y Hugging Face para la transcripción, y acceso a api.openai.com para el modo rápido. El motor local es opcional: necesita GCC/G++ para compilar llama-cpp-python desde requirements-local.txt en este entorno glibc.

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

Las pruebas en nube usan transporte HTTP simulado: comprueban paralelismo, datos enviados, cancelación y manejo de saldo/límites; no prueban acceso a una cuenta real ni latencia del proveedor. Las pruebas de video ejercitan exportaciones reales, duración máxima y mínima, subtítulos a lo largo del clip, ausencia de solapamientos, posición/intervalo del logo, composición tipográfica y verificación de evidencia/títulos. No descargan el modelo editorial durante la suite rápida.

Validación editorial LOCAL opcional, con requirements-local.txt y los modelos instalados (puede tardar varios minutos):

```bash
HF_HOME=/workspace/app1/data/models .venv/bin/python tests/validate_local_ai.py
```

Esta usa transcripciones sintéticas, no se presenta como una prueba de viralidad. La transcripción de audio hablado real y la interfaz se validaron por separado en el entorno de desarrollo. No se ha validado el video real del usuario de 18 minutos porque no está disponible en este entorno.

## Límites

La IA analiza texto y contexto proporcionado: no interpreta gestos visuales ni conoce métricas de engagement del público. Puede equivocarse en interpretación, puntuación y títulos. Las puntuaciones son estimaciones editoriales, **no probabilidades de viralidad**; revisa antes de publicar. El encuadre aún no sigue personas automáticamente. Los trabajos y videos se recuperan desde metadatos o archivos fuente al reiniciar; transcripciones completas, logos, criterios y exportaciones permanecen en `data/` hasta que los elimines. Reanalizar el mismo trabajo reutiliza la transcripción completa. Las exportaciones son síncronas, para uso personal, no para muchos usuarios concurrentes.

## Actualizar sin perder tus datos

Cierra la app con Ctrl+C. Conserva tu carpeta anterior. Descarga el ZIP nuevo en una carpeta nueva y ejecuta INICIAR_WINDOWS.bat. Si necesitas conservar logos/modelos, copia la carpeta `data` anterior a la nueva con la app cerrada. No copies la `.venv` antigua: el iniciador instalará el entorno adecuado.
