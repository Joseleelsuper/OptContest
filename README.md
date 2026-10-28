# OptContest

Banco de pruebas para minimizar **Fmed** en un flow shop permutacional: cinco algoritmos × C++, Rust, Java, Python y Python con Numba. Windows 11 x64.

## Ejecutar

Necesitas Python 3.14, GCC/MinGW con C++20 y un JDK 17+. La preparación instala NumPy/Numba en `.venv` y Rust 1.99.1 en `.tools`, sin modificar el PATH global.

```powershell
python bench.py setup
python bench.py check
python bench.py run
```

`check` compila y comprueba las 25 combinaciones y sus entregas independientes. `run` ejecuta secuencialmente la campaña completa: **10 instancias × 5 repeticiones × 25 combinaciones × 57 s de CPU**, más las referencias de 10 000 permutaciones. Aproximadamente 20 horas de CPU para la parte principal; el tiempo real depende del equipo.

Resultados en `results/full/report.html`, `runs.csv` y `runs.jsonl`. El informe incluye medias, dispersión, mínimos, máximos, tiempos y resultados por instancia. Se actualiza al terminar cada ejecución. Repite el mismo comando para reanudar; cambiar código, configuración o entorno exige otra carpeta.

La campaña evita la suspensión automática del equipo mientras está activa. Mantén la tapa abierta durante las ejecuciones.

```powershell
python bench.py report results/full
python bench.py run --instances 1 --repetitions 1 --cpu-budget 10 --results results/pilot
```

## Medición y comparación

