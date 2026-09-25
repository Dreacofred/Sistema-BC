# Sistema-BC — contexto del proyecto

Sistema interno de **BC Combustibles SA** (Santa Fe, Argentina). Python +
Streamlit, con Supabase como base de datos y Claude (Anthropic) como motor de IA.
Repositorio: `Dreacofred/Sistema-BC`. El idioma de trabajo es el español
rioplatense, incluidos los comentarios del código.

Sucursales (`NOMBRES_SUCURSALES` en `lector.py`): 1 Reconquista, 2 Avellaneda,
3 Florencia, 4 Recreo.

## Reglas de trabajo

- **Nunca commitear ni pushear sin confirmación explícita de Diego**, mostrando
  antes qué archivos entran y el mensaje de commit propuesto.
- **Las credenciales van siempre en `st.secrets`** (Streamlit) o en variables de
  entorno (Render). Nunca hardcodeadas. `.streamlit/secrets.toml` está en
  `.gitignore`.
- **Regente es producción y no tiene ambiente de pruebas.** No se hace ningún
  POST/PUT contra su API sin el OK explícito de Diego. Hoy toda la integración
  es de solo lectura.

## Las tres aplicaciones

| Archivo | Qué es | Dónde corre |
|---|---|---|
| `lector.py` | App principal de gestión interna ("BC Combustibles - Gestión Pro"). Login por legajo + PIN contra la tabla `empleados`, y un menú horizontal (`streamlit-option-menu`) que delega en los módulos de `modulos/`. | Streamlit Cloud |
| `app_clientes.py` | Portal de consulta para clientes (BCRA / cheques). | Streamlit Cloud |
| `webhook.py` | Servidor Flask del bot de WhatsApp de cobranzas: recibe fotos de cheques y comprobantes y los lee con Claude. | Render |

`bot.py` no es una app aparte: es la pantalla de auditoría de comprobantes, que
`lector.py` ejecuta con `exec()` dentro de la pestaña "Laboratorio IA".

## Módulos del menú de `lector.py`

Cada módulo es `modulos/<nombre>.py` con una función `mostrar(...)` que recibe
ya inicializados los clientes que necesita (Supabase, Claude) desde `lector.py`.

| Pestaña | Módulo | Firma | Qué hace |
|---|---|---|---|
| Generador de Resumen | `modulos/resumen.py` | `mostrar(supabase, cliente_claude, user, NOMBRES_SUCURSALES, COLOR_ROJO)` | Lee remitos con Claude, revisión manual por camión y exportación a Excel. El módulo más grande. |
| Cuentas Corrientes | `modulos/cuenta_corriente.py` | `mostrar(supabase)` | **Contenedor** de consultas sobre la cuenta corriente de Regente (solo lectura). Ver abajo. |
| Verificación BCRA | `modulos/verificacion_bcra.py` | `mostrar(supabase, cliente_claude)` | Deudores y cheques rechazados del BCRA + escáner de cheques con Claude. |
| Gestión de Clientes | `modulos/clientes.py` | `mostrar(supabase, NOMBRES_SUCURSALES)` | Alta y edición de clientes, límites y permisos del portal. |
| Laboratorio IA | `bot.py` (vía `exec`) | — | Auditoría de comprobantes de cobranza. |

`modulos/proveedores.py` ("Facturas de Proveedores") **quedó fuera del menú en
septiembre 2026**, reemplazado por Cuentas Corrientes. El archivo sigue en el
repositorio pero no lo llama nadie. Era el último consumidor de Gemini: por eso
`lector.py` ya no crea el cliente de `genai` ni usa `GEMINI_API_KEY`.

## APIs externas y dónde vive cada conexión

El patrón del proyecto es: **un archivo aparte con la conexión y el parseo, y el
módulo de `modulos/` solo con la pantalla.**

