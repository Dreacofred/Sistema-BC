# Sistema-BC — contexto del proyecto

Sistema interno de **BC Combustibles SA** (Santa Fe, Argentina). Python +
Streamlit, con Supabase como base de datos y Claude (Anthropic) como motor de IA.
Repositorio: `Dreacofred/Sistema-BC`. El idioma de trabajo es el español
rioplatense, incluidos los comentarios del código.

Sucursales (`NOMBRES_SUCURSALES` en `lector.py`): 1 Reconquista, 2 Avellaneda,
3 Florencia, 4 Recreo.

**En este repositorio conviven dos sistemas funcionalmente distintos**, que
comparten `lector.py` y `core/`:

- El **Bot de Cobranzas**: cheques y comprobantes que entran por WhatsApp,
  auditoría, verificación BCRA y la integración con Regente.
- El **Sistema de Gestión de Cargas**: los pedidos de carga de combustible de
  los clientes (Generador de Resumen, Gestión de Clientes, y el módulo de
  proveedores que quedó fuera del menú).

El módulo de Cuentas Corrientes, el más nuevo, es una tercera pata que se apoya
en la misma API de Regente que usa el bot.

**La integración con Regente es solo para BC Combustibles.** Bonazzola y Buyatti,
las otras empresas del grupo, tienen instalaciones de Regente separadas, y las
credenciales de `ia_client` no llegan a esas bases (probado).

## Reglas de trabajo

- **Commits, según de qué sean** (regla ajustada con Diego el 25/09/2026):
  - *Documentación, comentarios, textos de pantalla y cambios cosméticos*:
    alcanza con avisarle qué archivos entran, y se commitea directo.
  - *Cambios de lógica*: se le muestran los archivos **y el mensaje propuesto**,
    y se espera su OK. Cuenta como lógica todo lo que toque `webhook.py`, la
    integración con Regente, las consultas a Supabase o el flujo de auditoría.
  - **Ante la duda, se trata como lógica.**
  - El push es una decisión aparte: si no lo pidió, se pregunta.
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
| `app_clientes.py` | Pantalla de verificación de cheques contra el BCRA, titulada "Herramienta exclusiva para clientes de BC Combustibles". Tres pestañas: consulta manual por CUIT, escáner de cheques con IA y carga masiva por Excel. | Streamlit Cloud |
| `webhook.py` | Servidor Flask del bot de WhatsApp de cobranzas: recibe fotos de cheques y comprobantes y los lee con Claude. | Render |

`bot.py` no es una app aparte: es la pantalla de auditoría de comprobantes, que
`lector.py` ejecuta con `exec()` dentro de la pestaña "Laboratorio IA". Por eso
usa los secrets de `lector.py` y no los suyos.

**OJO con `app_clientes.py`: no tiene ningún login.** No pide legajo y PIN como
`lector.py`, ni usa Supabase Auth: quien abra la URL entra directo y puede
consultar cualquier CUIT contra el BCRA. PENDIENTE DE DEFINIR cómo se controla
el acceso a esa app (¿URL privada? ¿no está publicada?).

## Módulos del menú de `lector.py`

Cada módulo es `modulos/<nombre>.py` con una función `mostrar(...)` que recibe
ya inicializados los clientes que necesita (Supabase, Claude) desde `lector.py`.

| Pestaña | Módulo | Firma | Qué hace |
|---|---|---|---|
| Generador de Resumen | `modulos/resumen.py` | `mostrar(supabase, cliente_claude, user, NOMBRES_SUCURSALES, COLOR_ROJO)` | Toma las órdenes de la tabla `ordenes_carga`, lee los remitos con Claude, permite corregirlos a mano y exporta el resumen final a Excel (`openpyxl`). Sube las fotos al bucket `remitos` de Supabase Storage. El módulo más grande del repo. |
| Cuentas Corrientes | `modulos/cuenta_corriente.py` | `mostrar(supabase)` | **Contenedor** de consultas sobre la cuenta corriente de Regente (solo lectura). Ver abajo. |
| Verificación BCRA | `modulos/verificacion_bcra.py` | `mostrar(supabase, cliente_claude)` | Deudores y cheques rechazados del BCRA, en tres pestañas (manual, escáner con IA, carga masiva). Guarda CUITs en `cuits_afectados`. Misma lógica que `app_clientes.py`, pero adentro de la app interna. |
| Gestión de Clientes | `modulos/clientes.py` | `mostrar(supabase, NOMBRES_SUCURSALES)` | Alta y edición de clientes, límites y permisos del portal. |
| Laboratorio IA | `bot.py` (vía `exec`) | — | Auditoría de los comprobantes que entran por el bot de WhatsApp. Ver "El bot de cobranzas", abajo. |

