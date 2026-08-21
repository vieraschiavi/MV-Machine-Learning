# Puesta en producción

Todo lo que hay que configurar para vender, en orden. Son tres lugares —GitHub,
Vercel y MercadoPago— y ninguna de las claves se escribe en el código.

---

## 1 · GitHub · claves de licencia

**Dónde:** `https://github.com/vieraschiavi/MV-Machine-Learning/settings/secrets/actions`
→ *New repository secret*.

| Nombre exacto | Qué es |
|---|---|
| `MV_LICENSE_PRIVATE_KEY` | Firma las licencias. **Es la llave del negocio**: con ella se emiten licencias sin límite. |
| `MV_LICENSE_PUBLIC_KEY` | Verifica las licencias. Va dentro de cada instalador; no es secreta. |

Las dos son el mismo par: la pública sólo valida lo que firmó la privada. Se
generan con:

```bash
python -c "import sys; sys.path.insert(0,'backend'); \
from app.core.licensing import generate_keypair; \
p,u = generate_keypair(); print('PRIVADA:',p); print('PUBLICA:',u)"
```

**Por qué importa que no cambien nunca:** cada instalador lleva grabada la clave
pública. Si se cambia el par, las licencias vendidas con el par viejo dejan de
validar en los instaladores nuevos. Guardá las dos fuera de GitHub también: si
se pierden, no se pueden volver a emitir licencias compatibles con lo que ya
está instalado en las máquinas de los clientes.

Sin estos secretos el instalador igual se compila, pero el workflow genera un
par descartable y avisa: sirve para probar, no para vender.

---

## 2 · Vercel · cobro y envío de licencias

**Dónde:** `https://vercel.com/mv13/mv-automl-studio/settings/environment-variables`

| Nombre exacto | Valor | Sin esto qué pasa |
|---|---|---|
| `MP_ACCESS_TOKEN` | Credencial de MercadoPago (`APP_USR-…`) | El botón de compra abre un correo en vez de cobrar |
| `MV_LICENSE_PRIVATE_KEY` | La **misma** que en GitHub | El pago entra pero no se emite la licencia |
| `RESEND_API_KEY` | Clave de Resend (`re_…`) | La licencia se emite pero no se envía: queda en los registros de Vercel y hay que mandarla a mano |
| `CORREO_DESDE` | `MV Software <ventas@tudominio.com>` | Se usa el remitente de prueba de Resend |
| `SITIO` | `https://mv-automl-studio.vercel.app` | Se deduce del pedido; conviene fijarlo |

Marcá las cinco para **Production**, y `MP_ACCESS_TOKEN` también para *Preview*
con el token de prueba si querés ensayar sin cobrar de verdad.

### De dónde sale cada una

* **MercadoPago** → `https://www.mercadopago.com.uy/developers/panel/app` →
  tu aplicación → *Credenciales de producción* → **Access Token**.
  Empezá con las *Credenciales de prueba* y recién después cambiala.
* **Resend** → `https://resend.com/api-keys` → *Create API Key* (permiso
  *Sending access* alcanza). Para que el correo salga desde tu dominio y no
  caiga en spam, verificá el dominio en `https://resend.com/domains`.

---

## 3 · MercadoPago · aviso de pago

**Dónde:** panel de tu aplicación → *Webhooks* → *Configurar notificaciones*.

* URL: `https://mv-automl-studio.vercel.app/api/pago-confirmado`
* Evento: **Pagos** (`payment`).

Es lo que dispara la emisión de la licencia. El servidor no confía en ese
aviso: sólo toma el id y consulta el estado real del pago contra la API de
MercadoPago con tu token.

---

## Cómo probarlo antes de vender

1. Poné en Vercel el `MP_ACCESS_TOKEN` **de prueba**.
2. Entrá al sitio, elegí un plan y pagá con una
   [tarjeta de prueba](https://www.mercadopago.com.uy/developers/es/docs/checkout-pro/additional-content/test-cards)
   (Mastercard `5031 7557 3453 0604`, cualquier vencimiento futuro, código `123`,
   documento `12345678`).
3. Mirá los registros en `https://vercel.com/mv13/mv-automl-studio/logs`: tiene
   que aparecer una línea con el plan, el correo y la licencia emitida.
4. Pegá esa licencia en el programa. Debe pasar a **Profesional** al instante.

Recién cuando eso funcione, cambiá el token por el de producción.

---

## Qué está verificado y qué no

**Verificado ejecutándolo**, en `backend/tests/test_circuito_comercial.py`:
el cliente instala y queda en prueba con sus topes, se le vence la prueba y el
programa deja de trabajar, paga, **el servidor web emite la licencia y el
programa la acepta** —sin topes, sin marca de agua, con SQL e IA habilitados— y
una licencia firmada con otra clave se rechaza. Esa prueba corre en cada
integración: si alguien tocara el firmador del servidor y dejara de coincidir
con el verificador del programa, el pipeline se pone en rojo antes de que un
cliente pague y no pueda activar.

**Lo que no se puede verificar acá:** que MercadoPago le cobre de verdad a una
tarjeta real. Eso se comprueba con la compra de prueba del punto anterior.

---

## Recordatorios

* **Nunca** pongas `MP_ACCESS_TOKEN` ni `MV_LICENSE_PRIVATE_KEY` en el HTML, en
  el repositorio ni en un mensaje: cualquiera que lea la página vería el token.
  Por eso el cobro lo arma el servidor y no el navegador.
* Si sospechás que una credencial se filtró, rotala: en MercadoPago desde el
  panel de la aplicación, y el par de licencias regenerándolo (recordá que eso
  invalida las licencias vendidas con el par anterior).
* Los precios viven en `api/crear-pago.js`, del lado del servidor. Si
  dependieran de lo que manda el navegador, cualquiera compraría el plan más
  caro por un peso.
