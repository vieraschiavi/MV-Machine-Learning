# Proyecciones: qué motor se eligió y por qué

Este documento existe porque la decisión no fue de gusto: se midió. Todo lo
que hay acá se reproduce con

```bash
python scripts/backtest_proyeccion.py                # el motor del producto
python scripts/backtest_proyeccion.py --con-timesfm  # agrega TimesFM 2.5
```

La segunda forma requiere `timesfm` y `torch` instalados **aparte**: no
viajan en el producto, y la razón está más abajo.

## La pregunta

Se evaluó incorporar [TimesFM](https://github.com/google-research/timesfm), el
modelo de fundación de series temporales de Google, al módulo de aprendizaje
automático. El programa no tenía forecasting: sabía clasificar y estimar sobre
una fila, no mirar hacia adelante en el tiempo. El hueco era real.

## La medición

Protocolo: **walk-forward por origen**. En cada corte el método ve sólo el
pasado y se lo califica con lo que vino después. Métrica **MASE**: 1,00 es
errar lo mismo que repetir el período anterior; menos de 1 es mejor que eso.

### A. Series de negocio — mensuales y cortas (el caso del cliente)

Las 7 series de `examples/cobranzas_panel.xlsx`: 36 meses, horizonte 3, 70
evaluaciones.

| Método | MASE medio | MASE mediana |
|---|---:|---:|
| **Motor del producto** (combina los 3 mejores) | **0,622** | 0,582 |
| Holt-Winters fijo | 0,647 | 0,571 |
| TimesFM 2.5 zero-shot | 0,717 | 0,694 |
| Repetir el año pasado | 0,923 | 0,858 |
| Promedio histórico | 0,971 | 0,908 |

### B. Series públicas largas

CO2 de Mauna Loa, PBI, desempleo e inflación de EE.UU., manchas solares y
caudal del Nilo. 48 evaluaciones.

| Método | MASE medio | MASE mediana |
|---|---:|---:|
| **TimesFM 2.5 zero-shot** | **0,927** | 0,712 |
| Motor del producto | 1,174 | 0,929 |
| Repetir el año pasado | 1,357 | 1,011 |
| Holt-Winters fijo | 1,413 | 0,848 |

## La decisión

**TimesFM no se incorpora al producto.** Gana con claridad en series largas y
de patrón complejo, y pierde contra el motor propio justo en el caso que el
programa vende: series mensuales de negocio con dos o tres años de historia.
A eso se suman tres costos que no se pagan con ese resultado:

1. **Licencia.** Los pesos de TimesFM 3.0 —la versión que gana los benchmarks—
   se distribuyen bajo `timesfm-non-commercial-license-v1.0`: uso comercial y
   en producción **no permitido**. Sólo los pesos hasta 2.5 son Apache-2.0, y
   son los que se midieron acá.
2. **Peso.** PyTorch pesa 0,72 GB instalado y los pesos de 2.5 ocupan 1,7 GB
   en la caché. El paquete del programa hoy pesa 1,0 GB, y el instalador ya
   necesita ~2,5 GB libres en el disco del sistema para descomprimirse.
3. **Internet.** Los pesos se bajan de Hugging Face en el primer uso. El
   programa está pensado para correr en máquinas sin salida a internet.

## Qué se hizo en su lugar

Un módulo de proyecciones que corre con lo que **ya viajaba** en el paquete
(`statsmodels`), y que antes de proyectar mide:

- siete métodos compiten en un backtest walk-forward sobre la propia serie;
- se **promedian los tres mejores** en vez de apostar al ganador — con 30
  puntos de historia el backtest interno es ruidoso y a veces corona a uno
  que ganó de casualidad: combinar da MASE 0,622 contra 0,712 de quedarse con
  el primero;
- la tabla del backtest se muestra en pantalla, así que el usuario ve cuánto
  erró cada método antes de creerle a la línea;
- si el ganador es un método trivial —repetir, promediar—, el veredicto avisa
  que la serie no tiene un patrón aprovechable en vez de dibujar una
  proyección convincente.

## Cuándo revisar esta decisión

- Si aparecen pesos de TimesFM 3.0 con licencia comercial **y** el producto
  deja de tener el problema de tamaño del instalador.
- Si el uso real muestra clientes con series largas (miles de puntos, datos
  horarios o diarios de varios años), que es donde el modelo de fundación
  ganó de manera consistente.
- Como servicio aparte —no dentro del `.exe`—, para un cliente que ya tenga
  la infraestructura y el caso lo justifique.
