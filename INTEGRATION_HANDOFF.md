# Integration Handoff — Panel de Cúbico

Este documento es para el desarrollador externo que va a rediseñar el
**frontend** del panel de operaciones de Cúbico. Cubre todo lo necesario
para construir una interfaz nueva contra la API existente, sin tener que
tocar el backend (Python/FastAPI).

El backend NO se toca en este trabajo — el nuevo frontend solo consume
los endpoints descritos abajo.

---

## 1. Tecnologías utilizadas

**Backend (no se toca, solo se consume):**
- Python 3 + FastAPI (`fastapi==0.141.1`, `starlette==1.4.1`, `uvicorn==0.52.1`)
- SQLAlchemy 2.0 (`sqlalchemy==2.0.51`) sobre dos bases de datos distintas (ver sección 2)
- PostgreSQL (`psycopg2-binary`) para datos de clientes/paquetes/facturas
- SQLite local (`sesiones.db`) para el estado de las conversaciones (lo que consume el panel)
- Anthropic Claude API (`anthropic==0.121.0`) — motor conversacional del bot ("Bruno")
- OpenAI API (`openai==3.3.0`) — transcripción de notas de voz
- WhatsApp Cloud API (Meta) — canal de mensajería con el cliente
- APScheduler (`apscheduler==3.11.3`) — tareas programadas (ping diario, revisión de pagos)
- PM2 — gestor de procesos en producción (servidor Hetzner)

**Frontend actual (lo que se va a rediseñar):**
- Un único archivo HTML (`app/static/panel.html`) con CSS y JavaScript "vanilla" inline —
  sin framework (no React/Vue), sin build step, sin dependencias npm.
- Autenticación vía HTTP Basic Auth, guardada en memoria del navegador (variable JS `creds`),
  no hay cookies de sesión ni JWT.
- Polling simple cada 30 segundos para refrescar la lista de conversaciones (no hay WebSockets).

---

## 2. Estructura principal del proyecto

```
app/
├── main.py                  # Arranque de FastAPI, monta /static y registra los routers
├── core/
│   └── config.py            # Settings (variables de entorno vía pydantic-settings)
├── api/
│   ├── whatsapp.py          # Webhook de Meta + lógica de envío de mensajes/plantillas
│   ├── panel.py             # *** Todos los endpoints /panel/* que consume el frontend ***
│   └── notificaciones.py    # Endpoint interno para notificaciones de carga (no lo usa el panel)
├── db/
│   ├── database.py          # Engine de PostgreSQL (clientes, paquetes, facturas — solo lectura)
│   └── session_store.py     # Engine de SQLite local (sesiones.db) — modelo Sesion y su historial
├── ai/
│   └── orchestrator.py      # Lógica de Claude ("Bruno"): genera las respuestas automáticas
├── tools/
│   ├── clientes.py          # Verificación de cliente por código CBC / correo
│   ├── paquetes.py          # Consulta de paquetes por código de cliente
│   ├── facturas.py          # Consulta de facturas/saldos por código de cliente
│   └── ...                  # otras integraciones (cotizador, comprobantes, transcripción)
├── scheduler.py              # Tareas programadas (APScheduler)
└── static/
    ├── panel.html            # *** El archivo que se va a rediseñar ***
    └── logo.png               # Logo de Cúbico usado en el panel
```

**Detalle importante — dos bases de datos separadas:**

- `sesiones.db` (SQLite, en la raíz del proyecto): guarda el estado de cada conversación
  (`app/db/session_store.py`, clase `Sesion`). **Esta es la fuente de todos los datos que
  devuelve `/panel/*`.**
- PostgreSQL (`DATABASE_URL`): datos maestros de clientes, paquetes y facturas
  (`app/tools/clientes.py`, `app/tools/paquetes.py`, `app/tools/facturas.py`), usados
  internamente por el backend para resolver cosas como el nombre completo del cliente
  a partir de su código CBC. El panel no consulta esta base directamente — recibe
  los datos ya combinados en la respuesta de `/panel/conversaciones`.

---

## 3. Autenticación

Todos los endpoints bajo `/panel/*` requieren **HTTP Basic Auth**:

```
Authorization: Basic <base64(usuario:contraseña)>
```

- Los usuarios/contraseñas válidos se cargan desde la variable de entorno
  `PANEL_USUARIOS_JSON` (un JSON `{"usuario": "contraseña", ...}`), no hay una tabla de
  usuarios en base de datos.
- Si las credenciales son inválidas, cualquier endpoint responde:
  - **401 Unauthorized**, header `WWW-Authenticate: Basic`, body `{"detail": "Credenciales inválidas"}`
- No hay tokens, sesiones de servidor ni refresh — cada request debe mandar el header
  `Authorization` completo. El frontend actual simplemente guarda el string base64 en una
  variable JS (`creds`) tras el login y lo reenvía en cada fetch.

---

## 4. Endpoints del panel

