# Resultados y seleccion de la entrega

## Candidato publicado

**Equipo A2: C++20, Iterated Greedy secuencial, destruccion de 6 ordenes, temperatura max(1, 0.01 x coste inicial), reinicio tras 400 ciclos sin mejora global y 57 segundos de CPU.**

La release congela `cpp-ig-r400`. La entrada de entrega llama expresamente a `ig_search<6,100,400>`; la funcion base del laboratorio conserva el reinicio a 200. El ejecutable se enlaza estaticamente con los runtimes de GCC/MinGW para funcionar con las DLL del propio Windows.

## Que se minimiza

Todas las ordenes estan disponibles desde cero. Para una secuencia comun a todas las maquinas, cada operacion empieza cuando han terminado tanto la operacion anterior de esa orden como la orden anterior en esa maquina:

```text
C[k,m] = max(C[k-1,m], C[k,m-1]) + duracion[orden[k],m]
S = suma de C[k,ultima_maquina]
Fmed = S / numero_de_ordenes
```

Durante la busqueda se compara S como entero de 64 bits. Fmed se calcula al mostrar el resultado. No se minimiza solamente la finalizacion de la ultima orden. Las heuristicas devuelven la mejor secuencia encontrada; no certifican el optimo global.

## Algoritmos del laboratorio

| Algoritmo | Funcionamiento |
|---|---|
| Aleatorio | Genera permutaciones uniformes con Fisher-Yates y conserva la mejor. |
| Local con reinicios | Primera mejora por insercion y despues intercambio. Tras mejorar vuelve a explorar inserciones; al estancarse comienza desde otra permutacion aleatoria. |
| Recocido simulado | Propone inserciones y acepta empeoramientos con probabilidad exp((coste anterior - nuevo) / temperatura). Temperatura inicial max(1, 0.01 x coste inicial), enfriamiento 0.9995 y recalentamiento cada 10 000 propuestas. |
| Genetico | Poblacion de 32, torneo de 3, cruce OX, mutacion por insercion con probabilidad 0.2 y un individuo de elite. |
| Iterated Greedy | Ordena inicialmente por suma creciente de duraciones, construye por insercion para Fmed y aplica busqueda local. Retira varias ordenes, las reinserta, mejora la secuencia y acepta con Metropolis. Reinicia al acumular el numero configurado de ciclos sin mejora global. |

Las implementaciones comparten SplitMix64, barajado, parametros y desempates. El evaluador incremental reutiliza prefijos y buffers. En IG cada ciclo realiza construccion parcial y busqueda local; el contador de evaluaciones no equivale a ciclos completos ni a una cantidad fija de trabajo entre algoritmos.

## Diseno de las pruebas

- Cada ejecucion usa un proceso nuevo y se ejecuta secuencialmente, alternando candidatos.
- El controlador mide externamente CPU del proceso y sus hijos mediante Job Objects de Windows. Incluye arranque, lectura, inicializacion, salida y JIT cuando corresponde.
- El presupuesto principal es de 57 segundos de CPU total. El laboratorio admite hasta 0.5 segundos de finalizacion y corta por seguridad al superar 60 segundos de CPU o el limite de reloj.
- Con varios hilos, todos consumen el mismo presupuesto de CPU agregado. No son 57 segundos para cada hilo.
- Las secuencias de referencia, iniciales y finales se comprueban de forma independiente: permutacion completa, suma entera y Fmed declarado.
- Se guardan inmediatamente JSONL y CSV, con manifiestos de entradas, versiones, compilacion y equipo. Se permite reanudar sin mezclar otra configuracion o revision.
- Las pruebas por evaluaciones son reproducibles con una semilla y revision fijas. Bajo limite de CPU la trayectoria final tambien depende del rendimiento y la carga del equipo.

## 1. Lenguajes y algoritmos

Diez instancias de 75 x 20, duraciones uniformes enteras de 1 a 99, semillas de generacion 2001-2010 y cinco semillas de ejecucion (1-5). Se completaron **1250 pruebas con CPU limitada**, 50 por combinacion, y **250 referencias aleatorias de 10 000 evaluaciones**: 1500 resultados finales validos.

| Algoritmo | C++ | Rust | Java | Python | Numba |
|---|---:|---:|---:|---:|---:|
| Aleatorio | 3535.157 | 3535.621 | 3536.249 | 3604.716 | 3549.968 |
| Local con reinicios | 3148.596 | 3150.358 | 3150.910 | 3453.367 | 3159.582 |
| Recocido | 3169.798 | 3170.836 | 3170.066 | 3209.407 | 3178.167 |
| Genetico | 3203.933 | 3204.589 | 3204.325 | 3258.299 | 3205.426 |
| Iterated Greedy | 3112.748 | 3113.183 | 3113.542 | 3215.480 | 3124.108 |


C++/IG obtuvo el menor Fmed medio (3112.748). La ventaja frente a Rust/IG fue pequena; se comparan estas implementaciones concretas. Las cinco modalidades dieron la misma calidad para las 10 000 permutaciones comunes. Ese ensayo incluye generacion, evaluacion y arranque, y no constituye un microbenchmark aislado del evaluador.

El JSONL original conserva 1502 lineas, incluidas anotaciones y reintento de una interrupcion externa; al tomar el ultimo registro de cada identificador quedan 1500 resultados validos. El informe mantiene ese historial.

## 2. Hilos e instrucciones de CPU

Cinco instancias de ajuste (semillas 1001-1005), dos repeticiones y seis candidatos: 60 ejecuciones validas. `v3` indica el nivel de instrucciones x86-64-v3; `tN`, N hilos. `t0` selecciona automaticamente los 16 procesadores logicos de este equipo.

