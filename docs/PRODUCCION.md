# Poner el negocio a andar, paso a paso

Esta guía asume que no sabés nada de esto y que **no vas a correr ningún
comando**. Todo lo que hay que hacer se hace desde el navegador: copiar dos
valores, pegarlos en dos sitios web, y apretar un botón.

Son cuatro plataformas. **Ninguna te cobra por adelantado** y sólo dos te van a
cobrar algo alguna vez (está explicado abajo, en *Qué se paga de verdad*).

---

## Primero: qué es cada cosa

Los nombres raros que aparecen en GitHub y en Vercel son casilleros donde se
guarda un dato secreto. No hay que inventar nada: cada casillero tiene un nombre
fijo y un valor que sale de algún lado.

| Cómo se llama | Qué es, en criollo | De dónde sale el valor |
|---|---|---|
| `MV_LICENSE_PRIVATE_KEY` | El **sello** con el que se firman las licencias. Quien lo tenga puede regalar el producto. | Lo generás vos en `tusitio.com/claves` |
| `MV_LICENSE_PUBLIC_KEY` | El **lector del sello**. Va adentro de cada instalador para reconocer las licencias legítimas. No es secreto. | Sale junto con el anterior, del mismo botón |
| `MP_ACCESS_TOKEN` | La llave de tu cuenta de MercadoPago para cobrar. | Panel de MercadoPago |
| `PANEL_CLAVE` | La contraseña para entrar a tu panel de ventas. | **La inventás vos.** Una frase larga que no uses en otro lado |
| `RESEND_API_KEY` | Permiso para mandar el correo con la licencia. | Panel de Resend |
| `CORREO_DESDE` | Desde qué dirección sale ese correo. | Lo escribís vos |
| `SITIO` | La dirección de tu página. | La que te dé Vercel, o tu dominio |

Dos aclaraciones sobre cosas que confunden:

* **«Release»** en GitHub no es una clave ni hay que llenarla: es simplemente la
  página donde queda publicado el archivo `.exe` para descargar. Se crea sola
  cuando termina de compilar.
* **Los secretos de GitHub y las variables de Vercel son lo mismo con otro
  nombre**: un casillero con nombre y valor. GitHub les dice *secrets*, Vercel
  les dice *environment variables*.

---

## Paso 1 · Generar tu sello de licencias

1. Abrí **`https://tu-sitio.vercel.app/claves`**.
   (Si todavía no publicaste el sitio, hacé primero el Paso 3 y volvé acá.)
2. Apretá **Generar mis dos claves**.
3. Apretá **Descargar respaldo** y guardá ese archivo en algún lugar tuyo que no
   sea el repositorio. Un gestor de contraseñas está bien; el escritorio de la
   computadora, no.

Las claves se generan dentro de tu navegador y no viajan a ningún servidor, ni
al nuestro. Dejá esa pestaña abierta: los dos valores se usan en los pasos que
siguen.

> **Esto se hace una sola vez.** Cada instalador que se compila lleva grabada la
> clave pública. Si más adelante generás un par nuevo, las licencias que ya
> vendiste dejan de funcionar en los instaladores nuevos.

---

## Paso 2 · GitHub · guardar el sello

**Dónde:** `https://github.com/vieraschiavi/MV-Machine-Learning/settings/secrets/actions`
→ botón **New repository secret**.

Cargá dos, uno por vez. En *Name* va el nombre exacto, en *Secret* el valor:

| Name | Secret |
|---|---|
| `MV_LICENSE_PRIVATE_KEY` | la clave **privada** del Paso 1 |
| `MV_LICENSE_PUBLIC_KEY` | la clave **pública** del Paso 1 |

Después andá a **Actions → Escritorio Windows → Run workflow**. En unos 15
minutos quedan publicados los dos instaladores:

* **Demo**, público, en `Releases`. Es el que baja la gente desde tu página.
* **Owner**, en un release marcado como **borrador (draft)**: sólo lo ves vos.
  Ese instalador trae tu licencia de dueño adentro, así que abre el programa
  completo sin pedirte nada.

Si compilás sin haber cargado los secretos, el instalador igual sale, pero con
un sello descartable: sirve para probar, no para vender.

---

