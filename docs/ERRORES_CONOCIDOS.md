# Errores conocidos de ClipStudio: qué pasó, por qué, cómo se corrigió y qué impide que vuelva

Este archivo es la memoria de errores del proyecto. **Regla:** cada error corregido se anota aquí con su ID y al menos
una prueba automática (entre comillas invertidas) que falla si el error vuelve. La prueba
`test_every_known_error_has_a_guard` (tests/test_regressions.py) comprueba que cada entrada nombre pruebas que existen.

## Reglas de prevención (se aplican antes de cada cambio)

1. **Contratos compartidos.** Si una función la usan varios módulos (p. ej. `tracking.make_detector`, usada por el
   seguimiento y por la detección de cámara), su forma de salida no cambia: lo nuevo va detrás de una opción. Antes de
   tocarla: `grep` de todos sus usos.
2. **Nada de fallos silenciosos.** Prohibido `except Exception: pass` en los pasos que deciden cómo sale un clip. Un fallo
   se registra en `incidents` (data/incidents.jsonl), se guarda en el clip y se reintenta; la app muestra un aviso.
3. **El formato elegido manda.** Si no se puede aplicar (no hay cámara), el clip lo dice; nunca se cambia sin avisar.
4. **Probar con caras y videos reales.** Las pruebas con detectores simulados deben simular solo la red neuronal, no la
   función que la envuelve. Antes de instalar: `python verificar_instalacion.py` sobre los clips reales del usuario.
5. **Valores en el límite.** Un umbral que da resultados distintos en dos pasadas del mismo clip es un error.

## E-01 · «Cámara + juego» dejó de funcionar en todos los clips (nov 2026)
- **Síntoma:** clips de MrStivenTc con «Cámara + juego» elegido salían con bandas negras.
- **Causa raíz:** el PR #52 añadió un 6.º valor (mirada a cámara) a cada cara de `make_detector`. `layout.py` desempaqueta
  5 en tres sitios → `ValueError: too many values to unpack`. `_prepare_layout` tenía `except Exception: pass`, así que
  el error se ocultó y el clip cayó al formato con bandas sin aviso.
- **Por qué no lo vieron las pruebas:** todas sustituían `make_detector` entero por uno falso de 5 valores.
- **Solución:** `make_detector` devuelve 5 valores siempre; el 6.º solo con `with_front=True` (seguimiento). Registro de
  incidentes, aviso en la app, `layout_error` en el clip y reintento automático al arrancar.
- **Guardas:** `test_E01_make_detector_keeps_five_values_unless_asked`, `test_E01_every_consumer_runs_with_the_real_detector_shape`,
  `test_E01_failed_camera_preparation_is_recorded_not_swallowed`, `test_E01_unexpected_error_in_face_tracking_is_recorded_but_no_faces_is_not`,
  `test_E01_no_silent_handlers_in_the_steps_that_decide_the_format`

## E-02 · La cámara se encontraba o se perdía al azar (MrStivenTc, nov 2026)
- **Causa:** la cara del streamer (mirando abajo) aparecía en el 29-33 % de las muestras y el umbral era 30 %.
- **Solución:** con «Cámara + juego» elegido basta el 20 %.
- **Guardas:** `test_E02_chosen_stack_accepts_a_camera_seen_in_a_fifth_of_the_samples`, `test_without_any_face_only_when_the_user_chose_camera_plus_game`

## E-03 · Una cara del banner del streamer se tomó por la cámara (MrStivenTc)
- **Solución:** una cara que nunca cambia es un dibujo, no la cámara (detector v5).
- **Guardas:** `test_a_face_that_never_changes_is_a_picture_not_the_camera`

## E-04 · Un directo de una sola cámara o una sala quieta se tomó por «cámara + juego» (IRL, NaimDarrechi)
- **Guardas:** `test_a_one_camera_stream_is_not_camera_plus_game`, `test_a_still_room_with_people_seen_outside_the_corner_is_not_a_camera`, `test_a_camera_filling_the_screen_is_not_an_overlay`