| Candidato | Fmed medio | CPU media (s) | Reloj medio (s) |
|---|---:|---:|---:|
| cpp-v3-t2 | 3142.425 | 57.020 | 31.557 |
| cpp-ref | 3143.585 | 57.016 | 61.731 |
| cpp-v3-t1 | 3143.615 | 57.016 | 63.289 |
| cpp-v3-t4 | 3143.649 | 57.036 | 18.661 |
| cpp-v3-t8 | 3144.517 | 57.050 | 12.574 |
| cpp-v3-t0 | 3148.376 | 57.080 | 7.302 |


Dos hilos ganaron esta primera comparacion por un margen reducido. Usar todos los hilos redujo el tiempo de reloj, pero empeoro la calidad dentro de la misma CPU total. La compilacion v3 por si sola no demostro una mejora.

La confirmacion uso diez instancias nuevas (semillas 3001-3010), cinco repeticiones y 100 ejecuciones validas: referencia secuencial **3130.614133**, dos hilos **3131.732267**. La referencia gano 24 parejas, empato 13 y perdio 13. Se eligio un hilo para el ajuste posterior.

## 3. Ajuste de parametros de IG

Se modifico un parametro cada vez, manteniendo los demas. Cinco instancias de ajuste y dos semillas: 70 ejecuciones.

| Sufijo | Cambio respecto a la base |
|---|---|
| base | Destruccion 6, factor de temperatura 0.01, reinicio 200. |
| d4 / d8 | Destruccion de 4 / 8 ordenes. |
| t50 / t200 | Factor de temperatura 0.005 / 0.02. |
| r100 / r400 | Reinicio tras 100 / 400 ciclos sin mejora global. |

| Variante | Fmed medio | Ejecuciones | Estado |
|---|---:|---:|---|
| cpp-ig-base | 3147.359 | 10 | COMPLETO |
| cpp-ig-d4 | No comparable | 10 | DESCARTADO |
| cpp-ig-d8 | 3148.880 | 10 | COMPLETO |
| cpp-ig-r100 | 3149.273 | 10 | COMPLETO |
| cpp-ig-r400 | 3147.345 | 10 | COMPLETO |
| cpp-ig-t200 | 3149.831 | 10 | COMPLETO |
| cpp-ig-t50 | No comparable | 10 | DESCARTADO |


Hubo 68 ejecuciones validas y dos timeout (d4 y t50), coincidentes con suspensiones del equipo por cierre de tapa. Se conservaron y no se repitieron; esas variantes quedaron excluidas del ranking fiable. r400 gano entre los candidatos completos por solo 0.013333 puntos de Fmed (dos victorias, seis empates y dos derrotas frente a la base). Esa diferencia inicial requeria validacion independiente.

## 4. Validacion final de r400

Diez instancias nuevas de 75 x 20 (semillas 4001-4010) y cinco semillas de ejecucion. **100 ejecuciones validas, 50 parejas y ningun fallo.**

| Metrica | Base r200 | Candidato r400 |
|---|---:|---:|
| Fmed medio | 3096.595467 | 3094.742667 |
| Mediana | 3087.846667 | 3083.560000 |
| Desviacion entre muestras | 48.756435 | 48.820000 |
| Mejor Fmed | 3037.653333 | 3033.933333 |
| CPU media (s) | 57.032187 | 57.038125 |
| Reloj medio (s) | 61.006197 | 60.881696 |
| Evaluaciones medias | 63276086.40 | 64580087.04 |

La reduccion media de Fmed es **1.852800 puntos (0.059833 %)**. r400 gano 25 parejas, empato 12 y perdio 13; mejoro la media en siete de las diez instancias.

Se calculo la diferencia candidato menos base por pareja y se promedio dentro de cada instancia. El intervalo bootstrap del 95 % remuestrea esas diez medias por instancia 10 000 veces con semilla cero: **[-3.269067, -0.456533]**. Quedo completamente por debajo de cero y cumplio el criterio de seleccion establecido antes de ver la validacion.

## Interpretacion y limites

La mejora frente a r200 es pequena y esta respaldada por esta validacion local. La comparacion completa con d4 y t50 no quedo resuelta por sus interrupciones. No se demuestra que r400 sea el mejor IG posible ni que gane en cualquier instancia o equipo. No se han probado combinaciones de varios parametros modificados a la vez.

Las medias de fases con diferentes instancias no son comparables directamente. La desviacion de la tabla mezcla dificultad entre instancias y variacion entre semillas. El bootstrap se usa para esta comparacion de parametros y no sustituye el test oficial del concurso frente a la busqueda aleatoria.

Equipo de validacion: **13th Gen Intel(R) Core(TM) i7-13620H**, Windows (Windows-11-10.0.26300-SP0), 16 procesadores logicos. Compilador registrado: **g++ (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r8) 13.2.0**. La maquina prevista por las bases es un Ryzen 9 9900X; no se ha medido esta entrega alli.

## Evidencia publicada

Los [resumenes, CSV y manifiestos](results/) conservan la configuracion original de cada fase. El [ZIP de resultados](https://github.com/Joseleelsuper/OptContest/releases/download/v1.0.0/optcontest-resultados.zip) contiene tambien los JSONL originales y los informes HTML navegables tras extraerlo. Los datos se distribuyen separados de la entrega A2.

La [seleccion final](results/ig-tuning/selection.json) registra la decision y el intervalo. La revision experimental del ajuste es `c64664b`; esta release anade empaquetado estatico, identificadores de equipo alfanumericos e instrucciones, sin cambiar la busqueda r400 validada.