| API | Archivo de conexión | Notas |
|---|---|---|
| BCRA (Central de Deudores y cheques rechazados) | `utils_bcra.py` | Se consulta a través del proxy de ScrapeOps (`SCRAPEOPS_API_KEY`). |
| Claude / Anthropic | `core/prompts_ia.py` (prompts y herramientas) | Modelo: `claude-sonnet-5`. Todos los módulos usan *tool use* forzado en vez de parsear JSON a mano. |
| Regente — cuenta corriente | `utils_regente.py` | Los 4 endpoints de solo lectura del instructivo TK-3139. |
| Semáforo de cobranza | `core/semaforo.py` | La regla del color por días de atraso. Sin dependencias: la usan la pantalla, y más adelante el portal y el bloqueo de órdenes. |
| Regente — sujetos, cuentas y catálogos | `core/regente_client.py` | Login, caché del JWT y las consultas que ya usaba el bot de cobranzas. `utils_regente.py` reusa de acá el login y el token. |
| Supabase | `core/supabase_client.py` | `get_supabase_client()` cacheado con `@st.cache_resource`. |

### Integración con Regente (el ERP)

- La URL es un **túnel ngrok** y puede cambiar. Si fallan *todas* las consultas
  de golpe, lo primero a revisar es si Regente avisó una URL nueva.
- Login: `POST /api/v1/auth/login` con usuario + token de API, devuelve un JWT
  que **vence a los 60 minutos**. `core/regente_client.py` lo cachea en memoria
  y lo renueva con 5 minutos de margen; `utils_regente.py` además reintenta una
  vez cuando una consulta vuelve 401.
- Endpoints de cuenta corriente (todos por `id_sujeto`, todos GET):
  `/rgCompCuotaNg/deuda`, `/rgComprobanteNg/cta_cte`,
  `/rgComprobanteNg/estado_cuenta`, `/rgComprobanteNg/listado`.
- Trampas del formato, ya resueltas en los parseadores de `utils_regente.py`:
  importes, fechas e ids llegan **como texto**; la fila "Saldo Inicial" de
  `cta_cte` es la excepción y trae la fecha como **timestamp Unix**; el `saldo`
  de la deuda es siempre positivo y el signo lo da `signo_comp` (-1 = nota de
  crédito); el `total` de deuda **no** incluye punitorios.
- **El servidor corta las consultas a los 30 segundos.** Nunca usar `limite=0`
  por defecto: siempre un límite acotado y, donde se pueda, un rango de fechas.
- **Limitación conocida:** el buscador de `rgSujetoNg` (parámetro `q`) busca
  solo por nombre del sujeto, **no por CUIT**. Regente lo tiene agendado para una
  versión futura. Mientras tanto, la búsqueda por CUIT se resuelve contra la
  tabla `clientes` de Supabase (columna `id_sujeto_regente`).
- El usuario de integración necesita los permisos 112, 144, 221, 691, 879 y 984.
  Si le vence la contraseña en Regente, la API empieza a devolver 403.

## El módulo de Cuentas Corrientes

`modulos/cuenta_corriente.py` no dibuja contenido: es un **contenedor** con un
registro de consultas (`CONSULTAS`), un `st.segmented_control` para elegir cuál
se muestra y `abrir_ficha()` para que un listado pueda saltar a la ficha de un
cliente. Cada consulta vive en su propio `modulos/cc_*.py`.

El valor del módulo no está en consultar un cliente —eso ya lo hace Regente—
sino en las vistas cruzadas entre clientes que el ERP no da. Hoy **solo está
implementada "Ficha de cliente"** (`modulos/cc_ficha_cliente.py`); las otras
cuatro figuran en el selector marcadas con lo que están esperando. Tres de ellas
dependen de que Regente habilite `estado_cuenta` y `listado` **sin `id_sujeto`**
(pedido el 25/09/2026): sin eso no se puede listar a todos los deudores, y una
lista de cobranza incompleta no sirve.

### Entidades pagadoras