## E-05 · Cámara recortada demasiado estrecha / bordes de la sala tomados como borde
- **Guardas:** `test_camera_border_gives_the_real_width`, `test_static_room_edges_inside_a_wide_camera_are_not_its_border`

## E-06 · Reacción a un video (Westcol): salía un recorte del escritorio con chat y barra de tareas
- **Solución:** cámara arriba y solo el reproductor de video abajo.
- **Guardas:** `test_player_found_and_chat_left_out`, `test_reaction_uses_camera_and_video_unless_turned_off`, `test_game_is_not_a_screen_capture`

## E-07 · El modo automático cambiaba el formato que eligió el usuario
- **Guardas:** `test_another_format_is_never_turned_into_camera_and_game`, `test_a_stream_without_a_camera_box_stays_normal_even_when_chosen`

## E-08 · «La app olvida lo guardado»: el seguimiento facial solo funcionaba en el editor (#50)
- **Causa:** vistas previas, miniaturas, exportación rápida y clips en vivo no leían el ajuste guardado.
- **Guardas:** `test_saved_face_tracking_applies_outside_the_editor`, `test_cached_tracking_is_reused_without_computing`

## E-09 · El clip empezaba en la cara más grande, no en quien habla (Jay Wheeler, #52)
- **Guardas:** `test_clip_starts_on_the_speaker_not_on_the_biggest_face`, `test_background_talkers_never_take_the_camera`, `test_moving_without_talking_does_not_pull_the_camera`

## E-10 · Título por encima de la línea en el formato Zoom (franja negra propia del video, #53)
- **Guardas:** `test_bar_inside_the_video_moves_the_title_down_to_the_picture`, `test_title_moved_by_hand_stays_and_an_automatic_one_follows_the_format`

## E-11 · Título tapado por la barra superior de TikTok/Instagram en pantalla completa (#49)
- **Guardas:** `test_full_screen_title_sits_below_the_top_bar`, `test_title_goes_on_the_line_of_each_format`

## E-12 · Un nombre repetido (`const ago`) en shell.js paró todos los botones (#51)
- **Guardas:** `test_E12_no_duplicate_top_level_names_in_the_page_scripts`

## E-13 · YouTube entregaba 360p haciéndose pasar por HD
- **Guardas:** `test_real_360p_output_is_rejected_even_when_extractor_claims_1080p`, `test_measured_360p_is_rejected_even_if_file_claims_hd`

## E-14 · Límites de duración (YouTube 200 min, archivo local 120 min, Kick VOD 8 h, 12 GB)
- **Guardas:** `test_native_filter_and_source_guard_accept_200_minutes_and_reject_any_excess`, `test_local_upload_retains_120_minute_limit`, `test_quality_fits_12_gb`

## E-15 · Directo: el idioma se bloqueaba mal por un trozo con ruido
- **Guardas:** `test_one_noisy_chunk_does_not_lock_a_wrong_language`, `test_chosen_language_is_used_from_the_first_segment`

## E-16 · Directo: capturas huérfanas seguían grabando tras cerrar la app
- **Guardas:** `test_orphan_captures_are_stopped_at_startup`, `test_capture_dies_when_the_app_is_killed`

## E-17 · Clips casi en silencio y títulos inventados
- **Guardas:** `test_a_clip_that_is_mostly_silence_is_dropped`, `test_invented_titles_are_rejected`, `test_invented_names_and_quotes_do_not`

## E-18 · Sesión reanudada grababa en el sitio equivocado
- **Guardas:** `test_a_resumed_session_records_after_its_newest_segment`, `test_state_survives_restart_as_interrupted`

