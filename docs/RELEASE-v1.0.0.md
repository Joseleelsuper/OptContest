# OptContest A2 — C++/IG r400

Entrega para Windows 11 x64: un hilo, destrucción de hasta 6 órdenes, temperatura `max(1, 0.01 × coste inicial)`, reinicio tras 400 ciclos sin mejora global y presupuesto de 57 segundos de CPU por ejecución.

## Descargar y ejecutar

Descarga **[optcontestA2.zip](https://github.com/Joseleelsuper/OptContest/releases/download/v1.0.0/optcontestA2.zip)** y extráelo. Coloca el archivo de evaluación `test.txt` junto al ejecutable y abre PowerShell en esa carpeta:

```powershell
.\optcontestA2.exe
```

La salida tiene exactamente tres líneas: **Fmed, segundos de CPU y secuencia de órdenes desde uno**. La ejecución normal genera una semilla nueva. No requiere Python, Java, compilador ni DLL de MinGW instalados.

El ZIP incluye el ejecutable, las fuentes C++ necesarias, `leeme.txt` y la licencia. El archivo de evaluación no está incluido.

## Resultado que justifica la selección

- Validación independiente: 10 instancias nuevas de 75 × 20, cinco repeticiones, 100 ejecuciones válidas y ningún fallo.
- Fmed medio: **3094.742667 con r400**, frente a **3096.595467 con r200**.
- Reducción media: **1.8528 puntos, aproximadamente un 0.0598 %**.
- Comparaciones por pareja: 25 victorias, 12 empates y 13 derrotas; mejora media en siete de diez instancias.
- Intervalo bootstrap del 95 % para candidato menos base: **[−3.269067, −0.456533]**. Cumple el criterio de selección previsto.

La mejora es pequeña y corresponde a este banco local. En el ajuste quedaron dos timeouts por suspensión sin repetir; no se afirma que r400 supere a todas las variantes descartadas ni que certifique el óptimo global. La entrega no se ha medido en el Ryzen 9 9900X del concurso.

## Archivos de la release

- **optcontestA2.zip**: paquete para entregar.
- **optcontest-resultados.zip**: informes HTML, JSONL originales, CSV, manifiestos y selección de las cinco campañas. Se distribuye aparte del programa.
- **SHA256SUMS.txt**: sumas SHA-256 de ambos ZIP.

La compilación de entrega añade enlace estático a las opciones del candidato validado. Se comprueban la equivalencia por evaluaciones y la ejecución normal del ZIP extraído en un entorno con solo Windows System32 en PATH.

[Instrucciones completas](https://github.com/Joseleelsuper/OptContest/blob/v1.0.0/docs/ENTREGA.md) · [Algoritmos y resultados](https://github.com/Joseleelsuper/OptContest/blob/v1.0.0/docs/RESULTADOS.md) · [Comprobación del paquete](https://github.com/Joseleelsuper/OptContest/blob/v1.0.0/docs/DELIVERY-CHECK.json)
