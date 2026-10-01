# Contexto del Proyecto: Bot de Cobranzas — Sistema-BC (BC Combustibles)

Documento de continuidad para arrancar un chat nuevo sin perder nada de lo trabajado. Última actualización: **10/09/2026**, sesión de: revisión de mail de Damián con actualización de la API — dos endpoints nuevos confirmados (`rgSujetoNg/buscar` por CUIT, `rgCajaNg/abrir`). El bloqueante principal (spec de `detalles."0"` para Anticipo) sigue sin respuesta.

<aclaracion_importante_de_alcance>
Este proyecto es el **Bot de Cobranzas** de BC Combustibles: lectura de cheques/comprobantes por WhatsApp, auditoría de esos comprobantes, verificación BCRA, y (en curso) integración con el ERP Regente. Vive en el repo `Dreacofred/Sistema-BC`.

Este mismo repo también aloja, históricamente, módulos del **"Sistema de Gestión de Cargas"** (Facturas de Proveedores, Generador de Resumen de remitos, Gestión de Clientes) — sistema funcionalmente distinto (gestiona los pedidos de carga de combustible que hacen los clientes, no las cobranzas). Existe un chat de Claude aparte dedicado a ese sistema. No hay una restricción tan estricta como con el proyecto "Portal Clientes BC" (repo 100% aparte) — en `Sistema-BC`, cobranzas y gestión conviven en los mismos archivos compartidos (`lector.py`, `core/`).

**La integración con Regente es exclusiva para BC Combustibles.** Bonazzola y Buyatti (otras empresas del grupo) tienen sistemas internos de Regente completamente separados; las credenciales de API (`ia_client`) no tienen acceso a esas otras bases (probado en vivo).
</aclaracion_importante_de_alcance>

<resumen_proyecto>
El sistema automatiza la digitalización, extracción de datos y auditoría de **cheques y comprobantes de pago** que los clientes de BC Combustibles (4 sucursales: Reconquista, Avellaneda, Florencia, Recreo) envían por WhatsApp, para eventualmente cargarlos en el ERP interno de la empresa, Regente.

Roles/usuarios:
- **Playeros/operadores**: mandan fotos de cheques/comprobantes al bot de WhatsApp en un grupo.
- **Equipo administrativo/auditor**: revisa lo que extrajo la IA en un panel web, corrige errores, y (hoy) exporta a CSV para cargar manualmente en Regente — el objetivo final es automatizar ese último paso vía la API de Regente.
</resumen_proyecto>

<arquitectura_y_stack>
- **Bot de WhatsApp**: `webhook.py`, Python + Flask + Gunicorn, en **Render** (`bot-sice-whatsapp`). Webhook conectado a **Green-API**.
- **Motor de IA para lectura de comprobantes**: **Anthropic Claude** (`claude-sonnet-5`), con `tool_choice` forzado. El resto del sistema (`lector.py`, `utils_bcra.py`) sigue usando Gemini (`google.genai`).
- **Panel de auditoría de comprobantes**: `bot.py`, Streamlit. Corre DENTRO de `lector.py`, pestaña "Laboratorio IA" (hace `exec()` sobre `bot.py`).
- **Panel de gestión general**: `lector.py`, única app real en Streamlit Cloud ("BC Combustibles - Gestión Pro"), delega a módulos en `modulos/`.
- **Base de datos y storage**: Supabase (Postgres + Storage), proyecto `bjhykcdhafoqpfkpngvw`. Conexión vía `core/supabase_client.py`, clave `sb_secret_...`.
- **Verificación BCRA**: `utils_bcra.py`, vía proxy ScrapeOps.
- **ERP destino**: **Regente**, vía API REST propia — solo para BC.
</arquitectura_y_stack>

<estructura_del_repo>
Repo: `https://github.com/Dreacofred/Sistema-BC` (público, editado por Diego vía web de GitHub, sin entorno local).

