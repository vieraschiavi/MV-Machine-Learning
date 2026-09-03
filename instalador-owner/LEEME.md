# Instalador OWNER — la versión completa, para probarla vos

La compilación **Owner** trae la licencia adentro y la clave que la valida:
arranca con todo abierto —conectores SQL, proveedores de IA, variables de texto,
informe sin marca de agua, scoring, panel de diagnóstico— sin activar nada, sin
vencimiento y **sin pedirte ninguna clave**. Es la misma que recibe un cliente
que paga la versión completa, con el agregado del panel interno.

## Camino 1 — bajarlo del release (el más corto)

Cada compilación publica el instalador owner en su propio release, con link
fijo:

> `https://github.com/vieraschiavi/MV-Machine-Learning/releases/tag/owner-<número>`

El número es el de la ejecución del workflow. Si no lo tenés a mano, entrá a
**Releases** en el repo: el más nuevo está arriba de todo.

Doble clic al `.exe` y listo. **No pide licencia, ni token, ni pegar nada**: la
compilación owner lleva adentro la licencia y la clave que la valida. El
repositorio es privado, así que el release lo ven los colaboradores y nadie más.

Al lado viene `Activar-OWNER.bat`, que también trae la licencia adentro y
tampoco pregunta nada. Sirve para el otro caso: convertir a Owner una
instalación de cliente que ya tengas, sin bajar el instalador de nuevo. (De ese
archivo, por ser chico, queda además una copia en los *Artifacts* de la
ejecución.)

Para generar una compilación nueva: GitHub → **Actions** → *Escritorio Windows*
→ **Run workflow**. Tarda unos quince minutos.

### Por qué el release ya no es borrador

Lo era para que el instalador no quedara a la vista mientras el repositorio era
público. Ahora que el repositorio es privado, el archivo lo protege el
repositorio mismo. Y el borrador tenía un costo concreto: **no tiene URL
estable** —la que devuelve la API es `untagged-<hash>` y da 404 en el
navegador—, así que había que entrar a Releases y buscarlo a ojo.

### Por qué el `.exe` ya no va como artefacto de Actions

Estuvo, y salió mal: 375 MB por compilación llenaron la cuota de artefactos de
la cuenta (`Artifact storage quota has been hit`) y el paso empezó a fallar,
dando por perdido un build que ya había compilado y subido todo. Los releases no
consumen esa cuota.

## Camino 2 — pedírselo al sitio con tu licencia

`Bajar-OWNER.bat`. Sirve cuando el sitio ya está configurado y no querés entrar
a GitHub. Te pide una vez tu licencia de dueño y la guarda al lado, en
`mi-licencia.txt`; de ahí en más no pregunta nada.

Esa licencia se emite en `https://tu-sitio/panel` con tu `PANEL_CLAVE`, sección
**Emitir licencia**, nivel *Owner*, sin vencimiento. `/api/descargar` entrega la
compilación de dueño cuando la licencia es de nivel `owner`, y la del cliente
cuando es de nivel pago: la misma puerta, la misma verificación de firma.

Para que este camino funcione tienen que estar cargadas en Vercel
`MV_LICENSE_PUBLIC_KEY`, `GITHUB_TOKEN` y `PANEL_CLAVE`. Cuáles faltan lo dice
`https://tu-sitio/api/estado`, y `docs/PRODUCCION.md` las explica una por una.

## Por qué el `.exe` no está versionado acá

Pesa unos 375 MB —lleva Python, scikit-learn, LightGBM, XGBoost, CatBoost y SHAP
adentro— y **GitHub rechaza cualquier archivo de más de 100 MB**, así que no hay
forma de dejarlo en el repositorio aunque el repositorio sea privado. Vive donde
sí entra: como artefacto de la ejecución de Actions y como archivo de un
*release* en borrador.

Tampoco viaja versionada la licencia. `Activar-OWNER.bat` tiene el hueco vacío a
propósito y lo rellena el CI en la copia que publica: una licencia fija en el
repositorio dejaría de valer apenas cambien las claves, y mientras tanto sería
una llave del producto guardada en el historial, que no se puede borrar de los
clones que ya se hicieron. Hay una prueba que rechaza el commit si aparece una
(`backend/tests/test_instalador_owner.py`).

## Volver atrás

`Desactivar-OWNER.bat` borra la licencia activada en el equipo. No toca los
datasets, los modelos ni los informes.

## Si el programa arranca en Demo teniendo la compilación Owner

Era un bug, y está arreglado: el workflow dejaba la clave pública en una carpeta
que el instalador no empaquetaba, así que el programa no podía verificar ni su
propia licencia embebida y caía a Demo —y a un cliente que pagaba le rebotaba la
suya—. Si te pasa con un instalador viejo, recompilá: *Actions* → *Escritorio
Windows* → *Run workflow*.