`modulos/proveedores.py` ("Facturas de Proveedores") **quedó fuera del menú en
septiembre 2026**, reemplazado por Cuentas Corrientes. El archivo sigue en el
repositorio pero no lo llama nadie. Era el último consumidor de Gemini: por eso
`lector.py` ya no crea el cliente de `genai` ni usa `GEMINI_API_KEY`.

## El bot de cobranzas

Es el circuito que va desde una foto de cheque mandada por WhatsApp hasta un
archivo listo para importar en Regente. Son cinco archivos y dos procesos
distintos.

### 1. Entrada: `webhook.py` (Flask, en Render)

Expone `POST /webhook` y escucha los eventos de **Green-API** (el proveedor que
conecta WhatsApp). Solo atiende `incomingMessageReceived`. Funciona por
comandos, dentro de un chat:

| Comando | Qué hace |
|---|---|
| `!bot <texto>` | Abre un lote. Busca el texto en `clientes.nombre` (`ilike`) y toma el primer resultado; si no encuentra, avisa y no abre nada. |
| *(mandar fotos o PDFs)* | Con un lote abierto, descarga cada archivo a disco y lo suma al lote. Responde "Archivo N recibido". |
| `!procesar` | Cierra el lote y lo manda a procesar en un hilo aparte, para contestarle a WhatsApp enseguida. |

**Los lotes viven en memoria del proceso** (`lotes_abiertos`, un diccionario a
nivel de módulo). Si Render reinicia el servicio, los lotes abiertos se pierden;
y con más de un worker de gunicorn, un mensaje podría caer en un proceso que no
tiene el lote. PENDIENTE DE DEFINIR con cuántos workers corre hoy en Render.

### 2. Lectura con IA y guardado (`procesar_y_guardar`)

1. Calcula el **SHA-256 de cada archivo** y consulta `hashes_comprobantes`: los
   repetidos se saltean y se avisa por WhatsApp. Si fallara esa consulta,
   procesa igual — prefiere duplicar antes que perder un comprobante.
2. Sube los archivos nuevos al bucket **`comprobantes`** de Supabase Storage.
3. Se los manda a Claude (`claude-sonnet-5`) con la herramienta forzada
   `registrar_cheques_whatsapp` (`core/prompts_ia.py`). Nunca texto libre.
4. Inserta una fila por cheque en **`cobranzas_pendientes`**, con
   `estado_auditoria = "Pendiente"` y un `lote_id` (UUID) común. Cada fila
   queda apuntada a la foto de la que salió, por el número de imagen que
   devuelve la IA.
5. Recién con todo guardado registra los hashes, para no marcar como procesado
   algo que falló.
6. Si el comprobante traía un **total declarado** y no coincide con la suma de
   los cheques leídos (tolerancia de $1), avisa por WhatsApp que puede faltar
   una foto o que un monto se leyó mal.

### 3. Auditoría: `bot.py` (dentro de "Laboratorio IA")

Trae de `cobranzas_pendientes` todo lo que está en `"Pendiente"`, agrupado por
cliente. Cada comprobante es un acordeón con la imagen grande al lado del
formulario (los PDF se muestran embebidos con el visor de Google Docs). El
auditor corrige y confirma fila por fila; las correcciones viven en
`st.session_state` hasta cerrar el lote.

Cuando a una transferencia le falta el **código de banco**, que casi nunca
viene impreso, `core/cuentas_propias.py` lo resuelve solo: compara la cuenta, el
CBU/CVU y el alias de destino que extrajo la IA contra la tabla
`cuentas_propias`, en ese orden de prioridad, ignorando guiones y espacios.

Con todo revisado, el lote se cierra en dos pasos deliberados: primero se
**descarga el CSV** para importar en Regente (Titular, Emisión, Venc., Nro,
Bco., NCta., Plaza, Monto) y recién después, tildando una confirmación, se
marcan las filas como auditadas en Supabase.

### 4. Integración con Regente: la carga automática todavía no se puede programar