Base URL en producción: `https://bot.cubico.com.pa`

### `GET /panel/conversaciones`

Lista general de conversaciones (vista tipo "cámaras de seguridad").

- **Headers:** `Authorization: Basic <...>`
- **Body:** ninguno
- **Respuesta 200** — array de objetos (ver estructura completa en sección 5):

```json
[
  {
    "telefono": "50761234567",
    "nombre": "Juan Pérez",
    "codigo_cliente_verificado": "CBC0018",
    "estado": "verificado",
    "necesita_atencion_humana": false,
    "aviso_retiro_pendiente": false,
    "solicitud_domicilio_pendiente": false,
    "motivo_escalamiento": null,
    "ultimo_mensaje": {
      "rol": "assistant",
      "contenido": "Tu paquete ya está disponible para retiro."
    },
    "tiene_no_leidos": true
  }
]
```

---

### `GET /panel/conversacion/{telefono}`

Historial completo de una conversación específica.

- **Headers:** `Authorization: Basic <...>`
- **Path param:** `telefono` — número tal como lo usa WhatsApp (ej. `50761234567`, sin `+` ni espacios)
- **Body:** ninguno
- **Respuesta 200** (ver estructura completa en sección 6):

```json
{
  "telefono": "50761234567",
  "historial": [
    {"role": "user", "content": "Hola, quiero saber si llegó mi paquete"},
    {"role": "assistant", "content": "Claro, dame un momento para revisarlo..."}
  ]
}
```

- **Respuesta 404** si el teléfono no tiene ninguna conversación registrada:
  `{"detail": "No existe ninguna conversación con ese teléfono"}`

---

### `POST /panel/atender/{telefono}`

Marca una conversación como atendida (baja la alerta de "necesita atención humana").

- **Headers:** `Authorization: Basic <...>`
- **Body:** ninguno
- **Respuesta 200:** `{"status": "atendido"}`

---

### `POST /panel/retiro/{telefono}`

Marca como resuelto el aviso de retiro de paquetes en el local.

- **Headers:** `Authorization: Basic <...>`
- **Body:** ninguno
- **Respuesta 200:** `{"status": "retiro_resuelto"}`

---

### `POST /panel/domicilio/{telefono}`

Marca como resuelta la solicitud de entrega a domicilio.

- **Headers:** `Authorization: Basic <...>`
- **Body:** ninguno
- **Respuesta 200:** `{"status": "domicilio_resuelto"}`

---

### `POST /panel/responder/{telefono}`

Envía una respuesta al cliente **pasando por Bruno** (Claude redacta el mensaje final con
su tono habitual a partir de lo que escribe el trabajador). Cierra automáticamente el
escalamiento (`necesita_atencion_humana=False`).

- **Headers:** `Authorization: Basic <...>`, `Content-Type: application/json`
- **Body:**

```json
{"mensaje": "Dile que su paquete llega mañana y que no necesita pagar nada extra"}
```

- **Respuesta 200:** `{"status": "enviado"}`
- **Respuesta 400** si `mensaje` viene vacío: `{"detail": "Mensaje vacío"}`
- **Respuesta 404** si el teléfono no tiene conversación: `{"detail": "No existe ninguna conversación con ese teléfono"}`

---

### `POST /panel/enviar-directo/{telefono}`

Envía el mensaje **tal cual lo escribió el trabajador**, sin pasar por Claude. Pensado para
usarse junto con `/panel/control/{telefono}` cuando un humano tomó control total de la
conversación.

- **Headers:** `Authorization: Basic <...>`, `Content-Type: application/json`
- **Body:**

```json
{"mensaje": "Hola, te escribe Luis de Cúbico, ¿en qué te ayudo?"}
```

- **Respuesta 200:** `{"status": "enviado"}`
- **Respuesta 400** si `mensaje` viene vacío: `{"detail": "Mensaje vacío"}`

---

### `POST /panel/control/{telefono}`

Activa o desactiva el "modo control humano directo" de una conversación. Mientras está
activo, el bot (Bruno) **no genera ni envía ninguna respuesta automática** a los mensajes
entrantes de ese cliente — solo se siguen guardando en el historial para que se vean en
el panel.

- **Headers:** `Authorization: Basic <...>`, `Content-Type: application/json`
- **Body:**

```json
{"accion": "tomar"}
```

  Cualquier valor distinto de `"tomar"` (ej. `"soltar"`) desactiva el modo control.

- **Respuesta 200:**

```json
{"status": "ok", "control": true}
```

  `control` es `true` si el modo quedó activado, `false` si quedó desactivado.

---

### `POST /panel/marcar-leido/{telefono}`

Marca la conversación como leída por el trabajador (afecta el campo `tiene_no_leidos`
de `/panel/conversaciones`). Se llama normalmente al abrir el chat.

- **Headers:** `Authorization: Basic <...>`
- **Body:** ninguno
- **Respuesta 200:** `{"status": "leido"}`