- Cada ejecución utiliza un proceso nuevo. La CPU externa incluye lanzadores, procesos hijos, arranque, lectura, inicialización, JIT y salida mediante [Job Objects de Windows](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
- Numba compila en cada ejecución, sin caché del núcleo. Python usa el mismo código interpretado y NumPy como almacenamiento.
- En modo CPU, Numba reserva un segundo del presupuesto para preparar la salida y cerrar LLVM; ese tiempo también se mide externamente. El límite por evaluaciones no cambia.
- Las versiones comparten SplitMix64, muestreo sin sesgo, Fisher–Yates, parámetros y desempates: se conserva la primera alternativa con el mismo coste. La referencia aleatoria visita exactamente las mismas 10 000 permutaciones en todas las modalidades.
- Se compara la suma entera de finalizaciones de la última máquina, con todas las órdenes disponibles en cero. `Fmed = suma / n`. Cada secuencia y coste se recalculan con un evaluador independiente.
- `fmed_reference` corresponde a la permutación aleatoria común. El valor inicial real es el mejor individuo de la población inicial en GA y la construcción por inserción en IG. En los otros algoritmos coincide con la referencia.
- Las evaluaciones cuentan candidatos, incluidas secuencias parciales de IG. No son una unidad de trabajo equivalente entre algoritmos distintos.
- La búsqueda comprueba CPU cada 32 evaluaciones. El presupuesto solicitado es 57 s; se admiten hasta 0.5 s de finalización en el laboratorio y se termina el árbol de procesos si supera 60 s. Los fallos y excesos permanecen registrados y descartan al candidato del ranking fiable.

Se generan cinco instancias de ajuste con semillas 1001–1005 y diez de evaluación con semillas 2001–2010, siempre de 75 órdenes × 20 máquinas y tiempos uniformes de 1 a 99. La campaña usa semillas de ejecución 1–5. El manifiesto conserva hashes, versiones, opciones de compilación y equipo. El conjunto de ajuste queda separado de la evaluación; esta versión compara parámetros fijos, sin ajuste automático.

## Algoritmos

| ID | Implementación común |
|---|---|
| `random` | Permutaciones aleatorias; conserva la mejor. |
| `local` | Primera mejora por inserción y después intercambio; reinicia al alcanzar un óptimo local. |
| `sa` | Inserción, aceptación Metropolis, temperatura `max(1, 0.01 × coste inicial)`, factor `0.9995` y recalentamiento cada 10 000 propuestas. |
| `ga` | Población 32, torneo 3, cruce OX siempre, mutación por inserción 0.2, élite 1 y reemplazo generacional. |
| `ig` | Orden inicial por suma creciente de duraciones; construcción por inserción para Fmed, búsqueda local, extracción de hasta 6 órdenes, reconstrucción y aceptación Metropolis con temperatura `max(1, 0.01 × coste inicial)`. Reinicia tras 200 ciclos sin mejora global. |

Los evaluadores reutilizan prefijos y buffers. Son heurísticas: devuelven la mejor solución encontrada durante su presupuesto.

Interfaz común:

```powershell
build\cpp.exe --algorithm ig --instance instances\examples\Doc11.txt --seed 42 --cpu-budget 57
build\rust.exe --algorithm ig --instance instances\examples\Doc11.txt --seed 42 --max-evaluations 10000
java -cp build/java Solver --algorithm ig --instance instances/examples/Doc11.txt --seed 42 --cpu-budget 57
.venv\Scripts\python.exe solvers/python/main.py --algorithm ig --instance instances/examples/Doc11.txt --seed 42 --cpu-budget 57
.venv\Scripts\python.exe solvers/python/main.py --numba --algorithm ig --instance instances/examples/Doc11.txt --seed 42 --cpu-budget 57
```

`--cpu-budget` y `--max-evaluations` son excluyentes. La salida normal es JSON; `--contest` produce las tres líneas del concurso. Las semillas son enteros sin signo de 64 bits.

## Entrada y entrega

El archivo contiene una cabecera `n m` y una fila por orden con los pares `máquina duración`, en orden de máquina desde cero. Se admiten BOM UTF-8, espacios, tabuladores, líneas vacías y duraciones cero; hasta 10 000 operaciones y 1 MiB, con comprobación de desbordamiento de 64 bits.

```text
2 2
0 1 1 10
0 3 1 1
```

La secuencia `2 1` tiene coste 18 y Fmed 9. Las órdenes de la salida se numeran desde uno.

Después de comparar, exporta únicamente el lenguaje y algoritmo elegidos, sustituyendo `XX` por tu número de equipo:

```powershell
python bench.py export --language cpp --algorithm ig --team XX
```

El paquete de `submission/` contiene las fuentes compartidas necesarias, el algoritmo seleccionado, `optcontestXX`, licencia e instrucciones `leeme.txt`. Lee `test.txt` desde el directorio de ejecución y devuelve **Fmed, segundos de CPU y secuencia**, en tres líneas. Sin semilla explícita genera una nueva para cada ejecución. Las modalidades Python incluyen sus requisitos exactos.

Los [ejemplos originales](https://github.com/Joseleelsuper/GestionDeEmpresas-P2/tree/4000922412642757217872d31e3c232328ff0c9f/data/examples) están fijados a esa revisión; `Doc11.txt` tiene las dimensiones del concurso.

## Hardware: solo C++/IG

La variante de `experiments/` compila para AVX2 y ejecuta búsquedas independientes con memoria y generadores propios. `--threads 0` usa todos los procesadores lógicos disponibles; `--threads 1` ejecuta IG secuencial. Los 57 s de CPU son compartidos entre todos los hilos.

```powershell
python hardware.py check
python hardware.py run
build\ig-parallel.exe --threads 0 --instance test.txt --cpu-budget 57
python hardware.py export --team XX --threads 0
```

Sustituye `XX` por el número de equipo. La exportación incluye las fuentes necesarias y el comando de compilación, sin dependencias adicionales a Windows. AVX2 requiere una CPU compatible; tanto el i7-13620H local como el Ryzen 9 9900X de las bases lo admiten.

Las nuevas pruebas comparan únicamente C++/IG: referencia original y variante AVX2 con 1, 2, 4, 8 y todos los hilos. Usan las cinco instancias de ajuste y dos semillas, siempre con 57 s de CPU total. Los 60 resultados se guardan en `results/hardware/`, con reanudación e informe HTML. La selección depende de Fmed bajo ese presupuesto; más hilos pueden consumirlo antes sin mejorar la solución. El ajuste específico del Ryzen requiere medir en ese equipo.

Para confirmar la selección de dos hilos, `instances/hardware-validation/` contiene diez instancias nuevas, generadas con `random.Random(3001)` a `random.Random(3010)`, de 75 × 20 y duraciones uniformes enteras de 1 a 99. Se comparan referencia y dos hilos con cinco semillas y 57 s de CPU total: 100 ejecuciones. El directorio de resultados es independiente de las campañas anteriores; el mismo comando permite reanudar.

```powershell
python hardware.py run --instance-dir instances/hardware-validation --instances 10 --repetitions 5 --threads 2 --results results/hardware-validation
```