## E-19 · Clip en vivo «sin video» tras detener y reanudar una sesión (HotSpanish Vlogs, nov 2026)
- **Síntoma:** aviso «Corte del clip en vivo · FileNotFoundError: segments» y «Vista previa del clip · 404» repetido.
- **Causa raíz:** al detener una sesión se borra su memoria temporal de video. Al reanudarla, el «corte» que impide al
  análisis mirar hacia atrás solo se marcaba si FFmpeg se había reconectado antes (`next_index > 0`); esta sesión nunca
  perdió la señal, así que la primera ronda tras reanudar propuso el minuto 15, cuyo video ya no existía.
- **Solución:** `_mark_restart` marca el corte siempre que ya hay video grabado; el análisis nunca mira antes del
  fragmento más antiguo que sigue en el disco; un momento sin video se descarta (no queda roto en la biblioteca); un
  clip sin video no se cuenta como fallo de vista previa.
- **Guardas:** `test_E19_resuming_a_stopped_session_marks_a_gap_even_without_reconnections`, `test_E19_detection_only_looks_at_video_still_on_disk`,
  `test_E19_a_moment_whose_video_is_gone_is_discarded_not_left_broken`, `test_E19_a_library_clip_without_video_is_not_reported_as_a_failure`

## E-20 · Casi todos los clips de un video salían con unos 40/100 y como «flojo» (nov 2026)
- **Síntoma:** la media de un video era de unos 40 puntos; la app parecía mala para los cliperos.
- **Causa raíz:** el juez tenía la orden de que «la mayoría de momentos son normales, notas de 3 a 6», y un «flojo» quedaba
  encerrado entre 40 y 64. Además, los tramos de relleno que se agregan para cubrir el 75 % del video salían en la misma
  lista, y en videos largos solo se juzgaban 15 clips, sin los nombres del video.
- **Solución:** juez recalibrado («los clips ya están preseleccionados: ¿lo publicaría un clipero?») con el veredicto
  «publicable» (55-69); nota final = 60 % juez + 25 % señales del clip (arranca al grano, ritmo, pausas) + 15 % posición en
  su video (`scoring.py`); los mejores primero con «Top N de este video» y motivos en la tarjeta; el relleno va a «Para
  revisar»; se juzgan hasta 40 clips con los nombres del video.
- **Guardas:** `test_E20_a_publishable_clip_is_not_boxed_as_weak`, `test_E20_judge_is_told_clips_are_preselected_not_that_most_are_weak`,
  `test_E20_a_clip_that_starts_talking_scores_above_one_with_dead_air`, `test_E20_best_clips_first_with_rank_and_reasons`,
  `test_E20_filler_for_coverage_goes_to_review_not_to_the_main_list`, `test_E20_a_typical_video_no_longer_averages_forty`,
  `test_E20_place_in_the_video_never_turns_a_weak_clip_into_a_great_one`
- **E-20c (primera prueba real, video de Ibai):** la IA no marcó ningún momento y los 20 clips eran de cobertura; la rama
  dejó de juzgar la cobertura, nadie recibió nota y «Los mejores» quedó vacío (igual en otro video de Ibai y en «Más Allá
  del Silencio Podcast»). Ahora el juez revisa primero lo que marcó la IA y después la cobertura, hasta 40 clips; solo
  queda en «Para revisar» lo que no se juzgó o lo que el juez llamó relleno. Guardas:
  `test_E20c_coverage_clips_are_judged_when_the_ai_marked_no_moment`, `test_E20c_judged_coverage_enters_the_ranking_and_filler_waits_in_review`
- **E-20d (mismo video, con E-20c):** desde 55 entraban 17 de 18 clips a «Los mejores» y la pestaña no filtraba; las
  señales daban 86-99 a casi todos y no ordenaban. Ahora «Los mejores» empieza en 65 (los 3 mejores siempre), las señales
  son más exigentes y pesan 15 % (juez 70 %), y los títulos pierden los hashtags pegados. Guardas:
  `test_E20d_main_list_is_a_real_selection`, `test_E20d_ordinary_talk_no_longer_maxes_the_signals`, `test_E20d_titles_lose_stuck_hashtags`