Hoy el lote sale por CSV y alguien lo carga a mano en Regente. Automatizar ese
último paso es el objetivo, y está frenado por un dato que falta de parte de
Regente. Lo que hay hecho:

**Una vista previa dentro de `bot.py`**, en un desplegable, que arma los datos y
consulta si cada emisor ya existe. **No escribe nada**, ni en Regente ni en
Supabase.

**`core/regente_resolucion.py`** sí consulta Regente, **solo con GET**, para
decidir qué hacer con cada emisor: primero lo busca por número de cuenta y, si
no aparece, por apellido comparando **siempre por CUIT exacto, nunca por
parecido de nombre**. Devuelve `usar_existente`,
`crear_cuenta_para_existente`, `crear_sujeto_y_cuenta` o `revision_manual`.

⚠️ **Hoy ese segundo camino está roto, y además quedó obsoleto.** Está roto
porque saca el CUIT con una expresión regular aplicada al campo `"?column?"` de
la respuesta, un nombre que Regente ya no devuelve: ese campo ahora se llama
`detalle_adic` (verificado el 25/09/2026). Como el CUIT le sale siempre vacío,
la comparación nunca coincide y **cualquier emisor que ya exista en Regente se
clasifica igual como "crear_sujeto_y_cuenta"**.

Y quedó obsoleto porque todo ese rodeo —buscar por apellido, parsear un texto
concatenado, comparar CUITs a mano— existía solo porque no se podía buscar por
CUIT. Con `GET /rgSujetoNg/buscar?criterio=D:{cuit}` se resuelve en una
consulta, y la respuesta ya trae el CUIT en su propio campo `doc`, sin parsear
nada. **Al corregirlo conviene reemplazarlo, no parchear el nombre del campo.**
Se venía estimando que alrededor de la mitad de los cheques que llegan son de
emisores o cuentas que no están en Regente, lo que haría del alta automática de
sujetos un caso central y no una excepción. **Ese número hay que tomarlo con
pinzas**: por el bug que se explica abajo, la pantalla viene mostrando el 100%
de los emisores como nuevos, así que la estimación puede estar contaminada. No
conviene diseñar sobre ese porcentaje hasta que la resolución funcione. Un emisor nuevo necesita **dos altas**: el sujeto y la cuenta
(`rgSujetoNg` + `rgSujetoCuentaNg`); sin la segunda, el próximo cheque de esa
cuenta se vuelve a tratar como nuevo.

#### El mecanismo real de escritura (confirmado con Damián el 03/09/2026)

No son varios POST separados a `rgReciboNg` / `rgValorNg`, como se había
supuesto al principio. Es **un solo `PUT /api/v1/rgCajaNg/{id_caja}`**,
transaccional (todo o nada), con cuatro bloques: `usuario`, `criterios`, `datos`
y `detalles`. Dentro de `detalles`, el bloque `"1"` es *qué se paga* y el `"3"`
es *con qué se paga*; la suma de montos de uno tiene que dar exactamente igual a
la del otro. Hay campos que **nunca** hay que mandar porque Regente los completa
solo (`id_recibo`, `id_cuenta`, `id_tipo_movimiento`, `ult_modif`, y las fechas
del encabezado, que tienen un bug conocido).

Dos detalles que sorprenden: el **número de recibo vuelve como texto libre**
adentro de `data.razon` (`"[ RECIBO NRO: 4321 :]"`, hay que sacarlo con regex),
y **Regente no valida que la caja esté abierta**: si se le manda una cerrada,
graba igual y descuadra el cierre sin avisar. Para eso está
`POST /api/v1/rgCajaNg/abrir`, que devuelve la caja abierta del cajero o la crea,
pensado explícitamente como paso previo a registrar una cobranza.

#### Siempre Anticipo

Decisión de diseño cerrada: el bot **siempre** carga los pagos como *Anticipo*,
nunca imputando a una factura puntual. Es cómo trabaja BC —casi nunca se sabe de
antemano qué factura está pagando el cliente— y de paso evita tener que resolver
`id_comp`, `orden` y `nro_cuota`.