Un cliente puede tener sus facturas pagadas por otro. Eso se ve en los
**garantes del comprobante**, así que la ficha consulta los garantes de sus
primeros comprobantes pendientes y, si aparece alguien, avisa **"Esta cuenta la
paga: …"**. Cuesta una consulta por comprobante, por eso se miran solo tres y en
paralelo (`utils_regente.obtener_pagadores_de_deuda`).

Al revés todavía no se puede: desde la entidad pagadora no hay forma de listar a
quiénes les paga, y por eso su saldo aislado engaña. Está en los pendientes.

### El semáforo

El color **se calcula, no se guarda** (`core/semaforo.py`): verde hasta 2 días
de atraso, amarillo de 3 a 10, rojo de 11 en adelante; sin deuda o con saldo a
favor, no hay semáforo.

**Anticipos y saldos a favor (aclarado por Diego, 25/09/2026):** un comprobante
cuyo número empieza con `AnA-` es un **anticipo**, o sea un pago que el cliente
ya hizo y que todavía no se aplicó a una factura; en la tabla de deuda va con la
fila entera en verde. Y un **saldo actual negativo significa saldo a favor del
cliente**, así que se muestra con esas palabras y no como un número en menos.
Ojo que `signo_comp` vale -1 tanto para anticipos como para notas de crédito:
para distinguirlos hay que mirar el prefijo del número (`utils_regente.es_anticipo`).

**TRAMPA IMPORTANTE, verificada el 25/09/2026:** el campo `dias` que devuelve
`estado_cuenta` **no es confiable** — llega en 0 aun con facturas vencidas hace
meses (el cliente 89401 tenía 134 días de atraso y $18M de deuda con `dias` = 0).
Los días de atraso hay que sacarlos del detalle de la deuda (el campo `atraso`
de cada cuota) o, si solo se tiene el estado de cuenta, calculándolos contra
`peor_fecha`, que sí viene bien. Y las notas de crédito y anticipos
(`signo_comp` = -1) **no cuentan como deuda vencida**: son plata a favor del
cliente. Los umbrales están aislados en `obtener_umbrales()`
porque más adelante se van a administrar desde la app, no desde el código.

Lo único manual es la **lista de urgentes** que arma cada vendedor, en la tabla
`lista_urgentes`. El puente entre el empleado que se loguea y su usuario
vendedor de Regente es el **legajo**: `empleados.usuario_regente` cachea ese
cruce (114 de 116 cargados; el legajo 999 quedó sin resolver porque corresponde
a personas distintas en cada sistema).

## Tablas de Supabase que más se usan

`empleados` (login: legajo + pin; `usuario_regente` es el puente con Regente),
`lista_urgentes` (clientes marcados como urgentes por cada vendedor; RLS solo
para `anon`, un cliente del portal no la ve), `clientes` (razón social, CUIT, límites,
permisos del portal, `id_sujeto_regente`, `auth_user_id`), `cuits_afectados`
(lista negra del BCRA), `cobranzas_pendientes` (lote a auditar del bot de
WhatsApp), `cuentas_propias` (cuentas bancarias de BC, para resolver el destino
de una transferencia).

## Secrets necesarios

`lector.py` (Streamlit Cloud — cada app tiene su propia bóveda):
`SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`, `SCRAPEOPS_API_KEY`,
`REGENTE_API_URL`, `REGENTE_API_USUARIO`, `REGENTE_API_TOKEN`.

`webhook.py` (Render, como variables de entorno): las mismas, más las del
proveedor de WhatsApp.

`REGENTE_API_URL` va **sin** el `/api/v1` final: eso lo agrega el código.

## Pendientes

### Esperando respuesta de Regente (Damián)

Diego mandó el pedido por mail el **25/09/2026**. Hasta que haya respuesta, no
se avanza con las consultas de listado: una lista de cobranza que puede dejar
afuera deudores reales no sirve.

