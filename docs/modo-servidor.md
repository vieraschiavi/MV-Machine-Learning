# Modo servidor: usar el programa sin instalarlo, con los datos del cliente en el servidor del cliente

## El problema que resuelve

Una contratista te asigna a un proyecto de otro cliente. Los datos de ese
cliente **no pueden salir de su infraestructura**: ni a tu laptop personal, ni
a la laptop corporativa que te dieron. Y esa laptop, además, tiene bloqueada la
ejecución de `.exe` y `.bat` por política de seguridad, así que instalar el
programa no es una opción.

El programa ya era casi la respuesta: el backend **sirve la interfaz**, así que
el `.exe` de escritorio no es más que un navegador con el servidor adentro.
Separarlos alcanza.

```
   Servidor / VM del cliente                    Tu laptop de trabajo
  ┌──────────────────────────────┐            ┌──────────────────────┐
  │  MV AutoML Studio            │            │                      │
  │  ├─ datasets    (parquet)    │  ◀──────▶  │   Navegador          │
  │  ├─ modelos     (joblib)     │   HTTP     │   (lo único que hay  │
  │  └─ informes    (html/docx)  │            │    que abrir)        │
  │                              │            │                      │
  │  Los datos NUNCA salen de acá│            │  Acá sólo pasan      │
  └──────────────────────────────┘            │  pedidos y píxeles   │
                                              └──────────────────────┘
```

Nada que instalar del lado del usuario. Ningún dato del cliente en tu disco.

## Lo que hay que levantar, del lado del cliente

En el servidor o la VM que te asignaron:

```bash
git clone <el repositorio>      # o copiá la carpeta
cd MV-Machine-Learning
cp .env.ejemplo .env
```

Completá **tres** valores en el `.env`:

| Variable | De dónde sale |
|---|---|
| `MV_API_TOKEN` | la generás vos: `openssl rand -base64 32` |
| `MV_LICENSE` | del panel del sitio → «Emitir licencia» → nivel **Owner**, sin vencimiento |
| `MV_LICENSE_PUBLIC_KEY` | la clave pública que valida esa licencia, del mismo panel |

Y levantás:

```bash
docker compose up -d
docker compose logs -f       # hasta ver "Application startup complete"
```

## Cómo lo abrís desde la laptop

**Recomendado — túnel SSH.** No expone nada nuevo en la red de la empresa, y
por eso suele ser lo único que seguridad aprueba sin discusión:

```bash
ssh -L 8000:127.0.0.1:8000 usuario@servidor
```

Y en el navegador: **http://localhost:8000**

Te va a pedir la clave de acceso una vez —la de `MV_API_TOKEN`—. Se guarda en
la sesión del navegador y **se olvida al cerrar la pestaña**: en una laptop
prestada o compartida, la credencial del servidor de un cliente no puede quedar
dando vueltas.

**La otra opción** es exponerlo de verdad en la red (`MV_BIND=0.0.0.0` en el
`.env`). Hacelo sólo detrás de HTTPS —un nginx o un Traefik con certificado— y
con el visto bueno del área de seguridad del cliente. Por omisión el programa
escucha únicamente en el propio servidor, justamente para que exponerlo sea una
decisión y no un descuido.

## Las decisiones de seguridad, y por qué

**Sin credencial no arranca.** En el escritorio, cuando no hay `MV_API_TOKEN`
la autenticación se apaga sola: la API escucha en `127.0.0.1` y quien la lanzó
es el dueño del equipo. Esa misma línea, en un servidor alcanzable por la red y
con los datos de un tercero adentro, es una filtración esperando a que alguien
escanee el puerto. En modo servidor el programa **se niega a arrancar** sin
credencial, y también si es demasiado corta para resistir un intento de
adivinarla.

**La licencia no toca el disco.** Va por `MV_LICENSE`, en el entorno del
proceso. Un `license.key` escrito en el servidor del cliente es una credencial
tuya abandonada ahí: sobrevive al contenedor y la lee cualquiera con acceso al
volumen. Verificado: después de subir datos y entrenar, en el volumen no hay
ningún archivo de licencia.

**El contenedor no corre como root.** Si aparece un agujero en el programa, que
no sea además un agujero en la máquina del cliente.

**Nada de claves en la imagen.** El `.dockerignore` excluye `**/*.key`,
`**/owner/` y `.env`. Una imagen es un archivo que se copia; una licencia
horneada adentro se copia con ella.

## Qué queda en el servidor, y cómo se borra

Todo vive en el volumen `/datos` (por omisión `./datos-servidor` del lado del
servidor):

```
/datos
├── catalog.db          el catálogo de datasets y modelos
├── datasets/           los datos del cliente, en parquet
├── models/             los modelos entrenados
├── exports/            los informes generados
└── uploads/            los archivos tal como se subieron
```

Es lo único que persiste: **lo que hay que respaldar durante el proyecto, y lo
que hay que borrar cuando termine.**

```bash
docker compose down          # apaga el programa, deja los datos
rm -rf ./datos-servidor      # y esto borra los datos del cliente
```

## Cuando no hay servidor ni VM

Es el caso más restrictivo, y conviene ser claro: **el programa necesita correr
en algún lado**. Entrena modelos, cruza tablas y escribe archivos; nada de eso
pasa dentro de una pestaña del navegador. Sin una máquina del lado del cliente,
las opciones reales son:

| Opción | Qué hace falta | Los datos quedan en |
|---|---|---|
| **Docker en el servidor del cliente** | lo de arriba | el cliente |
| **Sin Docker, en el servidor del cliente** | Python 3.11 y `pip install -r requirements.txt`; se levanta con `MV_MODO=servidor MV_API_TOKEN=... uvicorn app.main:app --host 0.0.0.0` desde `backend/` | el cliente |
| **Una VM que te dé el cliente** | idéntico a los dos anteriores | el cliente |
| **Tu laptop, con el portable** | nada: se descomprime y se ejecuta | **tu laptop** ← esto es lo que no podés hacer con datos de un tercero |

Si el cliente no te da ni servidor, ni VM, ni permiso para instalar nada en
ningún lado, el problema dejó de ser técnico: no hay dónde procesar los datos.
Lo que corresponde ahí es pedir formalmente un entorno de trabajo, y este
documento sirve para pedirlo, porque dice exactamente qué hace falta y qué
garantiza a cambio: **una máquina con Docker, un puerto accesible por SSH, y
los datos que nunca se mueven de ahí.**

## Verificación

Lo de este documento está ejecutado, no supuesto. Contra la imagen construida
desde este `Dockerfile`:

| Qué se probó | Resultado |
|---|---|
| Levantar sin `MV_API_TOKEN` | el contenedor **no arranca**, con el mensaje que nombra la variable |
| Pedir `/api/datasets` sin clave | `401` |
| Pedir `/api/datasets` con clave equivocada | `401` |
| Pedir `/api/datasets` con la clave | `200` |
| Nivel de licencia, sin activar nada | `owner` |
| ¿Quedó un `license.key` en el volumen? | no, cero archivos |
| Subir un dataset y entrenar | terminado, AUC holdout **0,8779** |
| ¿Dónde quedaron los archivos? | `/datos/datasets/…/part-0000.parquet` y `/datos/models/…/bundle.joblib`, en el disco del servidor |
| Salud del contenedor | `healthy` |