## E-21 · La IA proponía momentos, pero el análisis de videos los descartaba casi todos (nov 2026)
- **Síntoma:** en el video de Ibai con Westcol y en el de «Más Allá del Silencio Podcast» ningún clip venía de la IA: todos
  eran de cobertura («Para revisar») y la cobertura del podcast fue del 15 %.
- **Causa raíz:** el análisis de videos llamaba al selector sin `repair`. La IA propuso 24 momentos y se aceptaron 0: casi
  todos por duración (remates de 4-11 s en Ibai, historias de 72-188 s en el podcast). El ajuste de duración y de la cita
  ya existía, pero solo se usaba en directo. Y el recorte de lo largo se quedaba con los primeros 60 s y perdía el remate.
- **Solución:** el análisis de videos usa `repair=True` (como el directo); una propuesta larga se recorta alrededor de su
  cita (`fit_around`), sumando remate y planteamiento por turnos hasta la mitad del rango; una corta crece con sus frases
  vecinas.
- **Guardas:** `test_E21_video_analysis_repairs_cuts_instead_of_dropping`, `test_E21_a_long_story_is_cut_around_its_quote`,
  `test_E21_a_short_punchline_grows_to_the_minimum`

## E-22 · Títulos copiados de los ejemplos de la guía en videos sin relación (nov 2026)
- **Síntoma:** en el video de Ibai con Westcol (un entrenamiento táctico) dos clips salieron con «¿Dónde está el límite cuando
  trabajas con tu pareja?». El mismo título está en al menos 7 proyectos guardados.
- **Causa raíz:** `TITLE_GUIDE` daba tres títulos de ejemplo y el modelo de 7B los copiaba tal cual. `clean_title` no rechazaba
  las copias de esos ejemplos.
- **Solución:** la guía describe formas, sin títulos para copiar (versión `topics-human-titles-v2`, que invalida los títulos
  guardados); `clean_title` rechaza los ejemplos antiguos y sus variantes cercanas. Exigir una palabra dicha en el clip se
  probó y se descartó: rechazaba títulos creativos válidos («Una habitación idéntica…» para un clip que dice «cuarto»).
- **Guardas:** `test_E22_example_titles_of_the_guide_are_never_accepted`

## E-23 · La IA describía la cita en vez de copiarla, y un clip sin título tumbaba el análisis (nov 2026)
- **Síntoma:** en el video de Ibai, con E-21 y E-22, 7 de 9 propuestas de la IA se rechazaron por «cita no respaldada»:
  la IA escribía «Se menciona que hay un rehén…» en lugar de una frase dicha. Dos títulos cambiaban el tono (una broma
  como «critica», un disparo accidental como «se pelean»). Y si todos los títulos de un clip se rechazaban dos veces, el
  análisis entero fallaba.
- **Solución:** el selector pide una copia exacta con un ejemplo de lo que no vale y el ID de su frase (`key`); con repair,
  si la cita no está en el fragmento, se usa el texto de esa frase (solo si está en el momento o a 3 frases). La guía de
  títulos pide respetar el tono real. Un clip sin título válido recibe «Momento del m:ss · ponle título» en vez de fallar.
- **Guardas:** `test_E23_a_described_quote_is_replaced_by_its_key_phrase`, `test_E23_a_key_far_from_the_moment_does_not_rescue_it`,
  `test_E23_selector_asks_for_a_copied_quote_and_its_phrase_id`, `test_E23_a_clip_without_valid_titles_does_not_fail_the_analysis`

## E-24 · El filtro de interés del selector tiraba lo que el juez valoraba, y la cobertura repetía clips de la IA (nov 2026)
- **Síntoma (con E-23):** en Ibai la IA propuso 9 momentos con cita real y se aceptaron 0: 8 por «interés o resolución
  insuficiente» (el propio modelo se ponía 2 en gancho o remate). En el podcast, dos clips de cobertura repetían las frases
  de clips de la IA (0:00 con 0:15, 1:50 con 2:00). Los títulos salían con mayúsculas en cada palabra y «Así fue...».
