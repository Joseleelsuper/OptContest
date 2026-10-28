# Entrega del equipo A2

Descarga **optcontestA2.zip** de la [release v1.0.0](https://github.com/Joseleelsuper/OptContest/releases/tag/v1.0.0).

1. Extrae el ZIP en una carpeta.
2. Coloca el archivo de evaluación, llamado exactamente `test.txt`, en esa carpeta.
3. Abre PowerShell en esa carpeta y ejecuta:

```powershell
.\optcontestA2.exe
```

El ejecutable es para Windows 11 x64. No necesita Python, Java, GCC ni DLL de MinGW instalados. No utiliza GPU ni instrucciones AVX2 específicas.

La salida consta de tres líneas, en este orden:

1. **Fmed**: suma de finalizaciones en la última máquina dividida entre el número de órdenes.
2. **CPU**: segundos de CPU del proceso, incluidos arranque e inicialización.
3. **Secuencia**: todas las órdenes, numeradas desde uno, separadas por espacios.

El presupuesto interno es de 57 segundos de CPU. El tiempo de reloj puede ser mayor si Windows reparte el procesador con otras tareas. El programa usa un hilo y una semilla nueva en cada ejecución normal.

## Archivos del ZIP

- `optcontestA2.exe`: ejecutable listo para evaluar.
- `optcontestA2.cpp`, `core.hpp`, `ig.hpp`: fuentes de la entrega seleccionada.
- `leeme.txt`: instrucciones breves.
- `LICENSE`: licencia del proyecto.

El archivo `test.txt` lo proporciona quien realiza la evaluación; no está incluido en el ZIP. El archivo **optcontest-resultados.zip** de la release contiene evidencia experimental y se distribuye por separado.

## Compilar desde las fuentes

Con GCC/MinGW compatible con C++20, desde la carpeta del ZIP:

```powershell
g++ -std=c++20 -O3 -DNDEBUG -static-libgcc -static-libstdc++ -static optcontestA2.cpp -o optcontestA2.exe
```

Los parámetros se fijan en `optcontestA2.cpp` mediante `ig_search<6,100,400>`. El segundo valor se divide entre 10 000: la temperatura es `max(1, 0.01 × coste inicial)`. La variante original de laboratorio sigue usando reinicio a 200 ciclos.

Para una comprobación rápida y reproducible, el ejecutable admite un presupuesto por evaluaciones:

```powershell
.\optcontestA2.exe --seed 42 --max-evaluations 2000000
```

Para el concurso, usa la ejecución normal sin argumentos. No combines los límites de CPU y evaluaciones.
