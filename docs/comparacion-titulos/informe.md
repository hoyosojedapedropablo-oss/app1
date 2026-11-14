# Comparación de modelos para títulos

| Modelo | Clips con algún título válido | Títulos válidos | s por clip | formato | sin anclar | filtro de la app |
| --- | --- | --- | --- | --- | --- | --- |
| qwen2.5:7b | 22 de 34 | 59 | 5.8 | 17 | 93 | 1 |
| qwen3:8b | 24 de 34 | 65 | 8.1 | 7 | 86 | 2 |

## Sobreviví a un Entrenamiento Táctico con Westcol

### 16:20 · Para revisar

> No, A mí me llevan a leotrecutar otra vez con ellos por su culpa. ¡Ah! Aquí, para, Sí. Vamos. ¡Vamos! ¡Policía! ¡Policía! ¡Policía! ¡Policía! ¡Policía! ¡Policía! a coger uno, eh! ¡Tira, tira, tira, tira! ¡Pas dentro, pa dentro! ¡Ven, ven, atrás! ¡Policía! ¡Policía! Aquí no hay na…

- Título actual: ¿Encontraron la planta? Buscaron en vano
- **qwen2.5:7b** (3.1 s): Westcol confunde la misión y comete errores al coger la planta | '¡Cubra la derecha!': Westcol se pierde en la misión táctica | ¿Westcol puede coger la planta sin errores en la misión?  
  rechazados: «Westcol vs. la planta medicinal: ¿Podrá mantenerse enfocado?» (sin anclar); «¿Cómo Westcol confunde la misión táctica y se pierde en la búsqueda de la planta?» (formato)
- **qwen3:8b** (38.0 s): Westcol se equivoca al intentar coger la planta | ¿Por qué Westcol no logra coger la planta?  
  rechazados: «Westcol se pierde en la misión táctica | «Veo una planta, veo harina»: el error que no se corrige» (sin anclar); «¿Cógelo o no? La confusión de Westcol en la misión | «La planta hay que cogerla»» (sin anclar); «Westcol se equivoca, pero sigue intentando | «Cubra la derecha»: la frustración en acción» (sin anclar)

### 6:34 · Para revisar

> Vale, y alante. Hasta muy dura, no falta ruedas. ¿Vas a flipar, Ulises? Te lo digo. Vas a alucinar. ¿Sabéis qué pasará de este ejercicio? No, no, no, no. Te guardé eso, papi. Entiendo que... Vamos a hablarnos mucho, de verdad. Sí, sí, sí. Perfecto. Confía en nosotros. Vale, a la …

- Título actual: Uli, ¿vas a alucinar con los burpees?
- **qwen2.5:7b** (5.6 s): —  
  rechazados: «Ulises se cae en el entrenamiento táctico: ¿Ibai y Westcol lo ayudan o empeoran?» (sin anclar); «'Vas a alucinar': Ibai y Westcol animan a Ulises mientras cae» (sin anclar); «¿Podrán Ibai y Westcol ayudar a Ulises?» (sin anclar); «Ulises pierde el control en el ejercicio táctico: ¿Qué pasará?» (sin anclar); «'Se me complica la cinta': Ulises se cae durante el entrenamiento» (sin anclar)
- **qwen3:8b** (7.0 s): —  
  rechazados: «Ulises se cae en la cinta durante el entrenamiento táctico | «Se me complica la cinta»: el error que encendió la risa» (sin anclar); ««Se me complica la cinta»: Ulises se cae en medio del entrenamiento táctico» (sin anclar); «¿Ulises aguantará la cinta? El error que interrumpió el entrenamiento» (sin anclar); «Ulises se cae: el momento que rompió la concentración del entrenamiento táctico» (sin anclar); ««Se se va»: el error de Ulises que dejó a Ibai y Westcol en risa» (sin anclar)

### 15:20 · Para revisar

> Cogeremos bien la mano, ponemos las esposas, aseguraremos que estén cerradas y ya lo tendremos controlado. Entramos West Coast a la derecha. Recuerda el plano. A la derecha o con la espalda que tenemos ahorita en la izquierda. ¿Sí? claro. Entra a la derecha, papi, yo le cubro esa…

- Título actual: ¿Cómo entraron al piso? Desastre en la misión
- **qwen2.5:7b** (6.6 s): —  
  rechazados: «Westcol y Ibai fallan estrepitosamente en la misión final | «¡Pietos!»: el error de Ibai» (sin anclar); ««¡Piedad ahí atrás!»: Ibai y Westcol en el infierno táctico | ¿Lograrán el asalto?» (sin anclar); «Ibai se burla de sí mismo: «¡Pietos!» durante el asalto final | ¿Podrán liberar al rehén?» (sin anclar); «Ibai da instrucciones desastrosas: «¡Piedad!» durante el asalto | ¿Podrán entrar en el piso?» (sin anclar); ««¡Derecha! ¡Derecha!»: Ibai y Westcol en el caos táctico | ¿Lograrán la misión?» (sin anclar)
- **qwen3:8b** (11.1 s): —  
  error: Unterminated string starting at: line 1 column 176 (char 175)

### 3:54 · Para revisar

> ¿Qué está pasando? Va, va, Al arriete, al arriete, al arriete ya. Vamos, vamos, Ya que papi, ya que papi. está. Vamos, cogerlo bien. La técnica. No se han explicado. nada más, ya se le van. Rápido. Va. Lo antes posible. hecho un video lo antes posible. 1, 2, 3. Vas arriba. 1, 2. …

- Título actual: Westcol: Aritete en acción
- **qwen2.5:7b** (5.7 s): —  
  rechazados: «Ibai grita 'Al arriete' a Westcol» (sin anclar); ««Al arriete, al arriete»: Ibai motiva a Westcol» (sin anclar); «¿Qué grita Ibai a Westcol durante el asalto?» (sin anclar); «Ibai corrige a Westcol con 'Vas arriba, 1, 2'» (sin anclar); «¿Quién da las instrucciones más locas? Ibai o Westcol?» (sin anclar)