- **Solución:** con repair (videos y directo) el selector solo descarta lo que el modelo puntúa con 1 o menos; el juez y la
  nota final deciden. La cobertura no añade una ventana que repita más de un cuarto de un clip existente. Los títulos pasan
  a mayúscula solo al inicio y en nombres (los que el clip escribe con mayúscula), sin puntos suspensivos, y la guía pide no
  preguntar por un desenlace que el clip ya muestra.
- **Guardas:** `test_E24_with_repair_the_judge_decides_moments_the_model_rated_two`, `test_E24_titles_in_spanish_case_and_without_ellipsis`,
  `test_E24_coverage_does_not_repeat_an_ai_clip`

## E-25 · Con E-24 seguían cayendo propuestas por la nota que la IA se ponía, y quedaban títulos vacíos o con nombres ajenos (nov 2026)
- **Síntoma:** en Ibai, 9 de 13 propuestas cayeron por «interés» (la IA se ponía 1). Quedaba un solapamiento de 4,6 s (22 %
  de un clip de 21 s) en Ibai y de 10,5 s en el podcast. Títulos: «¡Va, va, va!», «la vida delincuencial de un hablante», y
  «Westcol reflexiona…» en un clip donde habla el entrevistado.
- **Solución:** con repair, la nota que la IA se pone ya no descarta (solo `coherent=false`); decide el juez. La cobertura no
  repite más de 3 s ni más de un cuarto del clip más corto. Se rechazan títulos con menos de dos palabras de contenido, con
  «hablante», o con un nombre que no suena a nada dicho en el clip (un nombre mal oído, «Uescol» por Westcol, sí pasa).
- **Guardas:** `test_E24_with_repair_the_judge_decides_moments_the_model_rated_two`, `test_E25_titles_that_say_nothing_or_name_someone_absent_are_rejected`,
  `test_E25_coverage_never_repeats_more_than_three_seconds`

## E-26 · Títulos de videos largos que hablaban del clip vecino, ponían a otra persona o cambiaban el tono (nov 2026)
- **Síntoma (tras E-25, video de Ibai y podcast):** «Westcol: mi historia en la cárcel…» en un clip donde habla el
  entrevistado; «Westcol denuncia…» cuando presume en broma; «¿Quién sube a la escalera?» sobre el clip siguiente;
  genéricos («Descripción de la misión»); mayúsculas a medias («Desastre en el Piso»); y tras cada actualización hacía
  falta Ctrl + F5 porque `index.html` pedía siempre `shell.js?v=46`.
- **Causa raíz:** los títulos de videos largos se escribían en lotes de seis clips, sin saber quién habla. El filtro de
  nombres de E-25 se saltaba la primera palabra, y `sounds_said` a 0,6 confundía «westcol» con «estuvo».
- **Solución:** tras el juez, cada clip juzgado recibe su título de `viral.py` con el análisis del juez (quién, qué pasa,
  tono); el del lote queda como alternativa y como reserva. Los nombres del contexto deben sonar en el clip (a 0,7), también
  al inicio en la forma «Nombre: …». Se rechazan títulos genéricos, y las mayúsculas sueltas de palabras corrientes pasan a
  minúscula (un nombre mal oído las conserva). La página pide cada script con su fecha de modificación.
- **Guardas:** `test_E26_stray_capitals_become_spanish_case`, `test_E26_a_name_opening_the_title_must_be_said_in_the_clip`,
  `test_E26_generic_titles_are_rejected`, `test_E26_viral_titles_do_not_borrow_a_name_from_the_context`,
  `test_E26_title_writer_is_told_the_analysis_decides_who_and_tone`,
  `test_E26_the_page_asks_for_each_script_with_its_own_version`, `test_E26_a_name_the_transcriber_split_in_two_still_counts`
