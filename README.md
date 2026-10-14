# Clip Studio
Primera versión personal: FastAPI, FFmpeg y Whisper local en CPU. No requiere API de IA ni claves.

## Ejecutar
```bash
cd /workspace/app1
python -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000
```
FFmpeg, ffprobe y fuentes DejaVu/Liberation deben estar instalados. Whisper descarga el modelo `base` en la primera transcripción; requiere acceso a Hugging Face. `WHISPER_MODEL` permite usar una ruta local o un modelo compatible. No desactives la verificación TLS. El procesamiento CPU de videos largos puede ser lento.

Carga videos de hasta 120 minutos y 12 GB, elige un rango entre 5 y 180 segundos, analiza, edita y exporta. Los logos se cargan desde la interfaz. Exportación 1080×1920 H.264 CRF18 y AAC192k, con encuadre completo o recorte central. No se puede recuperar detalle ausente de la fuente.

## Límites de la primera versión
La selección es una heurística del texto transcrito: no es un modelo experto de viralidad ni detecta emociones visuales. Los títulos son extractos editables. Los subtítulos originales conservan los tiempos de transcripción; los editados se distribuyen uniformemente y requieren revisión de sincronización. Los trabajos se guardan en memoria y se pierden al reiniciar; videos y exportaciones permanecen en `data/` hasta eliminarlos manualmente. Las exportaciones son síncronas. No hay autenticación: usar únicamente en un entorno privado, no desplegar públicamente. Falta implementar análisis semántico avanzado, subtítulos sincronizados editables, persistencia y procesamiento robusto para producción.

## Validación
`.venv/bin/python -m unittest discover -s tests -v` verifica carga, exportación real 1080×1920, rangos, selección sin solapamientos y sincronización de subtítulos originales. La descarga del modelo está actualmente bloqueada por la política de red (403); se debe aplicar la configuración de Hugging Face antes de validar transcripción real.
