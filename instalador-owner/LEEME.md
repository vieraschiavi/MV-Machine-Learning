# Instalador OWNER — la versión completa, para probarla vos

La compilación **Owner** trae la licencia adentro y la clave que la valida:
arranca con todo abierto —conectores SQL, proveedores de IA, variables de texto,
informe sin marca de agua, scoring, panel de diagnóstico— sin activar nada, sin
vencimiento y **sin pedirte ninguna clave**. Es la misma que recibe un cliente
que paga la versión completa, con el agregado del panel interno.

## Camino 1 — la copia portable (la más corta, y no toca C:)

En el release, junto al instalador, está
**`MV-AutoML-Studio-Owner-Portable.zip`**. Descomprimilo donde quieras —`D:\MV`,
un disco externo, lo que sea— y ejecutá `MV AutoML Studio.exe`. No instala nada,
no pide administrador y **no escribe en el disco del sistema**: los datasets,
los modelos y los informes quedan en la carpeta `datos` que viene adentro.

Para mudar todo a otro lado, copiá la carpeta entera: los datos van con ella.

> Esa carpeta `datos` no es decorativa: es la señal. Mientras exista al lado del
> ejecutable, el programa guarda ahí. Si la borrás, vuelve a usar el perfil del
> usuario. Y al revés: si tenés una instalación normal y querés sacarle los
> datos de C:, creá una carpeta `datos` al lado del `.exe` instalado.
>
> No se crea sola a propósito. Una instalación normal también puede escribir en
> su directorio, así que crearla al vuelo convertiría toda instalación en
> portable — y el desinstalador borra ese directorio, con los datasets adentro.

## Camino 2 — el instalador de siempre

> `https://github.com/vieraschiavi/MV-Machine-Learning/releases/tag/owner-<número>`

El número es el de la ejecución del workflow. Si no lo tenés a mano, entrá a
**Releases** en el repo: el más nuevo está arriba de todo.

Doble clic al `.exe` y listo. **No pide licencia, ni token, ni pegar nada**: la
compilación owner lleva adentro la licencia y la clave que la valida. El
repositorio es privado, así que el release lo ven los colaboradores y nadie más.

### Si falla con «error escribiendo al archivo …\app-64.7z»

No es la instalación: es el paso previo. NSIS descomprime su paquete interno en
`%TEMP%` y **recién después** lo copia al destino, así que necesita el espacio
dos veces — y la primera vez siempre en el disco del sistema, aunque elijas
instalar en otro. Hacen falta unos **2,5 GB libres en C:**.

Dos salidas, las dos en el release:

- `Instalar-en-otro-disco.bat` — te pregunta una letra de disco, mueve el
  `%TEMP%` ahí y lanza el instalador. Al terminar, limpia.
- la copia portable del camino 1, que no pasa por NSIS en absoluto.

### Antes de eso, descartá lo barato

Un archivo de 371 MB se corta al bajar más seguido de lo que parece, y el
síntoma es exactamente ese error de extracción. El release publica el SHA-256 de
cada archivo; comparalo:

```powershell
Get-FileHash .\MV-AutoML-Studio-Owner-Setup.exe -Algorithm SHA256 |
  Select-Object -ExpandProperty Hash
```

Si no coincide, bajalo de nuevo y listo.

## Convertir una instalación que ya tenés

`Activar-OWNER.bat`, también en el release, trae la licencia adentro y no
pregunta nada. Sirve cuando ya tenés instalada la versión de cliente y la querés
pasar a Owner sin bajar el instalador de nuevo.

Cuidado con cuál usás: **el que está en este directorio del repositorio viaja
vacío a propósito** y te va a decir «este activador vino sin licencia adentro».
El que sirve es el del release, que pesa unos 300 bytes más — esa diferencia es
la licencia. La copia versionada es la plantilla que el CI rellena.

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

## Camino 3 — pedírselo al sitio con tu licencia

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
sí entra: como archivo de un *release*. Lo mismo la copia portable, que pesa
parecido.

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