- **qwen3:8b** (7.2 s): —  
  rechazados: «Ibai da instrucciones a Westcol durante el asalto a la puerta | «Vamos, cogerlo bien»: el grito que encendió el chat | ¿Ibai logró motivar al equipo? | «Los tenemos, los tenemos»: la tensión del asalto | ¿Qué pasará con el equipo después de las correcciones?» (sin anclar); «mejor”: 3} ✅ » (sin anclar); «mejor”: 3} ✅ » (sin anclar); «mejor”: 3} ✅ » (sin anclar); «mejor”: 3} ✅ » (sin anclar)

### 17:20 · Para revisar

> Tengo una puerta. ¡Policía Nacional! ¡Policía Nacional! ¡Ey, ¡Aseguro! ¡Aseguro! ¡Aseguro! ¡Aseguro! ¡Aseguro! ¡Aseguro! ¡Aseguro! ¡Eh, eh, eh, eh! ¡Paseposa, Weston! ¡Manu, atrás! ¡Manu, ¡Que estamos disfritando! ¡Aseguro aquí, asegúrate aquí! ¡Lo tengo, lo tengo! ¡Paseposa, det…

- Título actual: ¿Detuvieron al rehén? Fue un desastre
- **qwen2.5:7b** (5.5 s): —  
  rechazados: «Ibai dirige la misión final: 'Paseposa, Weston'» (sin anclar); ««Paseposa, Weston»: Ibai en acción» (sin anclar); «¿Podrán seguir las órdenes Ibai y Weston?» (sin anclar); «Ibai vs. Confusión táctica: 'Asegúrate aquí'» (sin anclar); «¿Detendrá Ibai el caos táctico?» (sin anclar)
- **qwen3:8b** (10.2 s): —  
  rechazados: «Ibai da órdenes durante la misión táctica | «Aseguro aquí, asegúrate aquí»: el grito que encendió el caos | ¿Lograrán controlar la situación? | ¿Aseguro aquí, asegúrate aquí? | ¿Qué pasará con la misión final?» (sin anclar); ««Aseguro aquí, asegúrate aquí»: el grito de Ibai en medio del caos táctico | ¿Aseguro aquí, asegúrate aquí? | ¿Lograrán controlar la situación? | ¿Aseguro aquí, asegúrate aquí? | ¿Qué pasará con la misión final?» (sin anclar); «¿Aseguro aquí, asegúrate aquí? Ibai se mete en el caos táctico | «Aseguro aquí, asegúrate aquí»: el grito que encendió el caos | ¿Aseguro aquí, asegúrate aquí? | ¿Lograrán controlar la situación? | ¿Qué pasará con la misión final?» (sin anclar); «Ibai se mete en el caos táctico: «Aseguro aquí, asegúrate aquí» | ¿Aseguro aquí, asegúrate aquí? | ¿Lograrán controlar la situación? | ¿Aseguro aquí, asegúrate aquí? | ¿Qué pasará con la misión final?» (sin anclar); ««Aseguro aquí, asegúrate aquí»: el grito de Ibai en medio del caos táctico | ¿Aseguro aquí, asegúrate aquí? | ¿Lograrán controlar la situación? | ¿Aseguro aquí, asegúrate aquí? | ¿Qué pasará con la misión final?» (sin anclar)

### 7:34 · Para revisar

> Se ha cargado el cámara tú. Yo voy bien ahora. Bien, bien, bien. Tres, dos, uno, cambiamos. Vamos a la rueda, vamos a la rueda. ¡Rápido, rápido, rápido! Su fusil atrás, su fusil atrás. Vale, papi, haga. Vale, papi. Ibai, al sitio. Avísale, avísale. Estoy, Uescol, ya en posición. …

- Título actual: ¿Quién avanza? ¡Tupado!
- **qwen2.5:7b** (5.9 s): Correcciones de Ibai: «Su fusil atrás» vs. «Arriba, arriba, Ues! | Ibai, avance»: ¿Ibai liderará la misión? o ¿Se descontrolará?  
  rechazados: «¿Podrá Ibai coordinar la misión táctico? «Vamos a la rueda»» (sin anclar); ««Vale, papi»: Ibai intenta corregir a Westcol» (sin anclar); «¿Ibai o la confusión táctica ganará?» (sin anclar)
- **qwen3:8b** (7.3 s): —  
  rechazados: «Ibai da órdenes en una misión táctica simulada | «Vamos, va, va»: el grito que encendió el caos» (sin anclar); «¿Ibai puede controlar la operación? | «No avance, no avance»: el error que salió a relucir» (sin anclar); «Ibai corrige los errores en tiempo real | «Díselo, díselo»: la tensión de la misión táctica» (sin anclar); «¿Se saldrá con la suya Ibai? | «Arriba, arriba, Ues»: el momento clave del entrenamiento» (sin anclar); «Ibai intenta liderar la operación | «Vamos a la rueda»: el grito que no logró controlar» (sin anclar)

### 18:19 · Para revisar

> Me falta una esposa solí. falta una nada más, ¿eh? No hay nada más. No hay nada más. Weston, en funda, que te están cubriendo tu compañero. Espera, espera, espera. Téngalo ahí, téngalo ahí. ¿Sigues qué pasó? Todo bien, esté bueno, esté bueno. Necesito las tijeras. Uno alarma fuer…

- Título actual: ¿Lograron la misión? No sin caos
- **qwen2.5:7b** (6.0 s): Libero al rehén, pero qué pasa ahora?  
  rechazados: «Westcol se lanza a liberar un rehén en plena misión táctica» (sin anclar); «¿Westcol puede liberar al rehén y salvar la misión?» (sin anclar); «Confusión en el asalto: Westcol intenta salvar la misión» (sin anclar); «Westcol vs. la confusión en la misión táctica» (sin anclar)
- **qwen3:8b** (6.5 s): No me dejes solo, pa»: Westcol pide ayuda en la misión  
  rechazados: «Westcol intenta liberar al rehén, pero se le complican las cosas» (sin anclar); «¿Westcol logrará liberar al rehén o se le escapará?» (sin anclar); «Westcol se pierde en la operación táctica: ¿qué pasará?» (sin anclar); «¿Se salva Westcol o se le complica la misión final?» (sin anclar)

### 4:51 · Para revisar

> ¿Asegurado? ¿Tenéis grilletes, esposas? No sé dónde ir. No puede hacer. Vale, ya los tenemos. Hemos dado órdenes y los tenemos del suelo. Perfecto. ¿Cómo costaba la puta puerta? Bien, bien, bien. ¿Cuesta o no cuesta abrir puertas? Las he aprendido. Esa cuesta. Lo que más está en …