```
Sistema-BC/
├── core/
│   ├── __init__.py
│   ├── prompts_ia.py          (prompts de IA; herramienta de Claude para WhatsApp)
│   ├── supabase_client.py     (conexión única a Supabase)
│   ├── cuentas_propias.py     (resuelve banco de destino de una transferencia)
│   ├── regente_client.py      (login/JWT, catálogos, búsquedas read-only)
│   ├── regente_mapeo.py       (agrupa comprobantes de un lote en recibos)
│   └── regente_resolucion.py  (resuelve emisor de un cheque: existente/nuevo/revisión)
├── modulos/
│   ├── clientes.py, resumen.py, proveedores.py, verificacion_bcra.py
├── pages/                     (no explorado)
├── Logo.jpeg
├── app_clientes.py            (no tocado en últimas sesiones)
├── bot.py                     (panel de auditoría — corre dentro de lector.py)
├── lector.py                  (dispatcher a los módulos)
├── requirements.txt
├── utils_bcra.py               (no tocado)
└── webhook.py                 (bot de WhatsApp en producción)
```

**Lectura confiable del repo**: `curl` desde `bash_tool` contra `https://raw.githubusercontent.com/Dreacofred/Sistema-BC/main/<ruta>`, o pedirle a Diego el "Raw". `web_fetch` sobre `github.com/.../blob/...` puede devolver contenido viejo cacheado.
</estructura_del_repo>

<logica_de_negocio_whatsapp_bot>
Sin cambios de fondo respecto a la sesión anterior. Resumen:
- `!bot [Nombre]` abre lote en memoria (`lotes_abiertos`), ya resuelve el cliente (no hace falta CUIT para saber la cuenta corriente).
- `!procesar` dispara `procesar_y_guardar` en un thread.
- Detección de duplicados por hash SHA-256 (`hashes_comprobantes`).
- Llamada a Claude con `tool_choice` forzado a `registrar_cheques_whatsapp` (definida en `core/prompts_ia.py`).
- 4 casos: Cheque Físico, Cheque Electrónico (tabla home banking), Fusión (liquidación + fotos), Transferencia.
- Depósitos en efectivo a recaudadora de petrolera → `id_tipo_pago = 1` ("Efectivo") en Regente, más simple de automatizar (cliente ya identificado).
- Auto-detección de banco de destino en transferencias vía `core/cuentas_propias.py` (`resolver_banco_destino`), comparando por dígitos contra la tabla `cuentas_propias` (7 cuentas reales de BC).
- Auditoría humana obligatoria antes de pasar cualquier cheque a Regente.
</logica_de_negocio_whatsapp_bot>

<integracion_regente_estado_de_avance>

## Acceso y credenciales (sin cambios)
- URL: `https://outshine-extrovert-numeric.ngrok-free.dev` (`/docs` Swagger, `/redoc`).
- Usuario `ia_client`, token `710db05ed587a72ecbc66ce4277d4a2c`. Login vía `POST /api/v1/auth/login` → JWT ~1hs.
- En Swagger, "Authorize" ya agrega "Bearer" solo — pegar solo el token pelado.
- Credenciales limitadas a la base de BC (confirmado, no ven Bonazzola/Buyatti).

## HALLAZGO CRÍTICO — el mecanismo real de escritura (confirmado 03/09 con la guía de Damián)

El mecanismo NO es una serie de POSTs separados a `rgReciboNg`/`rgReciboDetPagosNg`/`rgValorNg`. Es **un solo `PUT` a `/api/v1/rgCajaNg/{id_caja}`**, transaccional (todo o nada), con 4 bloques:

```
PUT /api/v1/rgCajaNg/{id_caja}
{
  "usuario": "...",      // quién firma
  "criterios": [...],    // repetir {id_caja:N} tantas veces como filas tenga "datos"
  "datos": [...],        // datos[0] = {id_caja:N} fila técnica vacía obligatoria; datos[1] = datos reales del recibo
  "detalles": {...}      // "1" = qué se paga, "3" = con qué se paga (los que no se usan, no se mandan)
}
```

**Bloque `detalles."1"`** (qué se paga — cuota puntual, NO lo vamos a usar): una línea por cuota cancelada, identificada por `id_comp`+`orden`+`nro_cuota`, con `id_tipo_pago` SIEMPRE `""` (vacío, para que Regente reparta solo contra el bloque `"3"`).

**Bloque `detalles."3"`** (con qué se paga — SÍ lo vamos a usar): una línea por cada cheque/transferencia/efectivo. `id_valor` siempre 0. Campos según `meta_tipo` (T=cheque terceros, O=transferencia, E=efectivo, etc.) y `pedir_info` (S/N, según tabla de tipos de pago de la instalación).

