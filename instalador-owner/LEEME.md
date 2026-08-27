# Instalador OWNER — la versión completa, para probarla vos

La compilación **Owner** trae la licencia de dueño adentro: arranca con todas
las funciones abiertas —conectores SQL, proveedores de IA, variables de texto,
informe sin marca de agua, scoring, panel de diagnóstico— sin activar nada y
sin vencimiento. Es la misma que recibe un cliente que paga la versión completa,
con el agregado del panel interno.

## Por qué el `.exe` no está en esta carpeta

Pesa unos 375 MB: lleva adentro Python, scikit-learn, LightGBM, XGBoost,
CatBoost y SHAP. **GitHub rechaza cualquier archivo de más de 100 MB en el
repositorio**, así que no hay forma de dejarlo acá aunque quisiéramos. Vive
donde sí entra: como archivo de un *release* en borrador, que no es público.

Lo que sí está acá son las dos formas de conseguirlo sin entrar a GitHub.

## Camino 1 — bajarlo con tu licencia (recomendado)

`Bajar-OWNER.bat`. Doble clic. La primera vez te pide tu licencia de dueño y la
guarda al lado, en `mi-licencia.txt`; las veces siguientes no pregunta nada.

De dónde sale esa licencia: entrás a `https://tu-sitio/panel` con tu
`PANEL_CLAVE`, sección **Emitir licencia**, nivel *Owner*, sin vencimiento. Se
emite una vez y sirve para siempre.

El sitio verifica la firma y responde con un enlace temporal de GitHub. No hace
falta token, ni cuenta, ni entrar a la interfaz de GitHub: la misma puerta que
usa un cliente que pagó, con la diferencia de que a una licencia de nivel
`owner` le entrega la compilación de dueño.

## Camino 2 — convertir una instalación que ya tenés

`Activar-OWNER.bat`. Si ya instalaste la versión de cliente y no querés bajar
375 MB otra vez, este script escribe tu licencia en la carpeta de datos del
programa instalado y al reabrirlo arranca en nivel Owner. Busca solo dónde está
instalado; no hay que copiarlo a ninguna parte.

Es reversible: `Desactivar-OWNER.bat` borra la licencia y el programa vuelve a
como estaba.

## Qué necesita cada camino

| | Bajar-OWNER | Activar-OWNER |
|---|---|---|
| Licencia owner emitida en `/panel` | sí | sí |
| El sitio desplegado y con sus variables cargadas | sí | no |
| El programa ya instalado | no | sí |
| Cuenta de GitHub, token o release a mano | no | no |

## Si el sitio todavía no está configurado

`Bajar-OWNER.bat` te lo va a decir con todas las letras: sin
`MV_LICENSE_PUBLIC_KEY` y `GITHUB_TOKEN` cargadas en Vercel, la descarga no
tiene de dónde sacar el archivo. La lista completa de lo que falta la da
`https://tu-sitio/api/estado` (o `docs/PRODUCCION.md`, que la explica una por
una). Mientras tanto queda el camino 2, que no depende del sitio.

## Cómo se genera el instalador

GitHub → pestaña **Actions** → *Escritorio Windows* → **Run workflow**. En unos
quince minutos quedan publicados los dos instaladores, los dos como release en
borrador: el del cliente —que entrega `/api/descargar` a quien compró— y el
Owner. El workflow no publica nada abierto a propósito: un instalador público es
el producto regalado a cualquiera que pase.