- Título actual: ¿La puerta se abre? Asalto frustrado
- **qwen2.5:7b** (6.0 s): —  
  rechazados: «¿Ibai asegura la misión final? | «No sé dónde ir» | 'Sobreviví' y Westcol se enfrentan al asalto final» (sin anclar); «Ibai: 'No sé dónde ir' durante el asalto | ¿Cómo costaba la puta puerta?» (sin anclar); «¿Cómo costaba la puerta? Ibai confiesa durante el asalto final» (sin anclar); «¿Ibai asegurará la misión? | 'No sé dónde ir' en el asalto final» (sin anclar); «Confesión de Ibai: 'No sé dónde ir' en la misión final» (sin anclar)
- **qwen3:8b** (6.5 s): No se abría, ya da energía»: el comentario que encendió el chat  
  rechazados: «¿Cuesta o no cuesta abrir puerta? Ibai se enfoca en la operación final» (sin anclar); ««No se abría, ya da energía»: Ibai explica el reto de la puerta» (sin anclar); «¿Por qué la puerta no se abría? Ibai habla de la tensión en la misión» (sin anclar); «¿Lograrán abrir la puerta? Ibai da instrucciones en la misión final» (sin anclar)

### 12:16 · Datos

> sorprendido. Ibal, va a decir algo, esto es Colombia. Eso es colombiano, oro sangre colombiana, que recorre por mi vena. Ulises, estamos preparados para la misión final. Sí, para entrar... No, para entrar en la casa. ¡Ay, gonos ramos! Sí, pero lo vais a pasar mal, ¿eh? Señores, m…

- Título actual: Misión final: recuperar una planta medicinal y liberar al secuestrado
- **qwen2.5:7b** (5.4 s): Ibai: 'Oro sangre colombiana' antes de la misión final | Oro sangre colombiana»: Ibai anuncia la misión final | ¿Ibai realmente entiende la misión final? | Ibai mezcla cultura y asalto: ¿Preparado para la misión? | Oro sangre colombiana»: Ibai comienza la misión táctica
- **qwen3:8b** (6.4 s): Ibai habla de Colombia y anuncia la misión final | ¿Por qué Ibai mencionó Colombia antes de la misión? | Esto es colombiano, oro sangre»: el grito de Ibai antes de la misión | Ibai se emociona al hablar de Colombia antes de la misión final  
  rechazados: «Ibai le hace un llamado a Westcol antes del asalto» (sin anclar)

### 13:49 · Humor

> Garamos esta primera zona y podemos pasar por acá, y ya tenemos este correo y aquí ya, papi, como ha sido, rea. ¿Estás fácil, no? Sí. Sí, es tan fácil, pero claro, luego hay la situación... Claro, es diferente, es diferente. Claro, no sé... Ellos están más usados que nosotros, br…

- Título actual: Relajación y humor en la misión
- **qwen2.5:7b** (5.7 s): —  
  rechazados: «Sobreviví admite que los delincuentes son más profesionales» (sin anclar); ««Los bandidos están más usados que el policía»: confesión de Sobreviví» (sin anclar); «¿Pueden superar a los bandidos en el entrenamiento?» (sin anclar); «Sobreviví vs Bandidos: ¿Quién será más eficaz?» (sin anclar); «¿Podrán Sobreviví y Ibai derrotar a los bandidos?» (sin anclar)
- **qwen3:8b** (6.8 s): —  
  rechazados: «Sobreviví confía en Ibai, aunque vea la ventaja de los bandidos» (sin anclar); ««Ellos están más usados que nosotros, bro»: la opinión de Sobreviví» (sin anclar); «¿Confían en que no fallarán? Sobreviví lo asegura» (sin anclar); «Sobreviví: los bandidos son más experimentados, pero no importa» (sin anclar); «¿Dónde está el rehén? Sobreviví se lo asegura a Ibai» (sin anclar)

### 20:14 · Humor

> Y antes ha dicho una cosa muy importante, que es que los malos también están nerviosos. Claro. Pero si yo me pongo tenso esto que está preparado. La realidad, hemos salvado al reen. ¿Cuál es así? ¡Es así! La Policía colombiana lo volví a hacer. La Policía Nacional colombiana haci…

- Título actual: ¡La Policía Colombia en España! ¿Qué pasó?
- **qwen2.5:7b** (6.4 s): —  
  rechazados: «Sobreviví revela: los malos también están nerviosos. ¿Qué pasó con la Policía colombiana?» (formato); ««Los malos también están nerviosos»: Sobreviví comparte un incidente con la Policía en España» (formato); «¿Qué escondes Sobreviví tras decir que los malos también están nerviosos?» (sin anclar); «Sobreviví vs. la Policía colombiana: ¿Qué sucedió en España?» (sin anclar); «Sobreviví confiesa: un incidente con la Policía nacional colombiana. ¿Dónde y cuándo?» (formato)
- **qwen3:8b** (6.5 s): —  
  rechazados: «Sobreviví habla sobre la tensión de los malos y un incidente con la policía» (sin anclar); ««La Policía colombiana lo volvió a hacer»: la observación de Sobreviví» (sin anclar); «¿Por qué Sobreviví mencionó un incidente con la policía?» (sin anclar); «¿La Policía colombiana actuó en España? Sobreviví lo revela» (sin anclar); «Sobreviví confiesa un incidente con la policía en España» (sin anclar)

### 5:35 · Para revisar

> Vale, señores, West Col, Ibai, segundo ejercicio. En este ejercicio haremos un recorrido de tiro táctico. Como hemos dicho antes, primero algo físico para subir pulsaciones. Corremos un poco en cinta, nos pasaremos la rueda y después habrá tres tiros aquí. Uno será de pie, otro d…

- Título actual: Westcol: recorrido de tiro táctico
- **qwen2.5:7b** (6.3 s): Ibai enseña a Westcol el recorrido de tiro táctico paso a paso | De pie, buena comunicación»: Ibai demuestra un ejercicio táctico a Westcol | ¿Ibai y Westcol podrán seguir las instrucciones en el tiro táctico? | Ibai y Westcol enfrentan el recorrido de tiro táctico: ¿quién pasa mejor? | Tiro táctico: Ibai y Westcol corren en cinta y pasan la rueda
- **qwen3:8b** (6.9 s): Ibai le enseña a Westcol el tiro táctico | ¿Cómo se hace un tiro táctico? Ibai lo explica a Westcol | Ibai le da la cobertura a Westcol | Ibai le enseña a disparar en posición de rodilla  
  rechazados: «Ibai y Westcol se preparan para el asalto | ¿Lograrán coordinarse?» (sin anclar)