1. **`GET /rgComprobanteNg/estado_cuenta` sin `id_sujeto`** — para traer el
   listado de todos los clientes de una. Habilita las consultas "Vencidas" y
   "Mis urgentes".
2. **`GET /rgComprobanteNg/listado` sin `id_sujeto`** — para saber quién compró
   en un período y quién no. Habilita "Sin cargar".

### Para sumar al pedido cuando conteste

No se mandaron todavía, a la espera de la respuesta al primer mail:

3. **Los campos resumidos de `estado_cuenta` vienen mal.** Verificado el
   25/09/2026 con casos reales:
   - `dias` llega en **0** aunque haya facturas vencidas hace meses (cliente
     89401: 134 días de atraso y $18M de deuda, con `dias` = 0).
   - `peor_fecha` a veces devuelve **la fecha de hoy** en lugar del vencimiento
     pendiente más viejo (cliente 1327: devuelve 25/09 cuando su factura más
     vieja vence el 15/10).

   Hoy lo esquivamos calculando ambos desde el detalle de la deuda, pero **el
   listado multi-cliente no va a traer ese detalle**: si devuelve estos mismos
   campos rotos, el ranking de atrasados va a salir mal ordenado. Hay que
   pedirle a Damián que los revise junto con los puntos 1 y 2.
4. **La deuda no consolida las entidades pagadoras.** Una entidad pagadora es
   un cliente que manda a cargar combustible a otros: las cargas se facturan a
   nombre de esos terceros, pero las paga ella. El vínculo está en los
   **garantes de cada comprobante** (subtabla `compgarantes`), no en la ficha
   del cliente: ojo que `sujetos_relacion` tiene un tipo "Pagadora"
   (`id_rel` = 5) que en la práctica está vacío. **La pantalla de caja de
   Regente consolida la deuda**, pero la API no. Caso verificado el 25/09/2026
   con el cliente 1058:

   | | Total |
   |---|---|
   | `GET /rgCompCuotaNg/deuda?id_sujeto=1058` | −6.088.623,87 |
   | Caja de Regente, mismo cliente | −402.259,66 |

   Sin consolidar, una entidad pagadora aparenta millones a favor y sus
   clientes figuran como deudores sin serlo. Hay que pedir que la deuda y el
   estado de cuenta se puedan calcular consolidados como la caja, o al menos
   poder consultar los comprobantes por su garante (hoy solo se puede ir del
   cliente facturado hacia su pagadora, leyendo `compgarantes` comprobante por
   comprobante: eso es lo que hace `utils_regente.obtener_garantes()`).

5. **Paginación en `rgSujetoNg`** — hoy devuelve como máximo 500 filas aun con
   `limite=0`, y no tiene `offset`. Con el punto 1 resuelto deja de hacer falta.

### Otros pendientes del proyecto

- **Claudia Montenegro no está en Sistema-BC.** El legajo 999 le corresponde a
  ella (en Regente es `cmontenegro`), pero no tiene fila en `empleados`. Ricardo
  Buyatti, que ocupaba ese número por error, se movió al legajo **1003** el
  25/09/2026 — no tiene cuenta en Regente, así que su `usuario_regente` queda en
  null. **Ricardo ahora entra a la app con el legajo 1003**, no con el 999. Si
  algún día hay que dar de alta a Claudia, el 999 está libre y su usuario de
  Regente se va a resolver solo por legajo.
- **Segunda tanda de diseño**: los cambios de CSS global de `lector.py`
  (títulos en gris, números de `st.metric` en gris, cifras tabulares, ancho
  máximo de lectura), mudar ahí la regla del botón de formulario y una vista de
  la deuda pensada para el celular.
- **El rojo en los títulos**: Diego lo iba a consultar. Por ahora queda como
  está.
- **Filtros comunes** (sucursal, vendedor, rango de montos) en el contenedor:
  entran junto con el primer listado.