**Regla de totales**: suma de `monto` del bloque que se use para "qué se paga" (afectado por signo) debe ser EXACTAMENTE igual a la suma de `monto` del bloque `"3"`. Coincide con el `total_declarado`/suma de cheques que el bot ya calcula.

**Campos que NUNCA hay que mandar** (Regente los completa solo): `id_recibo`, `id_cuenta`, `id_tipo_movimiento`, `ult_modif`, `fecha`/`fec_recibo` en el encabezado (bug conocido, se guardan mal). `id_det` e `id_valor` siempre en 0.

**Respuesta**: el número de recibo viene DENTRO de `data.razon` como texto libre `"[ RECIBO NRO: 4321 :]"` — parsear con regex `RECIBO NRO:\s*(\d+)`. Si `ok:false`, el motivo también está en `data.razon`, no en `error`.

**Regente NO valida que la caja esté abierta** al recibir el PUT — si se manda una caja cerrada, graba igual y descuadra el cierre sin avisar. Hay que verificar nosotros mismos antes de mandar (ver endpoint `rgCajaNg/abrir` más abajo, que simplifica esto).

Reintentar tras un error no duplica nada (transacción todo o nada), aunque consume números del secuenciador de valores (saltos en la numeración, es normal).

## NOVEDAD 10/09 — mail de Damián: dos endpoints nuevos en la API

Mail "Regente: Actualización API - BC Combustible" (10/09, 18:34hs), enviado a Diego y Emanuel Feresin (motion-co, otro cliente de Regente con integración propia), cc Pablo Giancarelli. Trae 5 capturas de Swagger con ejemplos reales ya ejecutados. **Ninguno de los dos endpoints resuelve el bloqueante de `detalles."0"`** — son mejoras a otras partes del flujo.

### 1) `GET /api/v1/rgSujetoNg/buscar` — RESUELVE la búsqueda de sujeto por CUIT

Endpoint nuevo, distinto del `GET rgSujetoNg/?q=` viejo (que solo buscaba por descriptor/nombre y no encontraba nada por CUIT). Parámetros:
- `criterio` (string, requerido): acepta `id_sujeto` pelado (ej. `1`), CUIT/doc pelado (ej. `20123456789`), texto descriptor (ej. `Perez`), o prefijos combinables separados por espacio (ej. `S:1 D:27098453`, donde `S:` = id_sujeto y `D:` = doc/CUIT).
- `limite` (integer, opcional): máximo de filas a devolver; `0` = sin límite (ojo: puede exceder el timeout del bridge si trae muchas coincidencias).

Devuelve el **juego completo de campos** por cada coincidencia. Probado en vivo con `criterio=D:30999002478&limite=100`, respuesta real:
```json
{
  "ok": true,
  "data": [
    {
      "id_sujeto": "505407",
      "sujeto": "COLEGIO DE ESCRIBANOS ",
      "direccion": "SAN MARTIN 1920 SANTA FE",
      "localidad": "SANTA FE",
      "cod_postal": "4220",
      "memo": null,
      "estado_cuenta_cli": "N",
      "telefono": "",
      "doc": "30999002478",
      "condicion": "RESPONSABLE INSCRIPTO",
      "id_tipo_doc": "1",
      "afectado": "N",
      "id_cond_cf": "4"
    }
  ],
  "error": null
}
```

**Esto resuelve el Pendiente Activo histórico** de "investigar cómo se busca correctamente un `rgSujetoNg` existente" — ya no hace falta ningún workaround, se busca directo por CUIT con el prefijo `D:`.

**PENDIENTE DE DEFINIR**: no se vio en las capturas cómo se comporta cuando NO hay coincidencias (¿`data: []`, `ok:false`, o algo distinto?) — falta probarlo o preguntarle a Damián antes de programar la lógica de "sujeto no encontrado → dar de alta".

### 2) `POST /api/v1/rgCajaNg/abrir` — simplifica el chequeo de caja abierta

Descripción textual de Damián/Swagger: *"Obtener la caja abierta de un cajero (la crea si no tiene)"*. Es un `POST` (no `GET`) porque tiene efecto: si el cajero no tiene una caja abierta, la inserta; y si el área cierra cajas automáticamente y la caja abierta es de un día anterior, adicionalmente la cierra.

Body de ejemplo:
```json
{
  "usuario": "shoprecong",
  "id_area": 7,
  "ctrl_caja_recien_cerrada": false
}
```