**Ese es el bloqueante**: el Anticipo se escribe con el bloque `detalles."0"`, y
Damián todavía no mandó qué campos lleva (pedido el 04/09, respondió "lo vemos y
te envío la estructura"; el mail del 10/09 trajo otras mejoras pero no esta).
Hasta que llegue, no se puede programar el `PUT`.

#### ⚠️ `core/regente_mapeo.py` quedó obsoleto

Ese archivo arma los payloads del **mecanismo viejo**: un recibo por tipo de
pago con `criterios` y `datos` como diccionarios, al estilo `POST rgReciboNg`.
El mecanismo real confirmado después es el `PUT` de arriba, con `criterios` y
`datos` como **listas** y un bloque `detalles` que el archivo ni contempla. Son
formas incompatibles: **hay que rehacerlo cuando llegue la spec de
`detalles."0"`**.

Lo que sí sigue valiendo de ese archivo son las reglas de negocio que tiene
escritas (cómo se agrupan los cheques físicos, los electrónicos y las
transferencias, y que el tipo "Otro" se carga a mano), más el detalle de que un
recibo combinado y varios recibos separados dan el mismo resultado contable, así
que la agrupación se puede elegir por conveniencia.

**Regla de seguridad vigente:** ningún `POST` ni `PUT` de prueba contra la API
real hasta tener la spec y el OK explícito de Diego. Es producción y no hay
ambiente de pruebas.

### 5. El documento de continuidad del bot

`contexto-bot-cobranzas-completo_10-09-26.md` (última actualización 10/09/2026)
es el documento donde se viene registrando la investigación de la integración
con Regente: el mecanismo de escritura, los catálogos confirmados, los hallazgos
con datos reales y los pendientes con Damián. **Lo que dice sobre Regente es la
fuente más completa que hay**, y de ahí salen las secciones de arriba.

Cuidado con cuatro cosas que en ese documento quedaron viejas respecto del
código de hoy: dice que `lector.py` y `utils_bcra.py` siguen usando Gemini
(migraron a Claude en agosto), lista una carpeta `pages/` que no existe, dice
que Diego trabaja solo desde el editor web de GitHub, y no incluye nada del
módulo de Cuentas Corrientes.

## Los prompts y herramientas de IA

Todo lo que se le manda a Claude vive en `core/prompts_ia.py`, y siempre con
*tool use* forzado: la respuesta viene tipada, no hay que parsear JSON a mano.
El modelo es `claude-sonnet-5` en los tres casos.

| Herramienta | La usa | Devuelve |
|---|---|---|
| `registrar_cheques_whatsapp` | `webhook.py` | Una lista de cheques (tipo, banco, código de banco y sucursal, cuenta, número, monto, fechas, CUIT y razón social del emisor, y los datos de destino de una transferencia) más el total declarado del comprobante. |
| `registrar_lectura_remito` | `modulos/resumen.py` | Fecha, razón social, importe, comprobante, litros, detalle de productos y observaciones de la IA. |
| `registrar_cheques_para_verificacion` | `utils_bcra.py` (módulo Verificación BCRA) | Número de cheque, emisor y CUIT. |

En el mismo archivo quedan tres prompts viejos de Gemini, de texto libre:
`PROMPT_LECTURA_CHEQUES` (ya no lo usa nadie), `PROMPT_FACTURAS_PROVEEDORES`
(solo `modulos/proveedores.py`, que está fuera del menú) y
`PROMPT_AUDITORIA_REMITOS`, que `lector.py` **importa pero nunca usa**.

## APIs externas y dónde vive cada conexión

El patrón del proyecto es: **un archivo aparte con la conexión y el parseo, y el
módulo de `modulos/` solo con la pantalla.**

| API | Archivo de conexión | Notas |
|---|---|---|
| BCRA (Central de Deudores y cheques rechazados) | `utils_bcra.py` | Se consulta a través del proxy de ScrapeOps (`SCRAPEOPS_API_KEY`). Lo comparten el módulo Verificación BCRA y `app_clientes.py`. |
| WhatsApp (Green-API) | `webhook.py` | Recibe los mensajes por webhook y contesta con `sendMessage`. Necesita `GREEN_API_URL` y `GREEN_API_TOKEN`. |
| Claude / Anthropic | `core/prompts_ia.py` (prompts y herramientas) | Modelo: `claude-sonnet-5`. Todos los módulos usan *tool use* forzado en vez de parsear JSON a mano. |
| Regente — cuenta corriente | `utils_regente.py` | Los 4 endpoints de solo lectura del instructivo TK-3139. |
| Semáforo de cobranza | `core/semaforo.py` | La regla del color por días de atraso. Sin dependencias: la usan la pantalla, y más adelante el portal y el bloqueo de órdenes. |
| Regente — sujetos, cuentas, usuarios y catálogos | `core/regente_client.py` | Login, caché del JWT, el puente legajo ↔ usuario de Regente y las consultas que usa el bot de cobranzas. `utils_regente.py` reusa de acá el login y el token. |
| Supabase | `core/supabase_client.py` | `get_supabase_client()` cacheado con `@st.cache_resource`. Lo usan `lector.py` y `app_clientes.py`; `bot.py` y `webhook.py` arman su propio cliente (uno con `st.secrets`, el otro con variables de entorno). El docstring del archivo dice que no lo usa nadie: quedó desactualizado. |

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
- **Búsqueda de clientes.** El buscador genérico de `rgSujetoNg` (parámetro
  `q`) busca solo por nombre del sujeto, **no por CUIT**. Por eso hoy
  `utils_regente.buscar_cliente_por_cuit` resuelve el CUIT contra la tabla
  `clientes` de Supabase (columna `id_sujeto_regente`), que solo cubre a los
  clientes dados de alta en Sistema-BC.
  **La solución ya existe y está confirmada, falta adoptarla:** Damián liberó
  `GET /rgSujetoNg/buscar?criterio=…` el **10/09/2026**, con la prueba ya
  ejecutada en Swagger. Resuelve por **id, CUIT o nombre** en una sola consulta
  y devuelve el juego completo de campos (domicilio, localidad, teléfono,
  condición de IVA). Acepta el valor pelado o con prefijos combinables: `S:`
  para el id_sujeto y `D:` para el documento (`criterio=D:30999002478`).
  Verificado otra vez el 25/09/2026: con `D:30547794482` devuelve AGRONORTE SRL,
  y **cuando no hay coincidencias responde `{"ok": true, "data": [], "error":
  null}`** — o sea que el caso "no existe, hay que darlo de alta" se detecta con
  una lista vacía, no con un error.
- El usuario de integración necesita los permisos 112, 144, 221, 691, 879 y 984.
  Si le vence la contraseña en Regente, la API empieza a devolver 403.
- **No hay más endpoints que buscar.** El OpenAPI (`/openapi.json`) declara
  **696 rutas**, pero solo **seis tienen lógica propia**: los cuatro de cuenta
  corriente, `/rgSujetoNg/buscar` y `/clases`. Todo el resto es el CRUD genérico
  de cada tabla (`rgLoQueSea/` con `q`, `clave`, `limite` y `campos_busq`).
  Revisado entero el 25/09/2026.
- **El CRUD genérico no sirve para traer volumen**, aunque parezca el atajo
  obvio: `rgComprobanteNg/?q=%` devuelve **500 a los 32 segundos** (el corte del
  servidor) y `rgCompCuotaNg/` devuelve `ok:false` con cero filas. Sí sirve para
  filtrar por un campo puntual: `campos_busq` acepta el nombre de la columna.
- **Cuánto tarda, si alguna vez hay que barrer muchos clientes** (medido el
  25/09/2026 contra el servidor real): **1,41 s por cliente** de a uno, y
  **0,46 s por cliente con 4 hilos**, sin un solo error. Con 4 hilos, 500
  clientes son unos 4 minutos. Ojo que **el túnel ngrok empieza a cortar
  conexiones cuando le entra una ráfaga larga** — pasó a las ~190 consultas
  seguidas —, así que cualquier barrido tiene que reintentar y, sobre todo,
  **informar lo que no pudo resolver en vez de descartarlo en silencio**.

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
de cada cuota). Si solo se tiene el estado de cuenta, se calculan contra
`peor_fecha`, que es menos malo pero **tampoco es confiable del todo**: en el
cliente 1327 devolvió la fecha de hoy en lugar del vencimiento pendiente más
viejo. Por eso `core/semaforo.py` se queda con el mayor de los dos valores. Y
las notas de crédito y anticipos (`signo_comp` = -1) **no cuentan como deuda
vencida**: son plata a favor del cliente.