---

## 5. Estructura completa del objeto de `/panel/conversaciones`

Cada elemento del array devuelto:

| Campo | Tipo | Descripción |
|---|---|---|
| `telefono` | string | Número de WhatsApp del cliente (sin `+`, ej. `"50761234567"`) |
| `nombre` | string \| null | Nombre completo del cliente, solo si está verificado (viene de PostgreSQL, cruzado por `codigo_cliente_verificado`) |
| `codigo_cliente_verificado` | string \| null | Código CBC del cliente si ya se verificó (ej. `"CBC0018"`) |
| `estado` | string | Estado interno de la conversación. Valores observados: `"esperando_codigo"` (default), `"verificado"` |
| `necesita_atencion_humana` | boolean | `true` si hay un caso escalado sin resolver |
| `aviso_retiro_pendiente` | boolean | `true` si el cliente avisó que va a retirar sus paquetes y no se ha cerrado |
| `solicitud_domicilio_pendiente` | boolean | `true` si el cliente pidió entrega a domicilio y no se ha cerrado |
| `motivo_escalamiento` | string \| null | Texto libre con el motivo del escalamiento (queja detectada, `escalar_a_humano`, etc.) |
| `ultimo_mensaje` | object \| null | `{"rol": "user"\|"assistant", "contenido": "..."}` — el último mensaje del historial, o `null` si no hay historial |
| `tiene_no_leidos` | boolean | `true` si `actualizado_en` de la sesión es más reciente que la última vez que el trabajador marcó la conversación como leída (o si nunca se ha marcado) |

No incluye: `atencion_humana_directa` (el modo control activo) — actualmente **no** viene
en esta respuesta, solo se puede activar/desactivar vía `/panel/control/{telefono}`. Si el
nuevo frontend necesita mostrar visualmente si el modo control está activo, hay que
pedir que se agregue ese campo al backend (no está expuesto hoy).

---

## 6. Estructura del historial de `/panel/conversacion/{telefono}`

```json
{
  "telefono": "50761234567",
  "historial": [
    {"role": "user", "content": "texto del mensaje"},
    {"role": "assistant", "content": "texto del mensaje"}
  ]
}
```

- Cada mensaje tiene únicamente dos campos: `role` y `content`. **No hay timestamp por
  mensaje** — solo existe `actualizado_en` a nivel de toda la sesión (no se expone en este
  endpoint).
- Valores posibles de `role`:
  - `"user"` — mensaje del cliente
  - `"assistant"` — mensaje enviado por Bruno (ya sea generado por Claude o redactado a
    partir de lo que escribió un trabajador vía `/panel/responder`)
  - `"humano"` — mensaje enviado tal cual por un trabajador vía `/panel/enviar-directo`
    (sin pasar por Claude)
- `content` es siempre un string simple en la práctica.
- El historial se recorta automáticamente a los últimos 8 mensajes cada vez que se agrega
  uno nuevo (para no encarecer las llamadas a Claude) — **no es un log completo e
  indefinido de la conversación**, solo una ventana reciente.

---

## 7. Variables de entorno necesarias

(Solo nombres — los valores reales viven en `.env`, nunca se commitean.)

- `DATABASE_URL`
- `ANTHROPIC_API_KEY`
- `WHATSAPP_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_VERIFY_TOKEN`
- `OPENAI_API_KEY`
- `PANEL_USUARIOS_JSON`
- `CUBICO_NOTIFY_KEY`

Para un rediseño de solo frontend, la única relevante en la práctica es
`PANEL_USUARIOS_JSON` (define qué usuarios/contraseñas acepta el Basic Auth de
`/panel/*`). El resto las necesita el backend para funcionar, pero no son configurables
desde el frontend.

---

## 8. Notas importantes

- El archivo HTML del panel actual vive en `app/static/panel.html` — es el que se va
  a reemplazar/rediseñar.
- El panel se sirve en **https://bot.cubico.com.pa/admin** (ruta definida en
  `app/main.py`, simplemente devuelve ese archivo HTML).
- El logo de Cúbico está publicado en **https://bot.cubico.com.pa/static/logo.png**.
- **Todos** los endpoints bajo `/panel/*` requieren Basic Auth — no hay ninguno público.
- Zona horaria del proyecto: `America/Panama` (el servidor corre en UTC; cualquier
  fecha/hora que se muestre en el frontend debe convertirse a Panamá).
- No hay WebSockets ni Server-Sent Events — cualquier "tiempo real" en el panel actual
  se logra con polling (cada 30s). Si el nuevo frontend necesita algo más instantáneo,
  requeriría cambios en el backend que no están incluidos en este handoff.
- Despliegue: el backend se actualiza con `git push` a `main` → SSH al servidor →
  `git pull` → `pm2 restart cubico-bot`. El nuevo frontend, al ser un archivo estático
  servido por el mismo backend, sigue el mismo flujo de despliegue.
