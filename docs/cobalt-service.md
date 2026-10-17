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

## Informe de transferencia vacía en Windows

La prueba en el PC del usuario arrancó los tres componentes correctamente, pero
la descarga falló con «El archivo recibido está vacío o incompleto». Esto es un
resultado distinto del rechazo del proxy en desarrollo; no atribuirlo al mismo
problema sin evidencia. Todavía no se conoce la causa del fallo de transferencia.

`services/cobalt/diagnose.py` comprueba prefijos de hasta 64 KiB del túnel combinado
y, mediante el contrato oficial `localProcessing: forced`, de las pistas por
separado. Solo acepta túneles de la misma instancia. Registra estados HTTP,
bytes recibidos y estado/OOM de los contenedores; excluye claves, URLs y tokens.
Genera `DIAGNOSTICO_COBALT.json` en la raíz de la app. Las pruebas con transportes
simulados verifican el aislamiento del fallo y que no se filtren credenciales.
Esta herramienta es diagnóstica: recibir un prefijo no valida un video completo.

El diagnóstico ampliado ejecuta, dentro de la imagen fijada, el extractor iOS de
Cobalt en un proceso aislado y comprueba HEAD y GET con rango para las pistas.
Conserva el proxy y la CA; no carga ni exporta cookies. La sesión en memoria del
proceso principal no se comparte: el informe registra esa limitación explícitamente.
Los estados permiten distinguir rechazo a HEAD de rechazo a lectura, pero no
prueban por sí solos que ambos procesos reciban los mismos enlaces o tokens.
El código limita lectura/tiempo y no imprime URLs ni errores internos del proveedor.

Validación en desarrollo: el programa se ejecutó en la imagen real y reportó
`extraction_error: fetch.fail` antes de obtener pistas, consistente con el bloqueo
conocido de esta conexión. Once pruebas relacionadas pasan, incluida una ejecución
Node con respuestas controladas HEAD 403 / GET 206 y ausencia de datos privados.
Pendiente ejecutar el diagnóstico ampliado en el PC Windows donde los túneles
combinado y separados devolvieron cero bytes sin OOM de contenedores.

## Corrección de transferencia comprobada con archivos locales

El PC del usuario mostró HEAD 403 y GET con rango 206 (65 536 bytes) para video y
audio. Ese resultado identifica un fallo del sondeo HEAD, aunque no valida todavía
un video completo. Además, la imagen fijada contiene Undici 6.24.1 y sus llamadas
`request(..., {maxRedirections})` fallan con «maxRedirections is not supported, use
the redirect interceptor». Ambos problemas se reprodujeron dentro de la imagen.

`head-fallback.mjs` aplica dos adaptaciones en memoria, sin modificar la imagen:

- Si HEAD falla por el método o no da tamaño, consulta GET `Range: bytes=0-0`.
  Acepta 206 con Content-Range válido, calcula el tamaño **total** y cancela el
  pequeño cuerpo del sondeo. No acepta un GET denegado como medio válido.
- Sustituye la opción incompatible por el interceptor oficial de redirecciones,
  conservando dispatcher, señal de cancelación y límite de redirecciones.

Se conservan TLS, el proxy, la autenticación y los límites. El cargador verifica
los SHA-256 del código de origen `internal.js` y `proxy.js`; rechaza otra versión
antes de aplicar cambios. El alcance es descarga normal de pistas, no la ruta
HLS experimental. El código original de Cobalt sigue bajo AGPL-3.0; imagen,
fuentes originales oficiales y parche están identificados para poder reproducir
la adaptación. No se usa un servicio público de terceros.

Prueba offline dentro de la imagen oficial, con un servidor local que rechaza
HEAD y permite GET: antes del parche, 0 bytes; después, pista idéntica al archivo
original y MP4 de 29 624 bytes. FFprobe verificó H.264, AAC, 320×180 y 1,2 segundos.
También se comprobó una redirección HTTP real en el túnel proxy. El contenedor de
prueba no tuvo acceso a red externa. El servicio Compose corregido arrancó con
los tres componentes saludables. Pasan 95 pruebas Python y 8 pruebas Node.

La descarga completa desde YouTube sigue pendiente de validar en el PC Windows.
No activar el proveedor hasta que su validación real y revisión del MP4 pasen.