Los umbrales están aislados en `obtener_umbrales()` porque más adelante se van a
administrar desde la app, no desde el código.

Lo único manual es la **lista de urgentes** que arma cada vendedor, en la tabla
`lista_urgentes`. El puente entre el empleado que se loguea y su usuario
vendedor de Regente es el **legajo**: `empleados.usuario_regente` cachea ese
cruce (114 de 116 cargados; el legajo 999 quedó sin resolver porque corresponde
a personas distintas en cada sistema).

## Supabase

Proyecto `Sistema-BC` (ref `bjhykcdhafoqpfkpngvw`). **Las tablas que toca este
repositorio son solo ocho**, y son estas:

| Tabla | La usa | Para qué |
|---|---|---|
| `empleados` | `lector.py` | Login por legajo + PIN. `legajo` es la clave primaria (no hay columna `id`) y `usuario_regente` es el puente con Regente. |
| `clientes` | `modulos/clientes.py`, `bot.py`, `webhook.py`, `utils_regente.py` | Razón social, CUIT, límites, permisos del portal, `id_sujeto_regente`, `auth_user_id`. |
| `ordenes_carga` | `modulos/resumen.py` | Las órdenes que alimentan el Generador de Resumen. |
| `cobranzas_pendientes` | `webhook.py`, `bot.py` | El lote de cheques que entra por WhatsApp y espera auditoría. |
| `hashes_comprobantes` | `webhook.py` | SHA-256 de cada archivo ya procesado, para no cargar dos veces el mismo. |
| `cuentas_propias` | `core/cuentas_propias.py` | Cuentas bancarias de BC, para resolver el banco de destino de una transferencia. |
| `cuits_afectados` | `utils_bcra.py`, `modulos/verificacion_bcra.py` | Lista negra del BCRA. |
| `lista_urgentes` | *(todavía ningún archivo)* | Clientes marcados como urgentes por cada vendedor. Creada el 25/09/2026; la va a usar la consulta "Mis urgentes" cuando se pueda implementar. |