Respuesta real probada:
```json
{
  "ok": true,
  "data": {
    "caja": {
      "id_caja": "1779701",
      "fec_aper": "2026-09-10 15:11:13",
      "descripcion": null,
      "nro_caja": "5297",
      "descr_caja": "2026-09-10 Reconquista Shop shoprecong 5297 abierta 1779701",
      "tipo": "C",
      "id_usuario_caja": "shoprecong"
    },
    "razon": ""
  },
  "error": null
}
```

**Esto reemplaza el plan anterior** de resolver la caja abierta nosotros mismos vía `GET rgCajaNg/?q=%usuario%abierta&limite=0`: ahora hay un endpoint hecho a medida, pensado explícitamente como "paso previo a registrar una cobranza" (palabras de Damián), que devuelve directo el `id_caja` a usar en el `PUT` de escritura — sea que ya exista o haya que abrirla.

**PENDIENTE DE DEFINIR**:
- Qué valor de `id_area` corresponde a cada una de las 4 sucursales de BC (el ejemplo usa `7` para Reconquista, según el `descr_caja` de la respuesta) — falta relevar el catálogo completo de áreas/sucursales.
- Qué significa exactamente `ctrl_caja_recien_cerrada` y cuándo conviene mandar `true` — no hay explicación en la captura, solo el nombre del campo.
- Con qué usuario técnico se va a abrir la caja en el flujo automático (¿un usuario por sucursal, tipo `shoprecong` para Reconquista? ¿o el mismo `ia_client`?) — no confirmado.

### 3) De referencia — cierre de caja (no urgente, el bot no cierra cajas)

`PUT /api/v1/rgCajaNg/{id}` con:
```json
{
  "usuario": "Cajero",
  "criterios": { "id_caja": 374 },
  "datos": { "fec_cierre": "2026-09-10 14:30:00" }
}
```
Dato anotado por completitud; el bot de cobranzas no tiene previsto cerrar cajas, solo abrirlas/usarlas.

## DECISIÓN DE DISEÑO CONFIRMADA — siempre Anticipo

El bot **siempre** va a cargar los pagos como **Anticipo** (nunca afectando una factura/cuota puntual directamente). Es la forma de trabajo real de BC: casi nunca se sabe de antemano qué factura paga el cliente; se cancela desde la más vieja, decisión manual posterior. Esto elimina la necesidad de resolver `id_comp`/`orden`/`nro_cuota` contra `rgComprobanteNg` — el bot nunca hace esa consulta.

**Confirmado con datos reales** (revisando por API el recibo `62464704`, cargado a mano como Anticipo con 2 cheques por $605.000 — ver cheques abajo): un Anticipo escribe así:
- `cajaotros`: una fila con `id_conc="6"`, `concepto="Anticipo Cliente"`, `tipo_conc="otr"`, `monto` = total.
- `recibodetcomp`: una fila con `id_comp="0"`, `nro_cuota="0"`, `nro="Anticipo Cliente"`, `monto` = total.
- `cajapagos` y `cajacuotas` quedan VACÍAS (no afecta ninguna factura).

La guía de Damián menciona el bloque `detalles."0"` ("Pagos a cuenta, sin imputar a una cuota puntual") como el candidato para reproducir esto por API, pero **no detalla sus campos** (a diferencia del bloque `"1"`).

## PENDIENTE ACTIVO #1 (bloqueante para programar) — spec del bloque `detalles."0"`

Mail enviado a Damián el 04/09 con el caso real del recibo `62464704` como referencia, preguntando puntualmente:
- Qué campos lleva la línea de `detalles."0"` (¿va `id_conc=6` fijo, o Regente lo completa solo?).
- Si aplica la misma regla de totales que el bloque `"1"`.

**Respuesta de Damián (04/09, 15:00hs)**: *"Lo vemos y te envío la estructura."* — **todavía sin la spec concreta**. El mail nuevo del 10/09 trajo otras dos mejoras (`rgSujetoNg/buscar`, `rgCajaNg/abrir`) pero **no tocó este punto**. Sigue siendo el bloqueante principal para empezar a programar el `PUT` de escritura del recibo.

## PENDIENTE ACTIVO #2 — confirmado modo "dos pasos"

Damián confirmó (04/09) que la instalación de BC usa el modo de cobranza **"dos pasos"** (el que describe la guía completa) — no hace falta la variante de "un paso". **RESUELTO.**