- **Ajuste al aplicar E-26:** a .7 también se rechazaba «JLexis» cuando la transcripción escribe «J. Lessie» (.62, dos
  palabras juntas), un caso real ya resuelto en directo. Una sola palabra exige .7; dos o tres palabras juntas, .6.
- **Retirado en E-27:** el título por clip (+35-63 % de tiempo, título propio en solo 8 de 35 clips con el modelo de 7B).

## E-27 · Títulos repetidos o abstractos, el juez tomaba el título del video como «quién habla», y nombres partidos (nov 2026)
- **Síntoma (con E-26):** «Humor y entusiasmo» dos veces en un video, «Persecución policial y tensión»; el juez ponía en
  «quien» «Sobreviví», «ASÍ CONTRATAN» o «Más Allá del Silencio Podcast», y salía «¿Por qué más Allá del Silencio defiende…?».
- **Solución:** ningún título se repite dentro de un video (el clip de menor nota toma otra alternativa o «ponle título»); se
  rechazan los títulos hechos solo de palabras abstractas; el juez pone en «quien» una persona del clip o su papel, y
  `judge.who` vacía lo que no suena en el clip; una mayúscula unida a un nombre se conserva («Más Allá del Silencio»). Se
  retira el título por clip de E-26. `tools/comparar_modelos_titulos.py` compara modelos de Ollama para los títulos.
- **Guardas:** `test_E27_titles_are_distinct_within_a_video`, `test_E27_titles_of_only_abstract_words_are_rejected`,
  `test_E27_multiword_names_keep_their_capitals`, `test_E27_judge_who_is_a_person_in_the_clip`, `test_E27_the_title_model_can_be_chosen`

## E-28 · Una palabra en mayúsculas del título del directo se volvía protagonista de los títulos (nov 2026)
- **Síntoma:** en el directo «EL PESAJE - STREAM FIGHERS 5» de Westcol, los títulos salían «¿PESAJE realmente subiría a un
  ring…?», «¿Quién será la primera rival de PESAJE?», «PESAJE: ¿Respeto en el ring…?».
- **Causa raíz:** `stream_names` toma las palabras con mayúscula del título como nombres del directo; «PESAJE» (el evento,
  escrito en mayúsculas) entró en la lista de nombres que reciben el transcriptor, el juez y el escritor de títulos.
- **Solución:** una sola palabra en mayúsculas de más de 4 letras solo cuenta como nombre si los textos o las etiquetas
  también la escriben en minúsculas o mixta (WESTCOL con «Westcol» en la descripción); las siglas cortas (VIP) siguen.
- **Guardas:** `test_E28_a_shouted_word_of_the_stream_title_is_not_a_name`

## E-29 · Los subtítulos en Montserrat salían en Arial, y las fuentes nuevas no llegaban a los proyectos (nov 2026)
- **Síntoma:** al preparar las fuentes de Fase 3, libass dibujaba «Montserrat» (la fuente por defecto de los subtítulos)
  con Arial Bold; y un proyecto ya exportado no tenía las fuentes nuevas (Luckiest Guy, Bangers…), que también caían en Arial.
- **Causa raíz:** `montserrat.ttf` es una instancia 700 de la Montserrat variable, pero conservó los nombres internos
  «Montserrat Thin»; y `export` copiaba `static/fonts` al proyecto solo si su carpeta no existía.
- **Solución:** `montserrat.ttf` lleva los nombres «Montserrat» Bold (los dibujos no cambian); `sync_fonts` añade o
  actualiza en cada exportación las fuentes que falten o hayan cambiado, sin borrar nada.
- **Guardas:** `test_E29_every_offered_face_is_drawn_with_its_own_file`, `test_E29_an_old_project_gets_the_new_faces`