Buckets de Storage: **`remitos`** (fotos del Generador de Resumen) y
**`comprobantes`** (archivos que entran por WhatsApp).

El proyecto tiene alrededor de **treinta tablas más** que este repositorio no
toca: `tanques`, `mangueras`, `cierres_turno`, `lecturas_totalizador`,
`movimientos_camiones`, `pedidos_datalink`, `agenda_items` y compañía.
PENDIENTE DE DEFINIR qué aplicación las usa. Hay pistas de que existe al menos
una app fuera de este repositorio: las políticas de RLS de `clientes` y
`empleados` se llaman "Permitir leer … a Vercel", y `modulos/clientes.py` crea
usuarios con `supabase.auth.admin.create_user` y guarda el `auth_user_id`, pero
**ninguna app de este repositorio usa Supabase Auth para que entre un cliente**.

### La RLS no protege nada en este repositorio

Todas las tablas tienen RLS activada y con políticas, pero **`SUPABASE_KEY` es
la service key (`sb_secret_…`)**, así que todas las apps de este repo
**saltean la RLS por completo**. Las políticas son irrelevantes para este
código; existirán por la app de afuera, que probablemente use la anon key.

Esto importa para no engañarse: cuando creé `lista_urgentes` le puse políticas
solo para el rol `anon`, pensando que así un cliente del portal no la vería.
**No protege nada**, por dos motivos encadenados: `app_clientes.py` no tiene
login (entra con el mismo rol que la app interna) y, con la service key, el rol
ni siquiera se evalúa.

**En este proyecto, la única barrera real entre un dato y un usuario es qué
consulta hace cada pantalla.** Si hay que proteger algo de verdad, se cambia la
forma de conectarse —una key distinta para la app interna, o un backend
propio—, no se agregan políticas.

## Secrets necesarios

`lector.py` (Streamlit Cloud — cada app tiene su propia bóveda):
`SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`, `SCRAPEOPS_API_KEY`,
`REGENTE_API_URL`, `REGENTE_API_USUARIO`, `REGENTE_API_TOKEN`.

`webhook.py` (Render, como variables de entorno) usa **solo cinco**, no todas
las de arriba: `SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`,
`GREEN_API_URL` y `GREEN_API_TOKEN`.

`bot.py` no tiene bóveda propia: corre adentro de `lector.py`, así que usa sus
secrets — incluidos los tres de Regente, que necesita para la vista previa de
integración.

`GEMINI_API_KEY` ya no lo usa ningún archivo que esté en el menú. El único que
sigue llamando a Gemini es `modulos/proveedores.py`, que quedó fuera de la app.