### 8:33 · Para revisar

> ¡Yo, se me casquillo! Pues arreglalo, Juli, Juli. Juli, seis. A ahora. ¡Soy, soy, voy, Escuchadme, nos han matado 30 veces. Uescol, por favor, se te han casquillo. Me han matado a mí y mi familia. Una cosita, ahora que sabéis que ya has practicado que sepáis que existe esto, ¿est…

- Título actual: ¿Estás preparado para el ataque?
- **qwen2.5:7b** (5.6 s): Entrenador grita: 'Soy, soy, voy, Escuchadme' | El entrenador se exaspera: 'Ya nos han matado'  
  rechazados: «¿Para qué es esto?» (sin anclar); «Instrucciones frustrantes: 'Nos han matado 30 veces'» (filtro de la app); «¿Están preparados para la misión final?» (sin anclar)
- **qwen3:8b** (6.9 s): Soy, soy, voy, Escuchadme, nos han matado 3,000 veces»: el grito del entrenador  
  rechazados: «Entrenador le da instrucciones a Ibai y Westcol en un ejercicio táctico» (sin anclar); «¿El entrenador les dijo que les matarían 30 veces a Ibai y Westcol?» (sin anclar); «El entrenador le exige a Ibai y Westcol que se preparen para la misión» (sin anclar); «¿Qué significa que les mataron 30 veces a Ibai y Westcol? El entrenador lo explica» (formato)

### 10:29 · Para revisar

> ¿Sí? La pregunta... ¿Quién va a subir de los dos? Carlos, solo puedes subir uno. Sí. Yo veo, ahí está muy flasco. Yo creo que subes un momentico. ¡Arriba! ¡Arriba! ¡Arriba! ¡Arriba! ¡Te aguanto! ¡Sube! ¡Sube! ¡Que bien! ¡Que bien, Ranita! ¡Que bien, Ranita! ¡Que bien, Ranita! ¿Qu…

- Título actual: ¿Quién sube a la azotea?
- **qwen2.5:7b** (6.4 s): —  
  rechazados: «Sobreviví motiva a Carlos: '¡Que bien, Ranita!' | ¿Podrá subir?» (sin anclar); «'¡Que bien, Ranita!' el apoyo incondicional de Sobreviví | ¿Subirá Carlos?» (sin anclar); «Sobreviví anima a Carlos: '¡Que bien, Ranita!' | ¿Lo lograrán?» (sin anclar); «Sobreviví bromea con Carlos: '¡Que bien, Ranita!' | ¿Subirá?» (sin anclar); «Sobreviví motiva a 'Ranita': '¡Que bien, Ranita!' | ¿El desafío lo superará?» (sin anclar)
- **qwen3:8b** (7.0 s): ¿Subirá Carlos a la escalera? | Más capucha, más capucha»: el llamado que busca identificar al objetivo | ¿Tiene posición de atiro?  
  rechazados: «Motiva a Carlos para subir a la escalera simulada | «Por Colombia, Papi»: el grito que encendió la energía» (sin anclar); «¿Quién es el sufusil arriba, eh? | La pregunta que encendió el apoyo de los instructores» (filtro de la app)

### 13:20 · Para revisar

> Sabemos la puerta de entrada, que será este acceso que está marcado y la premisa que tenéis que tener para que más o menos haga algo lógico, es que no dejéis nada en vuestras espaldas. Encontraréis puertas con un triángulo verde, que quiere decir que esa puerta se pueda abrir, y …

- Título actual: ¿Cómo entraremos?
- **qwen2.5:7b** (5.9 s): El entrenador le da un giro al asalto: 'No dejéis nada en vuestras espaldas' | El entrenador se enfoca en 'no dejar nada en vuestras espaldas' | ¿Cómo no olvidar esto? 'No dejéis nada en vuestras espaldas' | Entrenador: 'No dejéis nada en vuestras espaldas' y más cosas  
  rechazados: «¿Saben las reglas del asalto? 'No dejéis nada en vuestras espaldas'» (sin anclar)
- **qwen3:8b** (6.6 s): ¿Qué significa el triángulo verde en la misión? | No dejes nada en las espaldas: la regla que define el asalto  
  rechazados: «Entrenador explica las señales clave para el asalto | «No dejéis nada en vuestras espaldas»» (sin anclar); «El entrenador le da las reglas al equipo | ¿Seguirán las instrucciones?» (sin anclar); «El entrenador les dice lo que deben hacer | «Cubriéndose de este lado»» (sin anclar)

### 14:20 · Emoción

> Mi primera misión oficial. Ay, Dios... Ha llegado el momento. Todo lo que hemos hecho durante el día de hoy, toda la formación es para este ejercicio. Es los objetivos, ¿qué son? Las plantas y el reen. Las plantas y el reen. La planta y el reen. La planta y el reen. Si cometemos …

- Título actual: Emoción y tensión en la primera misión
- **qwen2.5:7b** (5.5 s): —  
  rechazados: «Sobreviví explica por qué la misión final puede costar vidas» (sin anclar); ««Las plantas y el reen»: Ibai advierte sobre los riesgos» (sin anclar); «¿Conoces los riesgos de la misión final?» (sin anclar); «Ibai confiesa: «Si cometemos algún error, alguien puede morir»» (sin anclar); «Sobreviví revela la gravedad de la misión final» (sin anclar)
- **qwen3:8b** (6.7 s): ¿Un error en la misión final podría costar la vida de alguien?  
  rechazados: «Sobreviví y Westcol escuchan con atención la advertencia de Ibai sobre la misión final» (formato); ««Las plantas y el reen»: Ibai advierte que un error puede costar la vida» (sin anclar); «Ibai se toma la misión final muy en serio: ¿qué pasa si fallan?» (sin anclar); «Sobreviví y Westcol escuchan en silencio la advertencia de Ibai» (sin anclar)

### 1:57 · Para revisar