## PENDIENTE ACTIVO #3 — permiso transferencias/e-checks

Cobrar por transferencia o e-check a una cuenta de la empresa necesita un permiso especial de usuario, aparte del permiso de cajas. Damián respondió (04/09): *"Vemos de asignar los permisos necesarios al usuario."* — EN TRÁMITE, no confirmado que ya esté activo. Verificar antes de la primera prueba con transferencias.

## PENDIENTE ACTIVO #4 (histórico "Investigar búsqueda rgSujetoNg") — RESUELTO 10/09

Ver "Novedad 10/09" arriba: el endpoint `GET rgSujetoNg/buscar` con prefijo `D:` resuelve la búsqueda por CUIT. Queda como sub-pendiente menor confirmar el comportamiento en caso de "sin resultados" (ver PENDIENTE DE DEFINIR en esa sección).

## Otros hallazgos confirmados con datos reales (03/09, dos cheques cargados a mano como Anticipo)

**Cheque 1** — Credicoop, Aserradero Teco SA, N° 91764059, $350.000, `id_valor=478304`:
- `nro_cuenta` guardado = `14730166453` (igual al impreso, sin ceros iniciales — no es útil para el caso de ceros).
- `cod_postal_plaza` guardado = `1702` (Ciudadela) — **no** es la plaza real (1703, José Ingenieros). Ver hallazgo de plaza/localidad abajo.
- `id_titular` nuevo = `251601` ("ACERRADERO TECO S.A.", con errata).
- `id_estado` = `14` = **"Recibido"** (confirmado por Diego viendo la pantalla real) — es el estado fijo de entrada de todo cheque nuevo cargado (sea por pantalla o por API); después puede pasar a Depositado, Entregado a Proveedor, Rechazado, etc. (catálogo de esos estados posteriores no relevado).

**Cheque 2** — Banco de Corrientes, GONZALEZ DAVID, N° 32432231, $255.000, `id_valor=478404`:
- `nro_cuenta` **impreso** = `00822671002` (11 dígitos, con 2 ceros adelante) vs. **guardado** = `822671002` (9 dígitos, sin los ceros). **RESUELTO**: Regente guarda sin ceros a la izquierda — `buscar_cuenta_por_numero` (cuando se implemente) tiene que sacar ceros iniciales de ambos lados antes de comparar, además de separadores.
- `cod_postal_plaza` = `3196` (Esquina, Corrientes) — quedó igual al real, sin necesitar workaround (esa localidad SÍ está en el catálogo de Regente).
- `id_adm` = `94` para Banco de Corrientes (código BCRA real `094`) — mismo patrón de sacar el cero inicial ya visto en Nación/BBVA/Santander.
- `id_titular` nuevo = `503804`.

**PENDIENTE — plaza/localidad**: al cargar un cheque de cuenta/sujeto nuevo, Regente valida `cod_postal_plaza` contra una tabla `localidades` vía FK (`fk_plaza`). Si la plaza real del cheque no está en esa tabla (confirmado con error real: plaza 1703 José Ingenieros no existía), Regente rechaza el guardado. Workaround manual de Diego: usar el código postal de una localidad cercana/conocida que sí esté en el catálogo (en la práctica, no necesariamente la capital de provincia exacta). **PENDIENTE DE DEFINIR** para la integración por API: resolver la plaza contra el catálogo real de `localidades` antes de mandar el dato (investigar si existe `rgLocalidadNg` o similar), o aplicar el mismo tipo de workaround.

## Recibo combinado cheques + efectivo — RESUELTO

Confirmado por Diego probándolo en vivo + explicación de la usuaria `amaidana`: cargar un Anticipo con varias líneas antes de grabar (cheques + efectivo con "Insertar Fila") da el MISMO resultado que hacer dos Anticipos/recibos separados. **Conclusión para el diseño**: no hace falta armar un único recibo combinado — se puede optar por la forma más simple de implementar (ej. un recibo por tipo de pago) sin cambiar el resultado contable.

## Entidades y catálogos confirmados (de sesiones previas, vigentes)

