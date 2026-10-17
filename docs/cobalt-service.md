# Servicio propio de descarga: integración experimental

Estado (17 de octubre de 2026): implementado y probado con un MP4 de prueba,
pero **no validado para descargar desde YouTube**. Permanece desactivado.
No entregar esta integración como reparación ni pedir al usuario que reinstale.

## Diseño

Clip Studio envía la URL al Cobalt administrado por el propietario de la app.
Cobalt prepara y transmite el archivo; Clip Studio lo guarda, verifica con FFprobe
y registra como un video normal del editor. El cliente final no instala Docker,
no aporta cookies y no inicia sesión en Google.

El servicio incluye Cobalt y BgUtils oficiales, fijados por digest en
`services/cobalt/compose.yaml`. Un adaptador interno convierte el contrato JSON
`POST /get_pot` de BgUtils al contrato de sesión de Cobalt. Los tokens son
anónimos, se mantienen en memoria y no se registran. No se usan instancias
públicas de terceros ni cuentas personales.

Importante: la versión seleccionada de Cobalt no solicita la sesión anónima para
todos sus clientes/calidades. Su ruta iOS de hasta 1080p no depende de ella;
la ruta de mayor resolución puede usar WEB_EMBEDDED y la sesión. Instalar el
proveedor de tokens **no garantiza** que YouTube acepte ambas rutas.

## Operación y validación (administrador, no usuario final)

Requisitos: Docker con Compose, Python con `requirements.txt`, FFmpeg y FFprobe.
Desde la raíz del repositorio, usando el Python del entorno de la aplicación:

```sh
.venv/bin/python services/cobalt/manage.py init
.venv/bin/python services/cobalt/manage.py start
.venv/bin/python services/cobalt/manage.py validate
# Solo después de cuatro descargas reales correctas:
.venv/bin/python services/cobalt/manage.py activate
```

`init` crea una clave aleatoria en `data/cobalt/`, excluido de Git, y deja
`enabled:false`. `start` comprueba disponibilidad de los tres componentes;
no demuestra acceso a YouTube. `validate` intenta los dos enlaces reportados,
en calidad rápida y original, verifica audio/video y duración y guarda resultados
privados. Se detiene al primer fallo para evitar reintentos inútiles.
`activate` rechaza resultados incompletos o de otra configuración.
Los MP4 correctos se conservan para revisión en `data/cobalt/validation/`.

```sh
.venv/bin/python services/cobalt/manage.py disable
.venv/bin/python services/cobalt/manage.py stop
```

Sin activación, el importador anterior permanece en uso. Los cambios no reparan
por sí mismos sus errores de sesión. Para un servicio remoto, el administrador
puede configurar `CLIP_COBALT_URL` (HTTPS) y `CLIP_COBALT_KEY` en el servidor de
Clip Studio; estas variables habilitan explícitamente esa instancia y requieren
validación previa en el entorno destino. Nunca deben llegar al JavaScript.
No usar `api.cobalt.tools`: su instancia pública no está autorizada para esta app.

## Protección y despliegue

La plantilla solo publica `127.0.0.1:9000`. Los componentes internos no publican
puertos; se ejecutan sin privilegios, con límites de recursos y archivos de solo
lectura. La clave protege las solicitudes de preparación. La respuesta de túnel
debe pertenecer a la misma instancia; no se siguen redirecciones, ni se propaga
la clave al descargar el archivo. Se limitan archivos a 12 GB, se eliminan
parciales y los errores del proveedor no se exponen directamente al cliente.

Para producción falta elegir alojamiento con acceso funcional a YouTube,
configurar HTTPS, capacidad, cuotas, limpieza y monitoreo. El video atraviesa ese
servidor: implica ancho de banda y posible coste de alojamiento. Esta plantilla
no publica un servicio ni contrata infraestructura. Mantener la clave únicamente
en el backend y comprobar licencias de Cobalt (AGPL) y BgUtils al desplegar.

En el entorno gestionado, `manage.py start` conserva el proxy de Docker y monta
la CA proporcionada sin desactivar TLS. El arranque es reproducible, pero la
conectividad de YouTube sigue fallando: `Tunnel connection failed: 403 Forbidden`.
PyPI responde 200. Cobalt devuelve `error.api.fetch.fail` y el adaptador informa
`YT-SERVICIO`. No se obtuvo ningún MP4 de YouTube ni se activó el servicio.
Ese rechazo del proxy de desarrollo no identifica la causa de los bloqueos en
el PC Windows del usuario.

## Pruebas reproducibles

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test services/cobalt/session-bridge.test.mjs
node --check static/app.js
```

Las pruebas verifican el contrato, autenticación, origen del túnel, limpieza,
límites, sanitización de errores, bloqueo de activación y transferencia/importación
de un MP4 generado con FFmpeg. El servidor de descarga está simulado en esas
pruebas; no cuentan como descargas reales de YouTube.