> Deberán coger el ariete doble, un ariete que pesa 30 kilos. Lo cogeremos entre los dos, nos aproximaremos a la puerta y tenéis que transmitir la energía lo más recto posible hacia la puerta. Tenemos que tener coordinación ahí, ¿cierto? Si hacen un péndulo y se quedan muy cerca o …

- Título actual: Westcol: Aritetes Pesados y estrés físico
- **qwen2.5:7b** (6.3 s): El entrenador confiesa: «Hay cristales en la cara, mucho grito» antes del asalto  
  rechazados: «El entrenador enseña a Ibai y Westcol cómo usar el ariete pesado para asaltar una puerta» (formato); ««Tenéis que transmitir la energía lo más recto posible»: El entrenador prepara a Ibai y Westcol» (formato); «¿Podrán Ibai y Westcol asaltar la puerta con el ariete pesado?» (sin anclar); «El entrenador promete estrés físico para preparar a Ibai y Westcol» (sin anclar)
- **qwen3:8b** (7.1 s): Tener coordinación o la puerta no se abrirá»: el consejo clave del entrenador | ¿Qué pasa si no coordinan bien el ariete? El entrenador lo explica con claridad  
  rechazados: «Entrenador prepara a Ibai y Westcol para la misión final | «Tienen que transmitir la energía lo más recto posible»» (sin anclar); «El entrenador pone tensión: «Subamos pulsaciones antes de la misión»» (sin anclar); ««Si hacen un péndulo, la energía se irá para arriba o para abajo»: la advertencia del entrenador» (formato)

### 9:32 · Para revisar

> ¡Vuelto al mío! ¡Vuelto al mío, papi! Dale, dale bien, dale. ¡Tupo! Le he dado ocho balazza. Bien, señores, bien. ¿Qué hubo ahí? Ahora bien. Buena comunicación, buena energía. ¿Puedo decir algo? Sí. ¿Pues? Respirar un poco, respirar. ¿Cuántos disparos has hecho desde ahí? No lo s…

- Título actual: Westcol, ¿neutralizas a quién en la misión final?
- **qwen2.5:7b** (6.6 s): —  
  rechazados: «Westcol desglosa el ejercicio de neutralizar a un objetivo en una escalera de helicóptero | «Neutralizar es eliminar»» (formato); «¿Entendieron el ejercicio de neutralizar a un objetivo en una escalera de helicóptero? | «Neutralizar es eliminar»» (formato); «Westcol enseña el tercer ejercicio del entrenamiento táctico | «Neutralizar es eliminar»» (sin anclar); «Entrenamiento táctico: Westcol explica cómo neutralizar a un objetivo en una escalera de helicóptero | «Neutralizar es eliminar»» (formato); «Explicación técnica: Westcol detalla el ejercicio de neutralizar a un objetivo en una escalera de helicóptero | «Neutralizar es eliminar»» (formato)
- **qwen3:8b** (6.2 s): Westcol explica el ejercicio de escalera de helicóptero | Neutralizar es eliminar»: la explicación de Westcol | Neutralizar en escalera: el ejercicio de Westcol  
  rechazados: «¿Westcol le enseñó a neutralizar a Ibai?» (sin anclar); «¿Qué significa neutralizar en el entrenamiento táctico?» (sin anclar)

### 0:57 · Para revisar

> Yo tengo por ahí una esposa también, o que ve. Esposas, linterna, defensa extensible, arma simulada. Bueno, y aquí tiene, si vay, un spray de defensa. Un spray de defensa. Sí, y no las crea que esto pesa mucho. Acá hay unas pesas también, esto es un chaleco antiguo, ¿vale? Eso es…

- Título actual: ¿Quién se lleva la linterna? Entrenamiento táctico
- **qwen2.5:7b** (5.6 s): Ulises lista el equipo para el entrenamiento táctico | ¿Qué lleva Ulises para el entrenamiento táctico? | Ulises explica las reglas del juego táctico | ¿El chaleco antiguo es suficiente para un asalto?  
  rechazados: ««Linterna, spray de defensa y chaleco antiguo»: Ulises prepara a Ibai y Westcol» (sin anclar)
- **qwen3:8b** (6.7 s): ¿Quién se atreve a romper la puerta? | ¿El ariete será el primer paso? | Ulises describe el equipo y el plan | El entrenamiento comienza con el ariete  
  rechazados: «Ulises prepara a Ibai y Westcol para el ariete | «Vais a tener que abrir esta puerta»» (sin anclar)

### 2:56 · Para revisar

> Porque así no nos va a regar el oxígeno en la mente y, seguramente, reducirimos el campo de visión, etcétera, y nos pondremos en situación. Una de una. Parece bien. A ver, ¿cómo estáis? 10 burpees. 10 burpees. Parece bien. Los canto yo, Sí, sí. Sí, no puede ser... Como que hubo u…

- Título actual: Westcol: burpees Intensos
- **qwen2.5:7b** (6.0 s): ¿Pueden hacer un burpee sin errores? | El entrenador muestra burpees perfectos  
  rechazados: «El entrenador corrige burpees a Ibai y Westcol | «Corregir burpees»: antes de la misión final» (sin anclar); «Entrenamiento táctico: burpees corregidos por el instructor | «Corregir burpees»: Ibai y Westcol» (sin anclar); «Entrenamiento táctico: burpees mal hechos | ¿Podrán hacerlo bien para la misión final?» (sin anclar)
- **qwen3:8b** (7.1 s): —  
  rechazados: «Ibai y Westcol intentan hacer burpees con ayuda del entrenador | «Esto es un video»: la frase que desató la risa» (sin anclar); «¿Cómo se hace un burpee? Ibai y Westcol lo intentan y no lo logran» (sin anclar); ««Imagina lo que tienen que hacer los realmente especialistas»: la frase de Ibai que generó risa» (formato); «El entrenador corrige a Ibai y Westcol en un burpee: ¿lo lograron?» (sin anclar); «Ibai y Westcol le piden al entrenador que les explique un burpee | «No sé»: la confesión que encendió el chat» (sin anclar)

## "ASÍ SE CONTRATAN SICARIOS EN COLOMBIA": CRIMINAL desde CÁRCEL REVELA como funciona OSCURO SISTEMA

### 22:32 · Emoción

> y saco también la pistola y la desaseguro no como yo estoy así recostó a la parella y ven la pistola entonces no me hace nada sino que salen otra vez entonces yo ya he asustado también prendo la moto y salgo a la variante en el momento que yo salgo a la variante se me pega la mot…