## Paso 3 · Vercel · la página y el cobro

**Dónde:** tu proyecto en Vercel → **Settings → Environment Variables**.

| Name | Value | Si falta |
|---|---|---|
| `MP_ACCESS_TOKEN` | tu credencial de MercadoPago (`APP_USR-…`) | El botón de compra no cobra |
| `MV_LICENSE_PRIVATE_KEY` | **la misma** privada del Paso 1 | El pago entra pero no se emite la licencia |
| `PANEL_CLAVE` | una frase larga que inventás vos | El panel de ventas queda cerrado |
| `RESEND_API_KEY` | tu clave de Resend (`re_…`) | La licencia se emite pero no se envía sola |
| `CORREO_DESDE` | `MV Software <ventas@tudominio.com>` | Sale desde una dirección de prueba |
| `SITIO` | `https://tu-sitio.vercel.app` | Se deduce sola, pero conviene fijarla |

Marcá todas para **Production**. Después de cargarlas hay que apretar
**Redeploy** una vez para que el sitio las tome.

### De dónde sale cada valor

* **MercadoPago** → `https://www.mercadopago.com.uy/developers/panel/app` → tu
  aplicación → *Credenciales*. Empezá con las **de prueba** y recién cambiá a
  las de producción cuando hayas hecho la compra de ensayo del final.
* **Resend** → `https://resend.com/api-keys` → *Create API Key* (alcanza con
  permiso *Sending access*). Para que el correo salga desde tu dominio y no
  caiga en spam, verificá el dominio en `https://resend.com/domains`.

---

## Paso 4 · MercadoPago · avisar cuándo se pagó

**Dónde:** panel de tu aplicación → *Webhooks* → *Configurar notificaciones*.

* URL: `https://tu-sitio.vercel.app/api/pago-confirmado`
* Evento: **Pagos** (`payment`).

Eso es lo que dispara la licencia. El servidor no le cree al aviso: toma el
número de operación y le pregunta a MercadoPago si ese pago está realmente
aprobado. Sin esta verificación, cualquiera podría mandar un mensaje falso
diciendo «pagué» y llevarse una licencia.

---

## Qué se paga de verdad

Nada te cobra por instalar ni por probar. Esto es lo que hay:

| Plataforma | Qué cuesta | ¿Obligatorio? |
|---|---|---|
| **MercadoPago** | Una comisión por venta, que se descuenta sola de cada cobro. En el panel vas a ver el número exacto: la diferencia entre *Cobrado (bruto)* y *Te queda (neto)*. | **Sí**, pero no pagás nada por adelantado. Es el costo de cobrar con tarjeta. |
| **GitHub** | Gratis. Con el repositorio público, compilar el instalador no consume cuota. | No |
| **Vercel** | El plan gratuito alcanza técnicamente de sobra. **Pero sus términos reservan el plan gratuito para proyectos personales sin fines comerciales**: un sitio que cobra con MercadoPago no encaja ahí, y pueden suspendértelo. El plan Pro es US$ 20 por mes. | **Sí, en cuanto empieces a vender.** Es el único costo fijo real. |
| **Resend** | Gratis hasta 3.000 correos por mes (100 por día). Con eso te alcanza para cientos de ventas mensuales. | No |
| **Dominio** | Entre US$ 12 y US$ 60 al año según la terminación (`.com` barato, `.uy` caro). | No: podés vender desde la dirección `tu-sitio.vercel.app`. Pero da mucha más confianza tener dominio propio, y es lo que te habilita mandar correos desde tu dirección. |

**El resumen honesto:** para arrancar y probar todo, US$ 0. Para vender en
serio y quedar prolijo: el dominio (una vez al año) y Vercel Pro (US$ 20 al
mes). La comisión de MercadoPago no es un gasto que pagás: es una parte de cada
venta que no te llega.

---

## Tu panel de ventas

**Dónde:** `https://tu-sitio.vercel.app/panel`. Entrás con la `PANEL_CLAVE`
que inventaste.

Muestra, en vivo:

* **Clientes** distintos y cuántas compras aprobadas hubo.
* **Cobrado (bruto)** contra **Te queda (neto)**, con la comisión de
  MercadoPago separada. El neto es plata real depositada, no precio de lista.