## E-30 · Los subtítulos del MP4 salían más pequeños que en el editor (nov 2026)
- **Síntoma:** con las plantillas a 68-90, las letras del video exportado se veían pequeñas: la línea más ancha ocupaba
  42-61 % del ancho y Bangers, Poppins Black o Anton salían al 56-59 % del tamaño pedido.
- **Causa raíz:** libass toma el tamaño del ASS como la altura de toda la línea de Windows de la fuente
  (`usWinAscent + usWinDescent`), mientras el navegador, PIL y `title_layout` lo toman como su em. Cada fuente tiene
  márgenes distintos (relación 1,23 a 1,76), así que cada una se encogía distinto.
- **Solución:** `styling.ass_scale(fuente)` lee esa relación del propio archivo de la fuente (tablas OS/2 y head, en caché
  por archivo y fecha; sirve para fuentes añadidas después) y `ass_file` multiplica por ella cada tamaño del ASS: el
  `Fontsize` de `Caption` y `Box`, el `\fs` de cada frase y el que `caption_styles` repone tras la palabra resaltada
  (`\rCaption`, `\rBox`). El corte de líneas sigue usando el tamaño pedido. Medido: 98-103 % del tamaño de PIL en las 11 fuentes.
- **Guardas:** `test_E30_capitals_in_the_mp4_match_the_size_asked_for`, `test_E30_every_size_in_the_ass_is_scaled`

## E-31 · «Cámara + juego» elegido, pero clips con bandas negras, dos líneas de división y el juego descentrado (Epidemic77, nov 2026)
- **Síntoma:** en un directo de Epidemic77 (GTA RP, cámara arriba a la izquierda) con «Cámara + juego» elegido: algunos
  clips salieron con bandas negras; en otros, el panel de la cámara traía una franja del juego (dos líneas de división, y el
  título en la línea de abajo, no en la que se ve); y el personaje quedaba al borde del panel del juego.
- **Causa raíz (medida en sus 31 momentos):** cada momento busca la cámara por su cuenta. 3 no la encontraron y pasaron a
  bandas negras; 8 dieron otra caja (450 px de alto en vez de 376, o 412 de ancho en vez de 516); y 5 tomaron una columna del
  escenario (x = 714) por el borde del juego. Además, el panel del juego se corría a un lado para no mostrar la cámara.
- **Solución:** `layout.consensus_camera` toma la cámara en la que coinciden los momentos de la sesión (mediana del grupo
  mayoritario, al menos 3); un momento que no la encuentra o da otra caja usa esa, salvo que en ese momento no haya nadie en
  el recuadro (intro, pantalla completa), y entonces avisa. Al arrancar, los momentos guardados con la caja equivocada se
  preparan otra vez. Sin «Seguir la acción del juego» (ahora apagado por defecto) el panel del juego va centrado. La esquina de
  la cámara que muestra el juego centrado se difumina (crop + boxblur + overlay con 8 px de margen, `layout.camera_blur`),
  igual en el MP4, la vista previa del editor y las miniaturas; con «Seguir la acción» el recorte sigue esquivando la cámara.
  Los proyectos ya abiertos desde un directo toman la cámara de la sesión si su caja es de las equivocadas y no se marcó a mano.
- **Guardas:** `test_E31_the_box_most_moments_agree_on_wins`, `test_E31_the_game_panel_is_centred_unless_following_the_action`,
  `test_E31_a_moment_that_missed_the_camera_uses_the_sessions`, `test_E31_a_wrong_box_is_replaced_by_the_sessions`,
  `test_E31_nobody_in_the_sessions_camera_means_no_camera`, `test_E31_saved_moments_with_a_wrong_box_are_prepared_again`,
  `test_E31_exports_centre_the_game_by_default`, `test_E31_the_camera_a_centred_game_panel_shows_is_blurred`,
  `test_E31_an_opened_project_takes_the_sessions_camera_unless_marked_by_hand`