- Título actual: Así fue cuando dos personas con una pistola me asustaron y escapé
- **qwen2.5:7b** (5.7 s): Saco la pistola y la desaseguro»: ASÍ en plena persecución | ASÍ confiesa su enfrentamiento a sicarios con pistola y moto  
  rechazados: «ASÍ revela su choque de moto y pistola con sicarios en Colombia» (sin anclar); «¿ASÍ logrará sobrevivir a la persecución de sicarios?» (sin anclar); «ASÍ vs Sicarios: ¿Quién dominará la persecución en moto?» (sin anclar)
- **qwen3:8b** (10.1 s): Llega tantan dos»: el grito que rompe el silencio  
  rechazados: «ASÍ describe una persecución con sicarios en moto | «No me hace nada»: la frase que encendió el chat | ¿Por qué ASÍ se siente vulnerable? | ¿Escapará del peligro o se enfrentará? | «Llega tantan dos»: el grito que rompe el silencio» (sin anclar); ««No me hace nada»: la frase que encendió el chat | ASÍ narra una persecución con sicarios en moto | ¿Por qué ASÍ se siente vulnerable? | ¿Escapará del peligro o se enfrentará? | «Llega tantan dos»: el grito que rompe el silencio» (sin anclar); «¿Por qué ASÍ se siente vulnerable? | ASÍ describe una persecución con sicarios en moto | «No me hace nada»: la frase que encendió el chat | ¿Escapará del pelig, o se enfrentará? | «Llega tantan dos»: el grito que rompe el silencio» (sin anclar); «ASÍ narra una persecución con sicarios en moto | ¿Por qué ASÍ se siente vulnerable? | «No me hace nada»: la frase que encendió el chat | ¿Escapará del peligro o se enfrentará? | «Llega tantan dos»: el grito que rompe el silencio» (sin anclar)

### 4:00 · Para revisar

> ¿Qué le enseñan el que maneja la moto? Primero no lo van a poner en un área despejada si me entienden a lo poner en un área que se da con obstáculos como decir las vías más complicadas de la ciudad de ahí para lo ponen a él a que llegue o a que salga si me entienden pero si es ot…

- Título actual: ¿Entrenamiento para motociclistas en áreas complicadas?
- **qwen2.5:7b** (5.7 s): ASÍ: ‘El entrenamiento no es el mismo que en una persona normal’  
  rechazados: «ASÍ desvela el entrenamiento oscuro de los sicarios en Colombia» (sin anclar); ««¿En qué áreas les enseñan a manejar motos?»: ASÍ responde» (sin anclar); «¿En Colombia, ¿cómo se preparan a los sicarios para el crimen?» (sin anclar); «ASÍ critica el sistema que entrena a los sicarios en áreas peligrosas» (sin anclar)
- **qwen3:8b** (6.3 s): —  
  rechazados: «ASÍ revela cómo entrenan a sicarios en motos en zonas peligrosas» (sin anclar); ««Ponen en áreas con obstáculos»: el método de los sicarios en Colombia» (sin anclar); «¿Cómo entrenan a sicarios para manejar motos en zonas peligrosas?» (sin anclar); «ASÍ explica el entrenamiento de sicarios en motos: ¿es peligroso?» (sin anclar); «¿Qué le enseñan a los sicarios para manejar motos en zonas complicadas?» (sin anclar)

### 21:46 · Emoción

> con lo yo volto a mirar no son del pedazo o no es donde el donde yo vivo no yo me asusto si me entienden porque yo siento es el frío de la muerte yo llego de Javier el higo hermano como le parece que eso yo es ahí a no llevar a revolver nos llana el día que me pasó una pistola co…

- Título actual: Así fue el día que recibí una pistola en una cuadra cerrada
- **qwen2.5:7b** (5.6 s): 'No hay salida': Javier cuenta su encuentro con sicarios en la cuadra | 'El frío de la muerte': Javier en primera persona sobre sicarios  
  rechazados: «Javier: 'No me asusto, pero esto fue espeluznante'» (sin anclar); «¿Podrías haberlo pasado mejor? Javier relata su experiencia con pistolas y gasoductos» (formato); «Javier revela: 'Esa cuadra es una trampa mortal'» (sin anclar)
- **qwen3:8b** (7.8 s): Javier describe una situación de riesgo en su vecindario | ¿Por qué Javier se encontró en una cuadra llena de tensión y armas? | Javier relata un momento de tensión extrema en su vecindario  
  rechazados: ««No hay salida porque de una pila de tierra»: la experiencia de Javier en un momento de peligro» (formato); ««Se devuelve cuando yo se vuelve el diatral»: la historia de Javier que no deja indiferente» (formato)

### 17:07 · Emoción

> yo estoy en una parte entonces yo estoy ahí el llama y dice así verman usted no tiene quien me vaya a llevar un revolver a tal lado yo le regalo 100 lucitas entonces yo le digo al parcero yo la hermano pase yo y los llevo ay yo y me ganó 100 lucas y yo salgo en mi bicicleta norma…

- Título actual: Así era el enfrentamiento en la calle
- **qwen2.5:7b** (5.9 s): Yo le regalo 100 lucitas»: ASÍ acepta un riesgo y luego decide no intervenir | ¿ASÍ se metió en problemas al ayudar a transportar un revolver? | ASÍ confiesa su encuentro con una moto sospechosa mientras llevaba un revolver  
  rechazados: «ASÍ revela su experiencia con sicarios y un amigo que le pidió ayuda» (sin anclar); «ASÍ presume su habilidad para manejar situaciones peligrosas sin involucrarse» (sin anclar)
- **qwen3:8b** (6.5 s): ASÍ acepta ayudar a transportar un revolver pero se queda en la bicicleta | No voy a hacer nada, me alcanzan»: ASÍ se escapa de una situación peligrosa | ASÍ confiesa que se quedó en la bicicleta tras una persecución sospechosa | ASÍ se queda en la bicicleta al ver una moto que intenta seguirlle  
  rechazados: «¿ASÍ se salva de la moto que intenta seguirlle?» (sin anclar)

### 25:02 · Relato

> ya willian el que me el que yo le voy al revolver estaba en la calle había salido de la cárcel si porque él estaba condenado a pero no sé qué fallo encontraron y que o después de haber llevado 4 años 4 meses en la cárcel salió libertad entonces me escriben hermano cómo le pare qu…

