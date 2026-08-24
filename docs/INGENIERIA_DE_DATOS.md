# Ingeniería de datos: qué se tomó de `autodata.py`

`autodata.py` es un script suelto que corre sobre un CSV o un Excel, escribe un
HTML y termina. Hace cuatro cosas que la plataforma no hacía, y que no son de
modelado sino de **ingeniería**: decir qué identifica una fila, si la serie de
tiempo está completa, qué se puede cruzar con qué, y cómo se lleva la tabla a un
servidor SQL.

Esas cuatro respuestas viven ahora en `backend/app/core/ingenieria.py`, se sirven
por `/api/ingenieria/*` y tienen su pestaña en la interfaz. **No se cobra
aparte**: es parte del programa, y lo único que limita al nivel Demo son los
topes de filas y datasets que ya se aplican al cargarlos.

## Qué se tomó y qué se mejoró

| Del script adjunto | Qué resuelve | Cómo quedó en la plataforma |
|---|---|---|
| Detección de clave primaria por unicidad | Sin clave no se puede deduplicar ni cruzar sin inflar filas | `claves()`. Además de la unicidad se exige que la columna **pueda** ser clave: un importe con decimales no repite en 3.000 filas y no identifica nada. Como la ingesta guarda todo lo numérico como `double`, el corte se hace midiendo si los valores son enteros, no por el tipo declarado |
| Clave compuesta por pares | La forma más común de clave real es entidad + período | `_pk_compuesta()`, con tope de pares para no volverlo cuadrático |
| Rango de fechas y huecos | Un dataset con tres meses vacíos produce tableros que parecen sanos | `tiempo()`, con **granularidad medida**: un panel con una fila por mes tiene el 97 % del calendario vacío contado en días. Reportarle «faltan 1.030 días» es cierto e inútil. Se mide si la serie es diaria, semanal o mensual y se cuentan los huecos en esa unidad |
| Frescura del dato | Una carga que dejó de correr no da error: deja de traer filas | Días desde la última fecha, más el conteo de fechas futuras (casi siempre zona horaria o parseo) |
| Sugerencia de cruces por nombre de columna | Dos tablas con `id` no se cruzan por llamarse igual | `joins()` mide el **solapamiento real de valores** y la cardinalidad (1:1, 1:N, N:1, N:N). Un cruce N:N multiplica filas en silencio: se marca en rojo con el aviso de agrupar un lado antes de unir |
| DDL de creación | Es lo que se pide cuando el análisis termina y hay que dejarlo andando | `contrato()` en cuatro motores (SQL Server, PostgreSQL, MySQL/MariaDB, DuckDB), con el tipo elegido por los valores: un año sale `BIGINT` y no `DECIMAL(18,4)`. Los nombres se transliteran, no se mutilan — `Año` queda `Ano`, no `A_o` |
| — | Comprobar mañana que la tabla sigue sana | Verificaciones SQL ejecutables: la clave no repite, no aparecen nulos donde no los había, los datos están frescos, no hay fechas futuras. Cada una devuelve cero cuando está todo bien, así se encadenan en un trabajo programado |
| — | Llevarlo a un repositorio versionado | Modelo `dbt` con los tests `not_null` / `unique` y `unique_combination_of_columns` para la clave compuesta |

## La fuente SQL ya estaba, y ahora cierra el círculo

El pedido incluía "fuente de datos SQL, no solamente CSV y Excel". La entrada ya
existía: `core/connectors.py` conecta SQL Server, PostgreSQL, MySQL, SQLite,
DuckDB y cualquier URL de SQLAlchemy, lista tablas, muestra una vista previa y
extrae a dataset con cursor del lado del servidor — **sólo lectura**. Lo que
faltaba era la vuelta: el contrato de datos toma cualquier dataset, venga de un
CSV, de un Excel o de una consulta, y devuelve el DDL y las verificaciones para
dejarlo corriendo en un servidor.

## Una consecuencia en la ingesta

Un CSV no trae tipos. Hasta ahora una fecha escrita como texto se guardaba como
texto, y el dataset quedaba sin ninguna columna temporal: sin cobertura, sin
frescura y con `VARCHAR` donde va una fecha, aunque el archivo estuviera lleno de
fechas. `storage.py` ahora las reconoce al ingerir, con dos cuidados:

* **Estricto a propósito.** Se exige que casi todos los valores tengan forma de
  fecha *y* que se puedan leer. Un código como `1.234-5` no pasa, y una columna
  con un 10 % de basura se queda como texto en vez de perder ese 10 % en
  silencio. El ETL, que mira una columna a la vez y con el nombre a la vista,
  sigue levantando esos casos.
* **El orden día/mes se decide por evidencia.** `25/12/2024` no puede ser el mes
  25. Cuando todos los valores son ambiguos manda la convención del archivo: uno
  con coma decimal viene de una configuración regional que escribe `dd/mm/aaaa`.

La decisión se toma una sola vez, con el primer bloque, y se aplica igual a
todos: si cada bloque decidiera por su cuenta, uno escribiría marca de tiempo y
el siguiente texto sobre la misma columna, y el Parquet quedaría inconsistente.