* Pagos **pendientes** y **rechazados**, que son los que te avisan si algo del
  cobro está fallando.
* **Descargas** de cada instalador, contadas por GitHub.
* Apertura **por plan** y **mes a mes**.

No hay base de datos ni servicio de analítica atrás: el panel le pregunta en el
momento a MercadoPago y a GitHub. Por eso no cuesta nada y por eso, si algún día
cambiás de herramienta, el historial no se pierde — nunca estuvo acá.

### Emitir una licencia a mano

Abajo del panel hay un formulario para dos casos:

* **Tu licencia de dueño**: elegís *Dueño*, apretás *Emitir*, y te da un código
  sin vencimiento con todo habilitado. Sirve para validar el programa completo
  sin depender del instalador owner.
* **Reponerle la licencia a un cliente**: elegís *Cliente*, el plan que compró y
  su correo. Se emite y se le manda. Úsalo cuando alguien pagó y el correo se
  perdió o cayó en spam.

---

## Probar que los pagos funcionan, antes de vender

1. En Vercel, poné en `MP_ACCESS_TOKEN` el token **de prueba** y hacé *Redeploy*.
2. Entrá a tu sitio, elegí un plan y pagá con una
   [tarjeta de prueba](https://www.mercadopago.com.uy/developers/es/docs/checkout-pro/additional-content/test-cards):
   Mastercard `5031 7557 3453 0604`, cualquier vencimiento futuro, código `123`,
   documento `12345678`, nombre `APRO` (ese nombre es el que fuerza la
   aprobación).
3. Fijate que llegue el correo con la licencia. Si no configuraste Resend, la
   licencia queda igual en los registros de Vercel (*Logs*): buscá la línea que
   dice `licencia`.
4. Abrí el programa y pegá ese código. Tiene que pasar a **Profesional** al
   instante.
5. Entrá al panel: la venta tiene que aparecer ahí.

Recién cuando eso funcione, cambiá al token de producción y hacé *Redeploy*.

---

## Qué está verificado y qué no

**Verificado, ejecutándolo en cada integración** (`backend/tests/`):

* `test_circuito_comercial.py` — el cliente instala y queda en prueba con sus
  topes, se le vence la prueba y el programa deja de trabajar, paga, **el
  servidor web emite la licencia y el programa la acepta** (sin topes, sin marca
  de agua, con SQL e IA habilitados), y una licencia firmada con otra clave se
  rechaza. También que la licencia de dueño no vence nunca y habilita todo.
* `test_claves_navegador.py` — el generador de `claves.html` produce
  exactamente el mismo par que deriva la biblioteca criptográfica del programa.
  Si esas dos implementaciones se separaran, el instalador quedaría con un
  lector que no reconoce su propio sello.
* `test_panel.py` — los totales del panel contra una lista de pagos armada a
  mano con los casos molestos: pendientes, rechazados, devoluciones parciales y
  el mismo cliente comprando dos veces.
* El workflow de Windows compila el `.exe` y **lo corre de verdad**: pide el
  token, sube un archivo, entrena un modelo y calcula SHAP. Si el binario no
  arranca, no se publica nada.

**Lo que no se puede verificar desde acá:** que MercadoPago le cobre de verdad a
una tarjeta real. Eso se comprueba con la compra de ensayo de la sección
anterior, y hay que hacerla una vez.

---

## Recordatorios

* **Nunca** pegues `MP_ACCESS_TOKEN`, `MV_LICENSE_PRIVATE_KEY` ni `PANEL_CLAVE`
  en el código, en un correo o en un chat. Los casilleros de GitHub y Vercel los
  guardan cifrados y no los vuelven a mostrar: ese es el único lugar donde van.
* Si sospechás que una credencial se filtró, cambiala: en MercadoPago desde el
  panel de la aplicación (es inmediato y no rompe nada), y `PANEL_CLAVE`
  editando la variable en Vercel. El par de licencias es el único que conviene
  no tocar, porque invalida lo ya vendido.
* Los precios viven en `api/crear-pago.js`, del lado del servidor. Si
  dependieran de lo que manda el navegador, cualquiera compraría el plan más
  caro por un peso.