- Título actual: Así era el enfrentamiento con willian
- **qwen2.5:7b** (6.0 s): —  
  rechazados: «Más Allá del Silencio Podcast: Revela el Peligro de los Sicarios en Colombia» (sin anclar); ««Estoy Amenazado por un Sicario»: La Revelación de Más Allá del Silencio Podcast» (sin anclar); «¿Cómo Lidiar con un Sicario en Colombia? Así lo Revela el Podcast» (sin anclar); «El Sistémico Peligro de los Sicarios: Así lo Confiesa Más Allá del Silencio Podcast» (formato); «¿Qué Pasará con el Entrevistado de Más Allá del Silencio Podcast? Amenazas en Colombia» (formato)
- **qwen3:8b** (6.7 s): El entrevistado se siente amenazado por willian, exsicario en libertad | Me entiende como le explicaba»: el miedo que le genera willian | ¿Por qué se siente en peligro al ver a willian en la calle? | Willian, exsicario en libertad, le genera miedo al entrevistado  
  rechazados: «Llega a Virginia Ríos y se muere de miedo: su historia» (sin anclar)

### 13:41 · Emoción

> hablando de poner valer a alguien sólo esto sucede en el mundo del narco o alguien más pide que le cobren sobre alguien pues la verdad rafa muchas veces los cobros no se hacen simplemente por guerras de african y mi pico muchas veces los cobros se hacen por parte de que de que la…

- Título actual: Así es como se entregan las armas en el mundo del narco
- **qwen2.5:7b** (5.5 s): ASÍ explica que los cobros son más complejos que guerras de narco | Los cobros no son solo por guerras" ASÍ revela | ASÍ desvela que los cobros son por razones personales, no solo por guerras | ¿Qué ocurre cuando la suegra pide sicarios?  
  rechazados: «¿Sabías que los cobros pueden ser por problemas familiares?» (sin anclar)
- **qwen3:8b** (6.3 s): ASÍ revela que los cobros no son solo por guerra, sino por familia | ¿Por qué una mujer contrató sicarios? ASÍ lo explica | ASÍ explica que los cobros pueden ser por el suegro o la suegra | ¿Qué pasó con el señor que mandó a hacer un cobro? ASÍ lo revela  
  rechazados: ««Contrataron sicarios por el marido»: el caso que ASÍ explica» (sin anclar)

### 18:36 · Emoción

> me me voló con una banda criminal que fue muy muy muy sonar y muy perseguía a la vigina Rizaralda que supuestamente la banda la él me involucra en ahí pero pues yo no tengo nada que ver pero como yo mantenía en el sitio donde se desempeñaba tanto es a mí me llevan para el comando…

- Título actual: Así fue la captura y liberación
- **qwen2.5:7b** (5.4 s): ASÍ cuenta su encuentro con sicarios y la policía | Me llevaron al comando de la policía»: ASÍ relata su historia | ¿Qué pasó con ASÍ y la banda criminal? | ASÍ, el miembro del podcast, revela su experiencia con la criminalidad  
  rechazados: «ASÍ: «Me llevaron a la cárcel por error»» (sin anclar)
- **qwen3:8b** (6.3 s): ASÍ fue llevado a la policía por una banda criminal | ¿Por qué ASÍ fue arrestado sin antecedentes? | ASÍ relata su detención en el bunker de la fiscalía | No tengo nada que ver»: la confesión de ASÍ en el podcast | ASÍ revela cómo lo llevaron a la policía sin antecedentes

### 2:00 · Relato

> sea de donde soy yo se respeta mucho los niños, los ancianos y las mujeres. sea la persona que va a ir a hacer un un pago por una mujer o por esto no allá no se hace, si me entienden. ¿Cómo los entren? O sea hay dos clases de entrenamiento cierto. Primero es la parte de parte del…

- Título actual: Entrenamiento de los delincuentes: roles y métodos
- **qwen2.5:7b** (5.5 s): Respeto niños y ancianos»: ASÍ revela las reglas de sicariato | ASÍ: 'No se trata de niños, ancianos o mujeres'  
  rechazados: «ASÍ explica cómo se entrena a los sicarios en Colombia» (sin anclar); «¿Cómo entrena a los sicarios? ASÍ lo explica en su podcast» (sin anclar); «Entrenamiento para sicarios: ASÍ lo revela en su podcast» (sin anclar)
- **qwen3:8b** (6.2 s): ¿Respetan a los niños y mujeres? ASÍ lo confirma en el directo  
  rechazados: «ASÍ revela cómo se entrenan los sicarios en Colombia | «No se hace por una mujer»» (sin anclar); «¿Cómo entrenan a los sicarios? ASÍ lo explica en el podcast» (sin anclar); «ASÍ describe el entrenamiento para sicarios: ¿es lo que parece?» (sin anclar); ««No se hace por una mujer»: ASÍ revela las reglas del sistema» (sin anclar)

### 32:40 · Relato

> pero no porque porque no haya querido declarar sino que después de que se termina la audiencia donde lo sacan a ellos el señor se me acerque él es un f2 si sabe que es una f2 cierta y la parte del f2 que era la policía antes del das si hasta hace el ex pensionado del f2 entonces …

- Título actual: Así era mi vida en la cárcel
- **qwen2.5:7b** (6.1 s): No declaré porque necesitaba que saliera»: el secreto tras la audiencia | ¿Qué pasó después de la audiencia? El entrevistado revela detalles sorprendentes  
  rechazados: «Más Allá del Silencio Podcast: El entrevistado revela por qué no declaró en una audiencia» (formato); «El sistema judicial en Colombia: ¿Qué ocurre detrás de las escenas?» (sin anclar); «Dos hombres lo sacan para Cali: ¿Cuánto tiempo lleva en la cárcel el entrevistado?» (formato)
- **qwen3:8b** (6.6 s): ¿Por qué el entrevistado calló ante un ex policía? | ¿Lleva tiempo en la cárcel o fue capturado? | El sistema lo saca de la audiencia: la escena clave  
  rechazados: «Más Allá del Silencio revela un pacto en la cárcel | «No declaré porque lo vea»» (sin anclar); «El f2 le pidió callar: la revelación del podcast» (sin anclar)

