# Servicio propio de descarga: integración experimental

Estado (17 de octubre de 2026): implementado y probado con un MP4 de prueba,
pero **no validado para descargar desde YouTube**. Permanece desactivado.
No entregar esta integración como reparación ni pedir al usuario que reinstale.

## Diseño

Clip Studio envía la URL al Cobalt administrado por el propietario de la app.
Cobalt entrega dos pistas por túneles propios. Clip Studio recibe y verifica
cada pista completa, las une localmente y compara las duraciones de audio, video
y contenedor con la duración original antes de registrar el resultado en el editor. El cliente final no instala Docker,
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

### Aplicar en una carpeta Windows existente

`services/cobalt/apply_media_fix.py` descarga siete archivos: `compose.yaml`,
`head-fallback.mjs`, `media-probe.mjs`, `media-chunks.mjs`, `manage.py` y
`diagnose.py` y el cliente raíz `cobalt_import.py`, del commit fijado
`b37bb4558d6e6aec0f48804d71959af60cfb9690`. Verifica SHA-256 antes de escribir,
conserva copia de los archivos anteriores en `data/cobalt/compat-backup-*` y
rechaza cambios locales desconocidos. No sustituye claves, videos ni `.venv`.
Reinicia el servicio mediante `manage.py start`; si ese arranque falla, restaura
los archivos anteriores e intenta reiniciar la configuración anterior.

Tras arrancar, ejecuta la validación real de los dos videos en calidad rápida,
revalidando el archivo anterior si está disponible. Si falla, muestra el resultado, conserva la corrección y genera
automáticamente el diagnóstico para investigar; no activa el proveedor. Si pasa, todavía se deben revisar los
MP4 y activar explícitamente solo la calidad rápida. Los usuarios finales de la app no
necesitan ejecutar este procedimiento: es una actualización de la instalación
de prueba del propietario.

La descarga de los archivos desde el repositorio y sus checksums se verificó
en desarrollo. Las pruebas del actualizador comprueban preservación de claves,
aplicación repetida, restauración y rechazo de contenido alterado o ediciones
locales. La ejecución completa de este actualizador y la descarga de YouTube
siguen pendientes de verificar en Windows.

### Resultado posterior en Windows

El instalador terminó y los componentes quedaron saludables, pero la primera
validación real siguió fallando con archivo vacío/incompleto. No presentar el
parche como reparación validada de YouTube ni repetir la instalación sin nueva
evidencia. El éxito de la integración offline no prueba el caso remoto.

El diagnóstico ampliado compara GET de un byte con GET de 64 KiB, registra
Content-Range numérico, comprueba que el contenedor tenga configurado el preload
y ejecuta la ruta `internalStream` corregida con las mismas URLs del extractor
anónimo aislado. Recoge estados HTTP y categorías de errores de lectura; no
registra URLs, claves ni mensajes originales de errores. Conserva la limitación
de no compartir la sesión en memoria del proceso principal. Falta el informe de
esta comparación para decidir el próximo cambio; no se modificó el sondeo de
producción basándose solamente en la hipótesis del tamaño de rango.

### Lectura de audio por bloques (informe completo posterior)

El informe Windows descartó que GET de un byte fuera la causa: tanto video como
audio respondieron 206 a un byte y a 64 KiB con Content-Range correcto. El preload
estaba configurado. La ruta corregida entregó video, pero la lectura por bloques
de audio recibió GET 403 y abortó. El informe no demuestra todavía qué tamaño
máximo admite ese servidor ni garantiza que reducir el rango resuelva el caso.

`media-chunks.mjs` reemplaza el lector de bloques de la imagen fijada. Empieza con
8 MB; ante un 403 de ese rango, prueba 1 MiB y después 64 KiB, sin repetir rangos
idénticos ni seguir intentando si el menor también es rechazado. Conserva la
misma URL/identidad de acceso, TLS, dispatcher y señal. Exige 206, Content-Range
exacto, tamaño total consistente y cantidad real de bytes. No concatena páginas
de error, rangos desplazados ni bloques incompletos. Gestiona el evento de aborto
al descartar una respuesta para evitar cerrar el proceso del servicio.

Una prueba offline ampliada con audio AAC de 15 s y metadatos al principio
(faststart) permite 64 KiB pero rechaza rangos grandes para el audio. El parche
anterior produce 0 bytes. El nuevo genera 155 370 bytes; FFprobe verifica 10
paquetes H.264 y 647 AAC, duración de contenedor 15,2 s. Se comprobó el contenido
de la pista y una redirección. La validación real ahora cuenta paquetes y exige
audio y video con datos, no solo declaraciones de pistas. Pendiente confirmar
la descarga completa de YouTube en el PC; no activar basándose en la prueba offline.

### Resultado inicialmente marcado OK, después invalidado por duración