- `id_tipo_pago`: Cheque Físico = **9** fijo. Cheque Electrónico (eCheq) = **66** fijo. Efectivo = **1** fijo. Transferencia = depende del banco de destino (tabla `TRANSFERENCIAS_POR_CODIGO_BCRA` en `core/regente_client.py`, con Nación=27/11, BBVA=52/17, Santander=6/72, Credicoop=60/191, Macro=87/285, Sta Fe=115/330, Bica=76/426). PENDIENTE: Mercado Pago (435) y Mutual Malabrigo (436) sin código BCRA de 3 dígitos.
- `id_condicion` por defecto para sujeto nuevo = **1** ("Responsable Inscripto", confirmado por Damián).
- `id_tipo_doc` = 1 (CUIT) fijo.
- `direccion`/`localidad` en `rgSujetoNg`: NO obligatorios.
- `codigo_sucursal` (bot) = `cod_postal_plaza` (Regente), mismo dato, confirmado.
- Búsqueda de `rgSujetoNg` por CUIT: **RESUELTO 10/09** vía `GET rgSujetoNg/buscar?criterio=D:{cuit}` (ver Novedad 10/09 arriba). El viejo `?q=` seguía sin funcionar por CUIT, solo por descriptor/nombre.
- `rgSujetoCuentaNg` (tabla `sujetos_bancos_cuentas`) permite buscar el sujeto por número de cuenta — mecanismo real que replica la pantalla de Caja.
- Cuando el emisor es 100% nuevo: hacen falta DOS altas, `POST rgSujetoNg` + `POST rgSujetoCuentaNg` (vincular cuenta) — si se omite el segundo paso, el próximo cheque de esa cuenta se trataría otra vez como nuevo.
- ~50% de los cheques recibidos son de emisores/cuentas no registrados en Regente — alta automática de sujetos es caso central.
- **Apertura/resolución de caja**: RESUELTO 10/09 vía `POST rgCajaNg/abrir` (ver Novedad 10/09 arriba) — reemplaza el plan de resolverlo con un GET propio.

### Pendientes activos de la integración (repaso completo, actualizado 10/09)

1. **Bloqueante principal**: spec del bloque `detalles."0"` (Anticipo) — esperando a Damián. Sin novedades en el mail del 10/09.
2. Permiso de transferencias/e-checks — en trámite, verificar antes de primera prueba.
3. Investigar `rgLocalidadNg` o equivalente para resolver `cod_postal_plaza` contra el catálogo real de Regente (o formalizar el workaround).
4. Confirmar significado de estados posteriores a "Recibido" (14) — Depositado, Rechazado, etc. — no urgente.
5. Diseñar el mapeo completo entre `cobranzas_pendientes` y el JSON del `PUT` a `rgCajaNg`, y programar la carga automática — bloqueado hasta el punto 1.
6. **Nuevo (10/09)**: confirmar comportamiento de `rgSujetoNg/buscar` cuando no hay coincidencias (¿`data: []`? ¿`ok:false`?).
7. **Nuevo (10/09)**: relevar el catálogo completo de `id_area` por sucursal para usar en `rgCajaNg/abrir` (solo se confirmó `7` = Reconquista, vía el `descr_caja` de la respuesta de ejemplo).
8. **Nuevo (10/09)**: entender el campo `ctrl_caja_recien_cerrada` de `rgCajaNg/abrir` (cuándo conviene `true` vs `false`) y definir con qué usuario técnico se abre la caja en el flujo automático.

**Regla de seguridad activa, sin cambios**: NO hacer `POST`/`PUT` de prueba a la API real de Regente hasta tener la respuesta del punto 1 y confirmación explícita de Diego — es producción, no hay ambiente de pruebas. Los `GET`/`POST` de lectura o consulta (como `rgSujetoNg/buscar` y `rgCajaNg/abrir`, que ya fueron probados por Damián/Diego) no cuentan como "prueba de escritura de recibo" — pero cualquier llamada nueva que el bot haga en producción se coordina con Diego igual.

### Otra parte del proyecto en curso (chat aparte) — Estado de Cuentas Corrientes

Diego está trabajando en otro chat la funcionalidad de consulta de estado de cuenta corriente de clientes, usando la misma API de Regente (mismas credenciales/Swagger). Punto de partida sugerido: `rgComprobanteNg` (comprobante + cuotas), `rgSujetoNg` (cliente). Falta confirmar el nombre exacto de una entidad de resumen tipo "cuenta corriente"/"saldo" (se vio un campo "Deuda en Cuotas" en la pantalla manual de Caja, sugiere que existe algo así) — pendiente de explorar en Swagger.
</integracion_regente_estado_de_avance>