### 4:32 · Para revisar

> ¿Y al parrillero que le enseñan? O sea yo no estuve en escuela de circunstancia las conozco si me entienden pero fue el parrillero el que hace el cobro como tal después de que usted hace el cobro así como el de la moto de la encargada de sacar a usted usted de la encargada de el …

- Título actual: ¿Cómo se enseña a los parrilleros en la calle?
- **qwen2.5:7b** (5.6 s): ASÍ: 'Estuve en la calle desde los 13 años' - ¿Qué hizo? | ASÍ confiesa su antiguo papel en la escuela de circunstancia  
  rechazados: «ASÍ revela su oscura experiencia desde los 13 años» (sin anclar); «'Desde los 13 años': ASÍ explica su pasado criminal» (sin anclar); «¿A qué edad comenzó ASÍ en el mundo criminal?» (sin anclar)
- **qwen3:8b** (6.7 s): ASÍ habla de su vida en la calle desde los 13 años | ¿A qué edad empezó a vivir en la calle? ASÍ lo confiesa | ¿Cómo vivía en la calle desde los 13? ASÍ lo cuenta  
  rechazados: ««Yo estoy en el mundo de la calle desde los 13 años»: la revelación de ASÍ» (filtro de la app); «ASÍ explica cómo se movilizaba en el mundo criminal | «El homicidio y se les pega»» (sin anclar)

### 5:26 · Para revisar

> ¿Qué fue lo que hizo? ¿Cómo comenzó? O sea yo a los 13 años soy un muchacho normal si me entienden por allá donde yo vivo tuve un problema con un muchacho de mi misma edad de yo tenía 13 años él tenía 14 años y bueno una riña yo le pegue ya al rato de haber pasado el problema me …

- Título actual: ¿Cómo comenzó su vida en la calle a los 13 años?
- **qwen2.5:7b** (5.4 s): —  
  rechazados: «ASÍ revela su historia de violencia a los 13 años» (sin anclar); «'A los 13 pegué y luego llegó un sicario'» (sin anclar); «¿Qué pasó después de la riña a los 13?» (sin anclar); «ASÍ comienza su relato de crímenes juveniles» (sin anclar); «'Llegó un hermano después de la pelea'» (sin anclar)
- **qwen3:8b** (6.2 s): ASÍ habla de su riña a los 13 y el hermano que llegó después | Yo le pegué, y luego llegó su hermano | ASÍ revela cómo una pelea lo metió en problemas | ¿El hermano del otro chico lo buscó? ASÍ lo confiesa  
  rechazados: «¿Qué pasó después de la riña? ASÍ lo cuenta» (sin anclar)

### 35:48 · Para revisar

> arma encima yo no estaría acá porque pues yo no me hubiera dejado coger y ellos tampoco me han dejado ir si me entiende Juan Camilo gracias gracias por tu tiempo hombre y buena suerte gracias a ellos también con mucho gusto

- Título actual: Gracias a los entrevistados por su tiempo
- **qwen2.5:7b** (5.7 s): Yo no me hubiera dejado coger»: ASÍ responde a Juan Camilo  
  rechazados: «ASÍ revela su historia oscura y agradece a Juan Camilo» (sin anclar); «¿ASÍ escapará de la cárcel? Su respuesta sorprendió» (sin anclar); «ASÍ agradece y revela su experiencia con armas y cárcel» (sin anclar); «Despedida turbulenta: ASÍ responde a Juan Camilo sobre armas y cárcel» (sin anclar)
- **qwen3:8b** (6.1 s): Gracias por tu tiempo»: ASÍ agradece a Juan Camilo en su situación | ¿ASÍ le confesó a Juan Camilo algo grave sobre su pasado?  
  rechazados: «ASÍ responde a Juan Camilo sobre su situación en la cárcel y armas» (sin anclar); «ASÍ habla de su complicada situación con armas y cárcel» (sin anclar); «¿Qué reveló ASÍ sobre su vida en la cárcel y armas?» (sin anclar)

### 0:15 · Relato

> Cada vez que llego a cárceles a entrevistar hay algo que me llama la atención, sobre todo en el tema ¿Cómo aprenden? Aprenden en la calle o hay escuelas de ciclos. Y también uno comienza a escuchar términos como ponen a valer a alguien y hay que cobrarlo. Juan Camilo gracias, gra…

- Título actual: Cómo aprenden los delincuentes en la calle y en las escuelas
- **qwen2.5:7b** (5.6 s): Rafa revela cómo aprendió en la calle y las 'escuelas de ciclos' | ¿Cómo aprendiste en la calle?»: Rafa responde | ¿Escuelas de ciclos para delincuentes existen? | Rafa: 'Aprendí en la calle, pero hay escuelas de ciclos' | Revelado: las 'escuelas de ciclos' para delincuentes
- **qwen3:8b** (11.2 s): —  
  error: Unterminated string starting at: line 1 column 437 (char 436)

### 3:25 · Para revisar

> Al delamoto que le enseñan pues es que el delamoto es el encargado de su vida como dicho si me entienden usted es el que hace el tío pero el encargado que usted regrese es el delamoto porque sea donde sea lo tiene que sacar como muchas veces se le presentan inconvenientes que pas…

- Título actual: ¿Quién es el encargado de tu vida en el delamoto?
- **qwen2.5:7b** (6.4 s): ¿Quién decide tu suerte? El delamoto responde | El delamoto explota sobre su rol en el mundo de los sicarios  
  rechazados: «El delamoto revela su papel en el oscuro negocio de los sicarios | 'El encargado de tu vida es el delamoto'» (sin anclar); «'El encargado de tu vida es el delamoto': así funciona el negocio de los sicarios | ¿Quién está detrás de tus decisiones?» (formato); «El delamoto confiesa su responsabilidad en la vida de los contratistas de sicarios | 'El encargado de tu vida es el delamoto'» (formato)
- **qwen3:8b** (6.6 s): ¿Quién se queda con la vida cuando el sicario falla? | El delamoto: ¿quién se responsabiliza por la vida de los contratados? | La vida suya depende el que da el arrastre»: revela el delamoto  
  rechazados: «El delamoto explica su rol como responsable de vidas en Colombia | «Tiene que responder con que usted llegue»» (sin anclar); ««Tiene que responder con que usted llegue»: el rol del delamoto en el sistema criminal» (formato)