El usuario ejecutó la actualización adaptativa en Windows. La validación real
mostró `JCcuOv5y_9g fast OK`: se obtuvo un MP4 reproducible y FFprobe comprobó audio,
video y paquetes. La revisión posterior demostró que era un archivo parcial de
64 segundos. Ese OK NO acreditaba una descarga completa. El paso siguiente `original` falló con `YT-RESTRINGIDO`; el
validador anterior se detuvo antes de probar el segundo video. No interpretar
ese código de la ruta original como prueba de que el video sea privado: la ruta
rápida sí pudo descargarlo.

El informe posterior confirma video y audio por la ruta corregida, y para audio
muestra 8 MB → 403 seguido de 1 MiB → 206. Los prefijos por sí solos no validan
videos completos; el resultado `fast OK` del validador antiguo tampoco acreditaba integridad: no
comparaba duración original ni tamaños completos. No reutilizar esos resultados.

El administrador puede ejecutar `manage.py validate --quality fast --reuse`.
Se exigen ambos videos en esa calidad, con paquetes de audio y video. Una descarga
anterior solo se reutiliza si pertenece a la misma configuración, se encuentra
bajo el directorio de validación, coincide con los datos registrados y vuelve a
pasar FFprobe. Los resultados se guardan tras cada video. La descarga nueva se
conserva con su ruta relativa para revisión. Original sigue pendiente.

Tras revisar los MP4, `manage.py activate --quality fast` habilita únicamente
`fast`. El cliente de la app rechaza `original` antes de hacer solicitudes al
servicio. Reiniciar la app con INICIAR_WINDOWS después de actualizar/activar para
cargar el cliente nuevo. La activación completa sigue exigiendo las cuatro
combinaciones. Las variables de servicio del entorno son configuración explícita
del operador y no usan la restricción del archivo local.

El actualizador comprueba ahora la calidad rápida y revalida el archivo ya guardado
para evitar volver a transferirlo. No activa el servicio automáticamente. Falta
el resultado real del segundo video en modo rápido y revisión de los MP4.

### Corrección de integridad tras los archivos de 64 segundos

`REVISION_DURACION.json` del usuario confirma 64,477052 s / 16 305 322 bytes y
64,641134 s / 44 116 015 bytes. Los dos anteriores OK quedan invalidados. El
primer video anunciaba más de 918 MB solo de pista de video, por lo que el MP4
no correspondía a una transferencia completa. No activar a partir de esos registros.

El cliente ahora solicita `localProcessing: forced`, recibe las dos pistas
completas con tamaño declarado, comprueba sus bytes agregados contra la información
del extractor, y solo después usa FFmpeg con archivos locales que permiten
búsqueda. Esto evita depender de que una unión en directo siga leyendo hasta el
final; no establece por sí solo la causa exacta de todo rechazo remoto.

El preload incorpora identidad, duración original y tamaño agregado de las pistas
a la respuesta JSON, desde los formatos y basic_info del extractor de YouTube.
Los dos módulos adicionales también se verifican por SHA-256 de la imagen fijada.
Los túneles siguen perteneciendo a la instancia y no reciben la clave API. Su
vigencia se amplía a 7500 s para que el segundo no expire mientras llega la primera
pista, dentro del límite de 7200 s de transferencia. No se exponen a la UI.

FFprobe debe confirmar paquetes y duraciones de audio, video y contenedor dentro
de max(2 s, 0,5 %) del original. La falta de información del original es un error,
no un permiso para aceptar un archivo sin verificar. Los registros requieren
`verification_version: 2` y `expected_duration`; los antiguos no habilitan ni
reutilizan descargas. El actualizador mantiene el servicio desactivado hasta la
nueva validación y revisión. No borra los MP4 antiguos del usuario.

Pruebas: un MP4 real de 64 s se rechaza para un original esperado de 1080 s y se
eliminan las nuevas pistas temporales y salida fallida. Una integración offline
en la imagen fijada entrega túneles firmados reales, rechaza HEAD y rangos grandes
de audio, transfiere ambas pistas sin faststart exactamente y luego une localmente:
394 129 bytes, 15 s de video y audio, 150 paquetes de video y 647 de audio.
La descarga completa desde YouTube sigue pendiente de validación en Windows.

Los archivos que superan la verificación nueva se reúnen en
`data/cobalt/validation/VERIFICADOS`, con nombres que incluyen el ID del video.
El actualizador abre esa carpeta al terminar correctamente en Windows. Los MP4
antiguos permanecen en sus carpetas originales y no se presentan como verificados.
Se muestran fases y avance durante la transferencia; si falla, el registro guarda
solo duración esperada y contadores de bytes observados, sin claves ni URLs.
`start` fuerza recreación para cargar los archivos de preload montados, incluso
cuando las rutas y nombres del Compose no han cambiado.