`REGENTE_API_URL` va **sin** el `/api/v1` final: eso lo agrega el código.

### Para correr algo en local

Hay un `.streamlit/secrets.toml` en la máquina de Diego (ignorado por git) que
tiene **solo las tres credenciales de Regente**; las otras cuatro están
comentadas. Por eso **`lector.py` entero no levanta en local**: falla al pedir
`SUPABASE_URL` apenas arranca.

Para ver el módulo de Cuentas Corrientes sin esos secrets está
`scripts/preview_cuenta_corriente.py`, que corre esa pantalla sola con el mismo
CSS de la app:

```bash
streamlit run scripts/preview_cuenta_corriente.py
```

## Deuda técnica conocida

Todo esto es verificable leyendo los archivos, y conviene tenerlo a mano antes
de tocar algo:

- **`core/regente_resolucion.py` tiene un bug vivo**: busca el CUIT en un campo
  `"?column?"` que la API ya no devuelve (hoy es `detalle_adic`), así que nunca
  reconoce a un emisor existente. Se arregla reemplazando esa búsqueda por
  `GET /rgSujetoNg/buscar?criterio=D:{cuit}`.
- **`core/regente_mapeo.py` quedó obsoleto**: arma el payload del mecanismo de
  escritura viejo (POST por entidad), incompatible con el `PUT` a `rgCajaNg` que
  se confirmó después. Hay que rehacerlo. Ver la sección del bot de cobranzas.
- **`modulos/proveedores.py` está muerto**: nadie lo llama desde septiembre de
  2026, pero sigue en el repositorio y es el único consumidor de Gemini. Por él
  siguen en `requirements.txt` `google-genai` y `google-generativeai`.
- **`lector.py` importa `PROMPT_AUDITORIA_REMITOS` y no lo usa** en ninguna
  línea.
- **El docstring de `core/supabase_client.py` dice que no lo usa nadie**, cuando
  lo usan `lector.py` y `app_clientes.py`.
- **`contexto-bot-cobranzas.md` está desactualizado** (julio 2026, dice que el
  motor de IA es Gemini).
- **Los lotes del bot de WhatsApp viven en memoria del proceso**: se pierden si
  Render reinicia.
- **El truco de `<div class="tarjeta-pro">`** que usan `modulos/clientes.py`,
  `modulos/resumen.py`, `modulos/verificacion_bcra.py` y `app_clientes.py` no
  envuelve nada: Streamlit sanitiza ese HTML y cierra el div solo, así que deja
  una barra blanca vacía. En `modulos/cuenta_corriente.py` ya se reemplazó por
  `st.container(border=True)`.
- **Los botones de formulario salen sin el rojo de la marca** en Gestión de
  Clientes y en el bot de auditoría: el CSS de `lector.py` apunta a
  `.stButton>button`, que no alcanza a `.stFormSubmitButton`.

## Pendientes

### ⛔ El árbol de git está así a propósito — no lo "limpies"

Si `git status` muestra esto, **está bien y no hay que arreglarlo**:

```
 D contexto-bot-cobranzas.md                    ← borrado, SIN commitear
?? contexto-bot-cobranzas-completo_10-09-26.md  ← nuevo, SIN trackear
```

`contexto-bot-cobranzas.md` era el volcado viejo del bot (julio 2026) y Diego lo
reemplazó por el nuevo. **El borrado se dejó sin commitear a propósito**: mientras
no se commitee, el archivo viejo sigue recuperable con
`git checkout -- contexto-bot-cobranzas.md` (verificado el 25/09/2026: 26.982
bytes accesibles desde HEAD).

Se mantiene así hasta decidir **dónde van a parar los JSON reales de las
respuestas de la API y el detalle de los dos cheques que se cargaron a mano el
03/09/2026**, que están en el documento nuevo y que el `CLAUDE.md` no absorbió a
propósito. Decisión ya tomada: **van a un `docs/` aparte, no acá**. Recién
cuando eso esté hecho se commitean juntos el borrado del viejo y el alta del
nuevo.

**No commitear ese borrado, no borrar el archivo sin trackear y no hacer
`git checkout`/`git clean` sobre ellos** sin hablarlo con Diego.

### 🔴 Lo más urgente: el acceso a `app_clientes.py`

