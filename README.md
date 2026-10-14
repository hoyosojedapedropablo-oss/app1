# Clip Studio · Editor 2.0

Aplicación personal para transformar videos largos en clips verticales. FastAPI, FFmpeg, Whisper para transcripción y Qwen2.5 local para análisis editorial. No necesita claves de API.

## Windows

1. Instala Python **3.12 de 64 bits** y FFmpeg (`winget install --id Gyan.FFmpeg -e`).
2. Extrae el ZIP de este repositorio y ejecuta **INICIAR_WINDOWS.bat**.
3. Deja abierta la ventana de comandos. El navegador se abre cuando el servidor responde.

El iniciador instala un wheel CPU de llama-cpp-python 0.3.2 desde su repositorio oficial, evitando necesitar un compilador en Windows. Si faltan DLL de Visual C++, muestra el comando para instalar Microsoft Visual C++ Redistributable. El iniciador de Windows aún no se ha ejecutado en una máquina Windows durante esta revisión; se verificaron las pruebas y el navegador en Linux.

La primera transcripción descarga Whisper `small` (~460 MB). El primer análisis descarga Qwen2.5-7B Q4 (~4,68 GB) en modo **Preciso** o Qwen2.5-3B Q4 (~1,93 GB) en modo **Ligero**. Se recomienda **16 GB de RAM** para Preciso. Los modelos quedan en `data/models/`. Funcionan en CPU y el análisis puede ser lento. Los modelos GGUF predeterminados tienen revisión y SHA-256 fijados, verificados antes de cargar.

## Usar

- Carga un video de hasta **120 minutos / 12 GB**.
- Escribe el contexto de ese video, identifica al hablante si lo conoces y elige el rango de duración.
- Guarda criterios y ejemplos de tu canal si quieres orientar el estilo editorial.
- El analista compara posibles historias, exige evidencia literal, puntúa gancho, remate, novedad, emoción y conversación. Selecciona sin solapamientos, reduce duplicados, limita la cobertura y puede devolver cero clips. Luego revisa los límites y redacta títulos específicos.
- En el editor, cambia entre **Título, Subtítulos, Logo y Encuadre**. La descarga queda visible en escritorio. Arrastra las capas o usa sus controles de posición/tamaño.
- Los títulos automáticos tienen hasta 64 caracteres y 10 palabras. Los manuales aceptan hasta 96 caracteres y se ajustan a un máximo de dos líneas. Fondo blanco y texto negro; aparecen los primeros seis segundos.
- Los subtítulos comparten la misma lista de frases con tiempos relativos al clip en la vista previa y el MP4. Se dividen en frases cortas, respetan silencios y permiten editar texto y tiempos. Si cambias mucho la transcripción, revisa el ajuste de las palabras nuevas.
- Carga cualquier logo PNG/JPG/WebP de hasta 5 MB. Ajusta ancho, posición y segundos de aparición, por ejemplo 2→final o 10→20. El PNG transparente es preferible. Las opciones Kick/Roobet/Rainbet requieren tus archivos; no se incluyen logos oficiales.
- Las fuentes Montserrat, Poppins, Anton, Bebas Neue, Oswald y Barlow Condensed están incluidas con sus licencias SIL OFL. Título y subtítulos tienen fuentes independientes. Los contornos de título y subtítulos admiten color y grosor; el título conserva el fondo blanco.
- Exportación MP4 **1080×1920**, H.264 CRF18, AAC192k y 24–60 fps según la fuente. Se conserva el detalle disponible, sin recuperar información ausente. El encuadre por defecto llena 9:16, con posición ajustable. Las bandas son opcionales.

## Linux / entorno de nube

Se necesitan Python 3.12, FFmpeg/ffprobe, GCC/G++ y acceso a PyPI, GitHub y Hugging Face. El wheel Linux del release 0.3.2 requiere musl y no sirve en este entorno glibc, por eso se compila la dependencia desde fuente.

```bash
cd /workspace/app1
python -m venv --system-site-packages .venv
CC=gcc CXX=g++ CMAKE_BUILD_PARALLEL_LEVEL=4 CMAKE_ARGS='-DGGML_NATIVE=OFF' \
  .venv/bin/python -m pip install -r requirements.txt
HF_HOME=/workspace/app1/data/models .venv/bin/python iniciar.py
```

`iniciar.py` escucha solo en 127.0.0.1. Para uso en el entorno aislado de nube puede iniciarse con `.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000`. Esta aplicación **no tiene autenticación**; no debe exponerse a Internet sin protección.

`WHISPER_MODEL` permite cambiar el modelo de transcripción. `EDITORIAL_MODEL_PATH` permite usar tu propio GGUF compatible en lugar de los modelos fijados; en ese caso tú eres responsable de verificar su origen e integridad. Los modelos y datos no se suben a GitHub.

## Validación

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Las pruebas ejercitan exportaciones reales, duración máxima y mínima, subtítulos a lo largo del clip, ausencia de solapamientos, posición/intervalo del logo, composición tipográfica y verificación de evidencia/títulos. No descargan el modelo editorial durante la suite rápida.

Validación editorial opcional, con los modelos instalados (puede tardar varios minutos):

```bash
HF_HOME=/workspace/app1/data/models .venv/bin/python tests/validate_local_ai.py
```

Esta usa transcripciones sintéticas, no se presenta como una prueba de viralidad. La transcripción de audio hablado real y la interfaz se validaron por separado en el entorno de desarrollo. No se ha validado el video real del usuario de 18 minutos porque no está disponible en este entorno.

## Límites

La IA analiza texto y contexto proporcionado: no interpreta gestos visuales ni conoce métricas de engagement del público. Puede equivocarse en interpretación, puntuación y títulos. Las puntuaciones son estimaciones editoriales, **no probabilidades de viralidad**; revisa antes de publicar. El encuadre aún no sigue personas automáticamente. Los trabajos viven en memoria y se pierden al reiniciar; videos, transcripciones completas, logos, criterios y exportaciones permanecen en `data/` hasta que los elimines. Reanalizar el mismo trabajo reutiliza la transcripción completa. Las exportaciones son síncronas, para uso personal, no para muchos usuarios concurrentes.

## Actualizar sin perder tus datos

Cierra la app con Ctrl+C. Conserva tu carpeta anterior. Descarga el ZIP nuevo en una carpeta nueva y ejecuta INICIAR_WINDOWS.bat. Si necesitas conservar logos/modelos, copia la carpeta `data` anterior a la nueva con la app cerrada. No copies la `.venv` antigua: el iniciador instalará el entorno adecuado.
