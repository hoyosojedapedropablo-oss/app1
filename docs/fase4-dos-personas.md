# Fase 4 · «Dos personas» (pantalla dividida)

Objetivo: en podcasts y entrevistas, una persona arriba y otra abajo, cada una centrada en su cara, sin que la cámara
vaya de un lado a otro. Regla de oro (lo aprendido con «Cámara + juego», E-01, E-07, E-31, E-32): **nada se da por bueno
sin medirlo en clips reales, y el formato que elige el usuario nunca se cambia en silencio.**

## Parte A · Medir antes de programar (sin tocar la app)

1. Arma el **banco de pruebas** en `tests/bench/dos_personas.json` (solo referencias: id del proyecto, inicio, fin y lo
   que se espera), con 10 clips reales del usuario:
   - 4 de **dos personas que se ven a la vez** (deben dividirse): de «Sinvergüenza Podcast» (TOPBOY), «ASÍ SE CONTRATAN
     SICARIOS» (Más Allá del Silencio), «El niño que hackeó Harvard…» y Reboll333 si hay tramos así.
   - 2 de **podcast con planos alternos**, una persona por plano (no deben dividirse: saldría la misma persona dos veces).
   - 2 de **una sola persona** (streamer a cámara, Westcol IRL).
   - 1 de **tres o más personas** (Ibai con Westcol en el entrenamiento, KODDY G VS 10 MUJERES).
   - 1 de **juego con cámara** (Epidemic77).
   Marca a mano en cada uno lo que se espera (`dividir: true/false`) mirando el video.
2. Corre `tracking.analyze` en los 10 y guarda, por clip: personas principales, porcentaje de fotogramas en que las dos
   salen **a la vez**, cuánto habla cada una (según `active`), distancia horizontal entre caras (en % del ancho), cortes
   de plano y cuántas veces se intercambian de lado.
3. Mándame la tabla antes de seguir. Con esos números se fijan los umbrales de la Parte B; no se inventan.

## Parte B · Programar

### Cuándo se divide (función pura, `tracking.duo_plan(result)`)
Se divide solo si se cumplen **todas**. Umbrales fijados por el usuario con la tabla de la Parte A
(`tests/bench/dos_personas_medidas.json`):
- exactamente **2 personas principales** (las demás, más pequeñas que `NEAR` de la mayor, no cuentan);
- las dos se ven **a la vez** en al menos el **80 %** de los fotogramas del clip (los 4 que se dividen: 95–100 %; los
  demás: 54 % como mucho);
- separación entre caras **mediana de al menos el 30 %** del ancho y **mínima de al menos el 25 %** (los 4: mediana
  46–54 %, mínima 35 % o más; si están más juntas, un recorte normal ya las muestra a las dos);
- **0 cambios de lado** en el clip;
- **sin criterio de voz**: en una entrevista es normal que en 20–30 s hable solo una (Jose Pino: el presentador no
  gana ninguna de las 22 ventanas con voz).

Si no se cumple, devuelve `None` y un **motivo legible**. Los motivos, en este orden:
- «No se ve a ninguna persona en este clip.»
- «Solo se ve una persona a la vez: el video muestra a una persona o alterna planos de una en una.»
- «Hay N personas en el plano: «Dos personas» es para dos.»
- «Las dos personas solo se ven a la vez el X % del clip (hace falta el 80 %).»
- «Las dos personas se cambian de lado durante el clip.»
- «Las caras están muy juntas (X % del ancho; hace falta el 30 %): un recorte normal ya muestra a las dos.»
- «En algún momento las caras se acercan demasiado (X % del ancho; el mínimo es el 25 %).»

Pruebas sintéticas al límite (`tests/test_duo.py`):
- una persona que se va a mitad del clip (60 % a la vez → no);
- dos caras juntas al 22 % (→ no);
- dos personas que se cruzan (→ no).

Con el banco real acierta los 10 (`test_the_bench_of_ten_real_clips_is_decided_right`, con el seguimiento de los 10
clips guardado en `tests/bench/dos_personas_tracking.json.gz`).

### Composición (igual de medidas que «Cámara + juego»)
- Lienzo 1080×1920: panel de arriba (956 px), línea de 6 px (`layout.SEAM`), panel de abajo (958 px). Alturas pares
  porque FFmpeg trabaja en yuv420p: con dos paneles de 957 el video salía de 1080×1919 (E-37).
- **Arriba la persona de la izquierda y abajo la de la derecha**, siempre igual dentro del clip.
- Cada panel es un recorte del video original con la forma del panel, centrado en la cara de su persona y con la cara
  ocupando un 30–40 % de la altura del panel. Sigue a esa persona con el mismo suavizado de `tracking` (sin saltos) y no
  se sale del cuadro. Si la persona desaparece un momento, el panel se queda quieto, nunca salta a la otra persona.
- **Título** centrado en la línea de división (como en «Cámara + juego»); **subtítulos** abajo, al 86 % de la altura.

### Formato y protecciones
- Nuevo encuadre `duo` («Dos personas») en «Configura tus clips» y en el editor, junto a los demás.
- **Solo se usa si el usuario lo elige.** Si un clip no cumple las condiciones, sale con el seguimiento normal y la tarjeta
  del clip muestra el motivo, nunca un cambio silencioso. En el editor el usuario puede forzarlo en ese clip.
- **Sugerencia, no cambio:** si al analizar un video la mayoría de sus clips cumplen las condiciones, mostrar un aviso
  «Este video parece un podcast de dos personas · Usar “Dos personas”», que el usuario acepta o ignora.
- Las plantillas no cambian el encuadre (ya es así).

### Todos los lugares que dibujan un clip (lección de E-01)
La misma geometría y la misma ruta de cámara en: exportación (FFmpeg, con `sendcmd` para los dos recortes), vista previa
del editor (lienzo, como `drawStack`), miniaturas, vistas previas de la biblioteca, exportación desde la biblioteca y
directos. Una prueba recorre todos esos caminos con el mismo clip y comprueba que dan el mismo recorte.

## Parte C · Comprobar antes de instalar

1. **Decisión:** en el banco de 10 clips, `duo_plan` acierta los **10** (divide los 4 de dos personas y ninguno de los otros 6).
   Si falla uno, se ajusta y se vuelve a medir; no se instala con fallos.
2. **Calidad en los 4 de dos personas**, medida en el MP4 exportado:
   - la cara de cada persona está completa dentro de su panel en al menos el 95 % de los fotogramas;
   - nunca sale la misma persona en los dos paneles, y nunca se intercambian;
   - la cara ocupa entre el 25 y el 45 % de la altura del panel;
   - el movimiento de cada panel no supera la velocidad máxima de `tracking`.
3. **Igualdad:** la vista previa del editor y el MP4 muestran el mismo recorte (comparación de fotogramas).
4. **Sin romper nada:** suite completa en verde, y «Cámara + juego», zoom y pantalla completa siguen saliendo igual en sus
   clips del banco.
5. Lámina para el usuario: un fotograma de cada uno de los 10 clips del banco, con lo que hizo la app.
6. Registrar en `ERRORES_CONOCIDOS.md` cualquier fallo que aparezca, con su prueba de guarda.
7. Instalar solo si no hay un directo grabando; avisar antes.