`app_clientes.py` **no tiene ningún control de acceso**: no pide legajo y PIN
como `lector.py` ni usa Supabase Auth. Cualquiera que tenga la URL entra y puede
consultar el historial de deudas y cheques rechazados de **cualquier CUIT** del
país contra el BCRA, y esas consultas se pagan con los créditos de ScrapeOps de
BC. Además la app se conecta con la service key de Supabase.

PENDIENTE DE DEFINIR con Diego: si esa app está publicada, quién tiene la URL y
qué control corresponde ponerle.

### Esperando respuesta de Regente (Damián)

Diego le mandó **dos mails el 25/09/2026**: primero uno con los puntos 1 y 2, y
después uno consolidado con los cinco que siguen. **Los cinco están enviados**;
lo que falta es la respuesta. Hasta que llegue no se avanza con las consultas de
listado: una lista de cobranza que puede dejar afuera deudores reales no sirve.

1. **`GET /rgComprobanteNg/estado_cuenta` sin `id_sujeto`** — para traer el
   listado de todos los clientes de una. Habilita las consultas "Vencidas" y
   "Mis urgentes".
2. **`GET /rgComprobanteNg/listado` sin `id_sujeto`** — para saber quién compró
   en un período y quién no. Habilita "Sin cargar".

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

### Pendientes de la integración del bot de cobranzas

Vienen del documento de continuidad, actualizados al 10/09/2026:

1. **Bloqueante**: la spec del bloque `detalles."0"` (el del Anticipo), pedida a
   Damián el 04/09. Sin eso no se puede programar el `PUT` de escritura, y sin
   el `PUT` hay que seguir cargando el CSV a mano.
2. **Permiso de transferencias y e-checks**: cobrar por esos medios a una cuenta
   de la empresa necesita un permiso aparte del de cajas. Damián quedó en
   asignarlo el 04/09; verificar que esté activo antes de la primera prueba.
3. **`cod_postal_plaza`**: Regente lo valida contra su catálogo de localidades y
   rechaza el guardado si la plaza del cheque no está cargada (pasó con José
   Ingenieros, 1703). Hoy se resuelve a mano usando una localidad cercana que sí
   exista. Falta ver si hay un `rgLocalidadNg` para resolverlo por API.
4. **Catálogo de `id_area` por sucursal**, que hace falta para `rgCajaNg/abrir`.
   Solo está confirmado el 7 = Reconquista. Tampoco está definido con qué
   usuario técnico se abriría la caja en el flujo automático, ni qué significa
   el campo `ctrl_caja_recien_cerrada`.
5. **Rehacer `core/regente_mapeo.py`** sobre el mecanismo correcto, cuando
   llegue la spec del punto 1.
6. **De-duplicación por contenido**: el SHA-256 detecta el reenvío del mismo
   archivo, pero no una foto nueva del mismo cheque. Sin resolver.

Datos ya confirmados que conviene no volver a investigar: el `id_tipo_pago` es
9 para cheque físico, 66 para e-cheq y 1 para efectivo (las transferencias
dependen del banco); `id_estado` 14 es "Recibido", el estado de entrada de todo
cheque nuevo; Regente guarda los números de cuenta **sin ceros a la izquierda**,
así que hay que normalizar los dos lados antes de comparar; y el
`codigo_sucursal` del bot es el mismo dato que el `cod_postal_plaza` de Regente.

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
- **Adoptar `GET /rgSujetoNg/buscar`** en dos lugares: en el buscador de
  clientes de Cuentas Corrientes, para buscar por CUIT contra Regente en vez de
  contra Supabase; y en `core/regente_resolucion.py`, que además de simplificarse
  se arregla (hoy no reconoce emisores existentes).

### PENDIENTE DE DEFINIR (dudas del relevamiento del 25/09/2026)

Cosas que no se pueden contestar leyendo el repositorio y conviene aclarar con
Diego antes de asumir nada:

- **Qué aplicación usa las otras treinta tablas de Supabase** y el
  `auth_user_id` de `clientes`. Las políticas "a Vercel" sugieren una app fuera
  de este repositorio.
- **Con cuántos workers corre `webhook.py` en Render**, por el tema de los lotes
  en memoria. El documento viejo menciona el host
  `bot-sice-whatsapp.onrender.com`, pero eso no se puede verificar desde el
  código.
- **Si `modulos/proveedores.py` se borra o se deja**, y con él las dependencias
  de Gemini.