<aprendizajes_clave>
- **Herramientas para leer el repo**: `curl` desde `bash_tool` contra `raw.githubusercontent.com` es lo más confiable; `web_fetch` sobre `github.com` puede devolver contenido viejo cacheado.
- **Regente — Swagger**: "Authorize" agrega "Bearer" solo — pegar solo el token pelado.
- **Regente — mecanismo de escritura real**: un solo `PUT` a `rgCajaNg/{id_caja}`, no varios POSTs separados. Ver guía completa en la sección de arriba.
- **Anticipo vs. cuota puntual**: son dos formas distintas de cargar un pago en Regente. El bot SIEMPRE va a usar Anticipo — simplifica enormemente el diseño al no requerir resolver cuotas.
- **`nro_cuenta`**: Regente lo guarda SIN ceros a la izquierda, aunque el cheque los tenga impresos — normalizar sacando ceros iniciales además de separadores.
- **`cod_postal_plaza`**: valida contra un catálogo de `localidades` vía FK; si la plaza real no está cargada, Regente rechaza el guardado — hace falta resolver esto antes de escribir por API.
- **`id_estado`**: 14 = "Recibido", el estado fijo de entrada de todo cheque nuevo (por pantalla o por API en el futuro).
- **Recibos combinados (cheques + efectivo)**: un solo Anticipo multi-línea y dos Anticipos separados dan el mismo resultado — libertad de diseño para elegir la implementación más simple.
- **Identificación del cliente vs. librador del cheque**: son cosas distintas. El cliente ya está resuelto por `!bot [Nombre]` de WhatsApp; el CUIT solo hace falta para el librador.
- **`id_tipo_pago` vs. `id_adm`**: conceptos independientes. Tipo de pago fijo para cheques (9/66), banco (`id_adm`) siempre puede variar.
- Digit-only normalization (dígitos, sin separadores ni ceros iniciales) es clave para matchear cuentas/CBU entre lo que extrae la IA y lo guardado en Regente.
- `tool_choice` forzado en la API de Claude sigue siendo mucho más robusto que parsear JSON de texto libre.
- SHA-256 sobre el archivo completo detecta reenvíos idénticos, pero NO detecta una foto nueva del mismo cheque físico (de-duplicación por contenido, no resuelta).
- **Nuevo (10/09) — búsqueda de sujeto por CUIT**: existe un endpoint dedicado `GET rgSujetoNg/buscar?criterio=D:{cuit}`, distinto del viejo `?q=` que solo servía por nombre. Acepta prefijos `S:` (id_sujeto) y `D:` (doc/CUIT), combinables.
- **Nuevo (10/09) — apertura de caja**: existe un endpoint dedicado `POST rgCajaNg/abrir` pensado como paso previo a registrar una cobranza — devuelve la caja abierta del cajero o la crea si no tiene. Reemplaza la idea de resolverlo con un GET propio.
- Regente le manda las mismas actualizaciones de API a distintos clientes con integraciones propias (el mail de Damián iba también a Emanuel Feresin, de motion-co) — señal de que la API es compartida entre instalaciones, no algo hecho a medida solo para BC.
</aprendizajes_clave>

<reglas_de_oro>
1. **Código completo siempre**: nunca fragmentos ni diffs a mano — reemplazo de archivo entero, indicando siempre el nombre del archivo.
2. **Antes de proponer cambios de código, consultar el contexto completo** (este documento + el archivo real del repo si hace falta).
3. **Lo que no esté definido, marcarlo como "PENDIENTE DE DEFINIR"** en vez de asumir o inventar.
4. **Verificar sintaxis de Python** (`ast.parse`) antes de entregar cualquier código, cuando sea posible.
5. **Cambios a `webhook.py` (producción, Render) se tratan con más cautela** que cambios a las apps de Streamlit.
6. **Integraciones con APIs externas (Regente) proceden read-first**: solo GET hasta entender bien el comportamiento de escritura, nunca POST/PUT de prueba en producción sin confirmación explícita de Diego.
7. Diego trabaja mayormente vía el editor web de GitHub, sin entorno de desarrollo local.
8. Diego tiene poca experiencia técnica — explicar en criollo, con pasos chicos y verificables, sin dar por sentado jerga.
9. **Hacer las preguntas de a una por vez** cuando hay varias dudas — Diego prefiere responder con claridad antes de pasar a la siguiente.
</reglas_de_oro>
