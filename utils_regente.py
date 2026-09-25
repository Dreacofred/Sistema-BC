"""
utils_regente.py

Conexión con los endpoints de CUENTA CORRIENTE DE CLIENTES de la API REST de
Regente (nuestro sistema de gestión). Mismo patrón que utils_bcra.py: acá vive
todo lo que es "hablar con la API" (login, renovación de token, consultas y
parseo), y la pantalla vive aparte, en modulos/cuenta_corriente.py.

INTEGRACIÓN DE SOLO LECTURA. Todas las funciones de este archivo son GET. No
hay — ni tiene que haber — nada que escriba o modifique datos en Regente:
Regente es producción y no existe un ambiente de pruebas separado.

Credenciales (st.secrets en Streamlit, o variables de entorno en Render):
    REGENTE_API_URL      -> https://<servidor>            (SIN el /api/v1 final)
    REGENTE_API_USUARIO  -> usuario de integración
    REGENTE_API_TOKEN    -> token de API (NO es el JWT; con esto se pide el JWT)

El login y el cacheo del JWT NO se reimplementan acá: se reusan los de
core/regente_client.py, que ya los tenía resueltos para el bot de cobranzas.
Si hubiera dos cachés de token distintos, la app haría el doble de logins
contra Regente sin necesidad.

Los 4 endpoints que cubre este archivo (instructivo "API REST Regente ·
Cuenta corriente de clientes", v1.0, septiembre 2026 — ref. interna TK-3139):

    GET /rgCompCuotaNg/deuda              -> obtener_deuda()
    GET /rgComprobanteNg/cta_cte          -> obtener_cta_cte()
    GET /rgComprobanteNg/estado_cuenta    -> obtener_estado_cuenta()
    GET /rgComprobanteNg/listado          -> obtener_listado_comprobantes()

Más la búsqueda de clientes (GET /rgSujetoNg), que ya usaba el bot y acá se
reusa para el buscador de la pantalla.

DETALLES DEL FORMATO QUE HAY QUE TENER EN CUENTA (están todos manejados en
los parseadores de la sección 3, pero conviene saberlos):

1. Todas las respuestas vienen envueltas en {"ok": ..., "data": ..., "error": ...}.
   Si "ok" es false, el motivo está en "error" aunque el HTTP sea 200.
2. Los importes, fechas e ids llegan como TEXTO ("38661.0000", "1", "2026-05-27").
   Nunca hay que confiar en que ya vengan como número.
3. En cta_cte, la fila "Saldo Inicial" es la excepción: ahí la fecha llega como
   timestamp Unix en segundos (1767236400) y los importes como números de verdad.
   El resto de las filas trae la fecha como texto YYYY-MM-DD.
4. En deuda, el campo "saldo" es SIEMPRE positivo: el signo lo da "signo_comp"
   (1 = factura/débito, -1 = nota de crédito/anticipo a favor del cliente).
5. El "total" de deuda NO incluye punitorios.
6. El JWT dura 60 minutos. Si algo vuelve 401, se renueva y se reintenta una vez.
7. Las consultas muy grandes mueren a los 30 segundos del lado del servidor.
   Por eso NUNCA usamos limite=0 por defecto: siempre un límite acotado y, en
   los endpoints que lo permiten, un rango de fechas.
"""
import re
import requests

from concurrent.futures import ThreadPoolExecutor

from datetime import date, datetime, timedelta

from core.regente_client import obtener_base_url, obtener_jwt, invalidar_jwt


# El instructivo avisa que el servidor corta las consultas a los 30 segundos.
# Le damos un poco más de aire del lado nuestro para que, cuando eso pase,
# llegue el error real de Regente y no un timeout ciego de requests.
TIMEOUT_CONSULTA = 35

# Límite por defecto de filas. El default de la API también es 100. Ojo:
# limite=0 trae todo, y es justamente lo que hace explotar los 30 segundos.
LIMITE_DEFECTO = 100


class ErrorRegente(Exception):
    """
    Error "esperable" al hablar con Regente (token, permisos, parámetros,
    consulta demasiado grande, túnel caído). Trae un mensaje ya redactado en
    criollo para mostrarle al usuario tal cual con st.error(...), sin tener
    que interpretar el crudo de la API.
    """
    pass


# ==========================================
# 1. LLAMADA HTTP BASE (con renovación de token)
# ==========================================
def _headers(jwt):
    return {
        "Authorization": f"Bearer {jwt}",
        # La API sale por un túnel ngrok gratuito: sin este header, ngrok a
        # veces contesta una pantalla HTML de advertencia en vez del JSON.
        "ngrok-skip-browser-warning": "true",
    }


def _traducir_error_http(respuesta):
    """Convierte un código HTTP de error en un mensaje entendible."""
    codigo = respuesta.status_code
    try:
        detalle = respuesta.json().get("detail", "")
    except Exception:
        detalle = (respuesta.text or "")[:200]

    if codigo == 403:
        return (
            "Regente rechazó la consulta por permisos (403). El usuario de "
            "integración necesita los permisos 112, 144, 221, 691, 879 y 984. "
            "También da 403 si venció la contraseña de ese usuario en Regente. "
            f"Detalle: {detalle}"
        )
    if codigo == 422:
        return f"Regente rechazó un parámetro de la consulta (422). Detalle: {detalle}"
    if codigo == 500:
        return (
            "Regente cortó la consulta (500). Suele ser porque se superó el "
            "tiempo máximo de 30 segundos: achicá el rango de fechas o bajá el "
            f"límite de filas. Detalle: {detalle}"
        )
    return f"Regente respondió HTTP {codigo}. Detalle: {detalle}"


def _get(ruta, params=None):
    """
    Hace un GET a un endpoint de Regente y devuelve el contenido de "data"
    ya desenvuelto.

    Si el token venció (401), pide uno nuevo y reintenta UNA sola vez — no
    más, para no quedar en un bucle de logins si el problema es otro.

    Levanta ErrorRegente con un mensaje listo para mostrar si algo sale mal.
    """
    try:
        base_url = obtener_base_url()
    except RuntimeError as e:
        # Faltan las credenciales en st.secrets / variables de entorno.
        raise ErrorRegente(str(e))

    url = f"{base_url}/api/v1{ruta}"

    for intento in (1, 2):
        try:
            respuesta = requests.get(
                url,
                params=params or {},
                headers=_headers(obtener_jwt(forzar_renovacion=(intento == 2))),
                timeout=TIMEOUT_CONSULTA,
            )
        except requests.exceptions.Timeout:
            raise ErrorRegente(
                "Regente no contestó a tiempo (más de "
                f"{TIMEOUT_CONSULTA} segundos). Probá con un rango de fechas "
                "más corto o menos filas."
            )
        except requests.exceptions.RequestException as e:
            raise ErrorRegente(
                "No se pudo llegar al servidor de Regente. Acordate de que la "
                "URL es un túnel ngrok y puede cambiar o estar caído. "
                f"Detalle: {e}"
            )

        if respuesta.status_code == 401 and intento == 1:
            # Token vencido: lo tiramos y en la vuelta siguiente se pide uno nuevo.
            invalidar_jwt()
            continue

        if respuesta.status_code != 200:
            raise ErrorRegente(_traducir_error_http(respuesta))

        try:
            cuerpo = respuesta.json()
        except ValueError:
            raise ErrorRegente(
                "Regente devolvió algo que no es JSON. Si empieza con HTML, lo "
                "más probable es que esté contestando el túnel ngrok y no la API."
            )

        if not cuerpo.get("ok", False):
            raise ErrorRegente(f"Regente no pudo resolver la consulta: {cuerpo.get('error')}")

        return cuerpo.get("data")

    raise ErrorRegente("El token de Regente sigue siendo rechazado (401) después de renovarlo.")


# ==========================================
# 2. PARSEADORES DE TIPOS
# ==========================================
# Nota sobre los importes: los convertimos a float, no a Decimal. Son pesos con
# dos decimales que solo mostramos y sumamos para totales de pantalla, y float
# se lleva mucho mejor con pandas y st.metric. Si algún día hay que hacer
# cálculos contables finos con estos números, convendría pasar a Decimal.
def _a_float(valor, defecto=0.0):
    """Convierte a float los importes que Regente manda como texto ("38661.0000")."""
    if valor is None or valor == "":
        return defecto
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return defecto


def _a_int(valor, defecto=None):
    """Convierte a int los ids y contadores que llegan como texto ("1365")."""
    if valor is None or valor == "":
        return defecto
    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return defecto


def _a_fecha(valor):
    """
    Devuelve un datetime.date, o None si no se puede interpretar.

    Contempla los tres formatos que aparecen en las respuestas:
      - "2026-05-27"            (la mayoría)
      - "2026-05-27 13:52:20"   (fvenc en deuda, fecha en listado)
      - 1767236400              (timestamp Unix: SOLO la fila "Saldo Inicial"
                                 de cta_cte, ver nota 3 del encabezado)
    """
    fecha_hora = _a_datetime(valor)
    return fecha_hora.date() if fecha_hora else None


def _a_datetime(valor):
    """Igual que _a_fecha pero conservando la hora cuando viene."""
    if valor is None or valor == "":
        return None

    # Caso timestamp Unix (número, o texto que son todos dígitos).
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        try:
            return datetime.fromtimestamp(valor)
        except (OverflowError, OSError, ValueError):
            return None

    texto = str(valor).strip()
    if texto.isdigit():
        try:
            return datetime.fromtimestamp(int(texto))
        except (OverflowError, OSError, ValueError):
            return None

    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def _formato_fecha_param(valor):
    """Las fechas de los parámetros se mandan siempre como YYYY-MM-DD."""
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")
    return str(valor)


# ==========================================
# 3. ENDPOINT 1: DEUDA PENDIENTE
# ==========================================
def _parsear_fila_deuda(fila, origen):
    """
    Normaliza una fila de deuda (venga del grupo "contado" o del grupo
    "cuotas") a un diccionario con tipos de Python y siempre las mismas
    claves, para poder mostrar los dos grupos en una sola tabla.

    OJO con el signo: "saldo" siempre viene positivo, incluso en las notas de
    crédito. El que decide si la fila suma o resta es "signo_comp" (1 o -1).
    Por eso agregamos "saldo_con_signo", que es el que hay que sumar.
    """
    signo = _a_int(fila.get("signo_comp"), 1) or 1
    saldo = _a_float(fila.get("saldo"))

    return {
        "origen": origen,  # "contado" o "cuotas"
        "id_comp": _a_int(fila.get("id_comp")),
        "nro": fila.get("nro") or "",
        # En el grupo "cuotas" la fecha del comprobante viene en "fcomp";
        # en "contado" viene en "fecha".
        "fecha_comp": _a_fecha(fila.get("fcomp") or fila.get("fecha")),
        "tipo_pago": fila.get("tipo_pago") or "",
        "plan": fila.get("planf") or "",
        "nro_cuota": _a_int(fila.get("nro_cuota")),
        "cant_cuotas": _a_int(fila.get("cant_cuotas")),
        "fvenc": _a_fecha(fila.get("fvenc")),
        "atraso": _a_int(fila.get("atraso"), 0) or 0,
        "monto": _a_float(fila.get("monto")),
        "saldo": saldo,
        "signo": signo,
        "saldo_con_signo": saldo * signo,
        "punitorio": _a_float(fila.get("punitorio")),
    }


def obtener_deuda(id_sujeto, toda_la_deuda=True):
    """
    GET /rgCompCuotaNg/deuda — lo que el cliente debe HOY, importe por importe.
    Solo trae lo pendiente; lo ya pagado no aparece (para eso está cta_cte).

    toda_la_deuda=True  -> todas las cuotas pendientes, vencidas o no.
    toda_la_deuda=False -> solo las vencidas.

    Devuelve:
    {
        "contado": [fila, ...],     # comprobantes sin plan de cuotas
        "cuotas":  [fila, ...],     # una fila por cuota, con su vencimiento
        "filas":   [ ... ],         # los dos grupos juntos, ordenados por vencimiento
        "total": float,             # neto adeudado, SIN punitorios (lo da la API)
        "total_punitorios": float,  # suma de los punitorios de todas las filas
    }
    """
    data = _get(
        "/rgCompCuotaNg/deuda",
        {"id_sujeto": id_sujeto, "toda_la_deuda": str(bool(toda_la_deuda)).lower()},
    ) or {}

    contado = [_parsear_fila_deuda(f, "contado") for f in (data.get("contado") or [])]
    cuotas = [_parsear_fila_deuda(f, "cuotas") for f in (data.get("cuotas") or [])]
    filas = contado + cuotas
    # Las filas sin vencimiento van al final, no adelante.
    filas.sort(key=lambda f: (f["fvenc"] is None, f["fvenc"] or date.max))

    return {
        "contado": contado,
        "cuotas": cuotas,
        "filas": filas,
        "total": _a_float(data.get("total")),
        "total_punitorios": sum(f["punitorio"] for f in filas),
    }


# ==========================================
# 4. ENDPOINT 2: PAGOS Y MOVIMIENTOS (CTA. CTE.)
# ==========================================
def obtener_cta_cte(id_sujeto, fecha_desde, fecha_hasta, limite=LIMITE_DEFECTO):
    """
    GET /rgComprobanteNg/cta_cte — los movimientos del período: cada
    comprobante (debe) seguido de los pagos que lo cancelaron (haber), con el
    saldo acumulado.

    La PRIMERA fila es siempre el saldo inicial (el resumen de todo lo
    anterior a fecha_desde) y es la única que trae la fecha como timestamp
    Unix y los importes como números. Queda marcada con "es_saldo_inicial".

    fecha_desde y fecha_hasta son obligatorias (acepta date o texto YYYY-MM-DD).
    limite: máximo de filas. NO usamos 0 (= sin límite) para no comernos el
    corte de 30 segundos del servidor.
    """
    data = _get(
        "/rgComprobanteNg/cta_cte",
        {
            "id_sujeto": id_sujeto,
            "fecha_desde": _formato_fecha_param(fecha_desde),
            "fecha_hasta": _formato_fecha_param(fecha_hasta),
            "limite": int(limite),
        },
    ) or {}

    filas = []
    for fila in (data.get("ctacte") or []):
        es_saldo_inicial = str(fila.get("nro", "")).strip().lower() == "saldo inicial"
        filas.append({
            "es_saldo_inicial": es_saldo_inicial,
            "id_comp": _a_int(fila.get("id_comp")),
            "tc": fila.get("tc") or "",
            # "nro" solo viene en la fila del comprobante; en las filas de
            # pago llega vacío (la fila pertenece al comprobante de arriba).
            "nro": fila.get("nro") or "",
            "fecha": _a_fecha(fila.get("fecha")),
            "id_recibo": _a_int(fila.get("id_recibo"), 0) or 0,
            "nro_recibo": fila.get("nro_rec") or "",
            "id_caja": _a_int(fila.get("id_caja"), 0) or 0,
            "tipo_pago": fila.get("tipo_pago") or "",
            "nro_cuota": _a_int(fila.get("nro_cuota")),
            "atraso": _a_int(fila.get("atraso"), 0) or 0,
            "debe": _a_float(fila.get("debe")),
            "haber": _a_float(fila.get("haber")),
            "saldo": _a_float(fila.get("saldo")),
        })
    return filas


# ==========================================
# 5. ENDPOINT 3: RESUMEN DE ESTADO DE CUENTA
# ==========================================
def obtener_estado_cuenta(id_sujeto, toda_la_deuda=True, fecha_desde=None,
                          fecha_hasta=None, id_area=0, limite=LIMITE_DEFECTO):
    """
    GET /rgComprobanteNg/estado_cuenta — la situación del cliente en una sola
    fila: saldo inicial, debe, haber, saldo final, punitorios y atraso.

    Devuelve un diccionario con esa fila, o None si el cliente no tiene saldo
    (en ese caso la API contesta la lista vacía, no un error).

    OJO con id_area: 0 = todas las sucursales, y eso requiere el permiso 879.
    Si el usuario de integración no lo tuviera, la respuesta puede venir vacía
    aunque el cliente sí tenga deuda en otra sucursal.

    Probado el 25/09/2026 con el cliente 2824: con id_area=0 devuelve el estado
    de cuenta completo, y filtrando por sucursal suelta devuelve VACÍO en tres
    de las cuatro (solo la 2 trae datos). O sea que pasar un id_area concreto
    puede esconder deuda real del cliente en otras sucursales. Si algún día se
    agrega un filtro por sucursal a la pantalla, tenerlo muy presente.
    """
    params = {
        "id_sujeto": id_sujeto,
        "toda_la_deuda": str(bool(toda_la_deuda)).lower(),
        "id_area": int(id_area),
        "limite": int(limite),
    }
    if fecha_desde:
        params["fecha_desde"] = _formato_fecha_param(fecha_desde)
    if fecha_hasta:
        params["fecha_hasta"] = _formato_fecha_param(fecha_hasta)

    data = _get("/rgComprobanteNg/estado_cuenta", params) or {}
    ventas = data.get("ventas") or []
    if not ventas:
        return None

    fila = ventas[0]
    # lstcompdeuda viene como texto con los id_comp separados por coma.
    lista_comp = [
        _a_int(x) for x in str(fila.get("lstcompdeuda") or "").split(",") if x.strip()
    ]

    return {
        "id_sujeto": _a_int(fila.get("id_sujeto")),
        "sujeto": fila.get("sujeto") or "",
        "estado_cuenta_cli": fila.get("estado_cuenta_cli") or "",
        "direccion": fila.get("direccion") or "",
        "localidad": fila.get("localidad") or "",
        "cod_postal": fila.get("cod_postal") or "",
        "telefono": fila.get("telefono") or "",
        "saldo_inicial": _a_float(fila.get("saldoini")),
        "debe": _a_float(fila.get("debe")),
        "haber": _a_float(fila.get("haber")),
        "saldo_final": _a_float(fila.get("saldofinal")),
        "punitorios": _a_float(fila.get("punitorios")),
        "saldo_con_punitorios": _a_float(fila.get("saldoincluyepunit")),
        # "dias" puede venir en null cuando no hay nada vencido todavía.
        "dias_atraso": _a_int(fila.get("dias"), 0) or 0,
        "peor_fecha": _a_fecha(fila.get("peor_fecha")),      # vencimiento impago más viejo
        "fecha_ultimo_movimiento": _a_fecha(fila.get("fum")),
        "fecha_ultimo_recibo": _a_fecha(fila.get("fup")),
        "comprobantes_en_deuda": lista_comp,
        "observaciones": fila.get("obse") or "",
    }


# ==========================================
# 6. ENDPOINT 4: LISTADO DE COMPROBANTES
# ==========================================
ESTADOS_COMPROBANTE = ("todos", "pendientes", "pagados")


def obtener_listado_comprobantes(id_sujeto, fecha_desde, fecha_hasta,
                                 estado="todos", solo_venta=False, id_area=0,
                                 limite=LIMITE_DEFECTO):
    """
    GET /rgComprobanteNg/listado — los comprobantes emitidos al cliente en un
    período (solo los ya impresos/emitidos definitivamente).

    estado: "todos" | "pendientes" (con deuda) | "pagados" (cancelados).
    El campo "deuda" de cada fila SOLO viene con estado="pendientes".
    """
    if estado not in ESTADOS_COMPROBANTE:
        raise ValueError(f"estado tiene que ser uno de {ESTADOS_COMPROBANTE}")

    data = _get(
        "/rgComprobanteNg/listado",
        {
            "id_sujeto": id_sujeto,
            "fecha_desde": _formato_fecha_param(fecha_desde),
            "fecha_hasta": _formato_fecha_param(fecha_hasta),
            "estado": estado,
            "solo_venta": str(bool(solo_venta)).lower(),
            "id_area": int(id_area),
            "limite": int(limite),
        },
    ) or {}

    comprobantes = []
    for fila in (data.get("listado") or []):
        signo = _a_int(fila.get("signo_comp"), 1) or 1
        imp_total = _a_float(fila.get("imp_total"))
        comprobantes.append({
            "id_comp": _a_int(fila.get("id_comp")),
            "tc": fila.get("tc") or "",
            "tipo_comp": fila.get("tipo_comp") or "",
            "nro": fila.get("nro") or "",
            "fecha": _a_datetime(fila.get("fecha")),
            "signo": signo,
            "id_cliente": _a_int(fila.get("id_cliente")),
            "cliente": fila.get("cliente") or "",
            "doc": fila.get("doc") or "",
            "id_area": _a_int(fila.get("id_area")),
            "id_vendedor": fila.get("id_vendedor") or "",
            "neto": _a_float(fila.get("neto")),
            "imp_total": imp_total,
            "imp_total_con_signo": imp_total * signo,
            "deuda": _a_float(fila.get("deuda")),  # 0 si no se pidió estado=pendientes
        })
    return comprobantes


# ==========================================
# 7. BÚSQUEDA DE CLIENTES
# ==========================================
def _extraer_cuit(texto):
    """
    Saca el CUIT del campo "detalle_adic" de rgSujetoNg, que viene con el
    domicilio, la localidad, el teléfono y el CUIT todo concatenado en un
    solo texto (ej: "RUTA 11 Y JORGE NEME 3040 SAN JUSTO  CUIT 30547794482").
    """
    if not texto:
        return ""
    coincidencia = re.search(r"CUIT\s*(\d{6,})", str(texto))
    return coincidencia.group(1) if coincidencia else ""


def buscar_clientes_por_nombre(texto, limite=50):
    """
    GET /rgSujetoNg — busca clientes por razón social / nombre.

    Regente busca por "contiene" cuando el texto arranca con %, que es como lo
    mandamos. Devuelve una lista de {id_sujeto, sujeto, cuit, detalle}.
    """
    texto = str(texto or "").strip()
    if not texto:
        return []

    data = _get("/rgSujetoNg", {"q": f"%{texto}", "limite": int(limite)}) or []
    # Este endpoint devuelve la lista directamente en "data" (no un objeto).
    if isinstance(data, dict):
        data = data.get("data") or []

    clientes = []
    for fila in data:
        detalle = fila.get("detalle_adic") or fila.get("?column?") or ""
        clientes.append({
            "id_sujeto": _a_int(fila.get("id_sujeto")),
            "sujeto": fila.get("sujeto") or "",
            "cuit": _extraer_cuit(detalle),
            "detalle": " ".join(str(detalle).split()),
        })
    return clientes


def buscar_cliente_por_cuit(cuit, supabase=None):
    """
    Busca un cliente por CUIT.

    LIMITACIÓN CONFIRMADA DE LA API (28/08/2026, y vuelta a verificar en
    septiembre 2026): el parámetro "q" de rgSujetoNg busca SOLO por el nombre
    del sujeto, no por CUIT. Regente lo tiene agendado para una versión
    futura. Mientras tanto, este buscador resuelve el CUIT contra la tabla
    "clientes" de Supabase, que guarda el id_sujeto_regente de los clientes
    dados de alta en nuestro sistema.

    Devuelve una lista de {id_sujeto, sujeto, cuit, detalle} (vacía si no lo
    encuentra). Si el cliente existe en Regente pero no está en Supabase, la
    lista va a venir vacía: en ese caso hay que buscarlo por razón social.
    """
    cuit_limpio = "".join(c for c in str(cuit or "") if c.isdigit())
    if not cuit_limpio or supabase is None:
        return []

    try:
        res = (
            supabase.table("clientes")
            .select("nombre, cuit, id_sujeto_regente")
            .eq("cuit", cuit_limpio)
            .execute()
        )
    except Exception as e:
        raise ErrorRegente(f"No se pudo consultar la tabla de clientes en Supabase: {e}")

    encontrados = []
    for fila in (res.data or []):
        id_sujeto = _a_int(fila.get("id_sujeto_regente"))
        if id_sujeto:
            encontrados.append({
                "id_sujeto": id_sujeto,
                "sujeto": fila.get("nombre") or "",
                "cuit": fila.get("cuit") or cuit_limpio,
                "detalle": "Resuelto desde la tabla de clientes de Supabase",
            })
    return encontrados


# ==========================================
# 8. QUIÉN PAGA LA CUENTA (ENTIDADES PAGADORAS)
# ==========================================
# Una "entidad pagadora" es un cliente que manda a cargar combustible a otras
# personas o empresas: las cargas se facturan a nombre de esos terceros, pero
# las paga ella. Si no se sabe, se le reclama al que no debe pagar.
#
# CÓMO SE REGISTRA EN REGENTE (verificado el 25/09/2026): NO está en la ficha
# del cliente. La tabla sujetos_relacion tiene un tipo "Pagadora" (id_rel = 5),
# pero en los casos reales que miramos está vacía. El vínculo real vive en
# CADA COMPROBANTE, en su subtabla "compgarantes": la factura del cliente 4181
# (PICONE MARIANO LUIS) tiene como garante al 1058 (RUIZ MARCELO HUGO), y eso
# es lo que la caja de Regente muestra entre paréntesis al lado del nombre.
#
# OJO CON EL COSTO: hay que pedir el comprobante entero, uno por uno. Por eso
# se consultan solo unos pocos y en paralelo — ver obtener_pagadores_de_deuda.
def obtener_garantes(id_comp):
    """
    Los garantes de un comprobante: quién responde por esa factura además del
    cliente facturado. Devuelve [{"id_sujeto", "nombre", "doc"}, ...], vacío si
    no tiene.
    """
    data = _get(f"/rgComprobanteNg/{id_comp}") or {}
    bloque = data.get("compgarantes") or {}
    return [
        {
            "id_sujeto": _a_int(g.get("id_sujeto")),
            "nombre": g.get("sujeto") or "",
            "doc": g.get("doc") or "",
        }
        for g in (bloque.get("data") or [])
        if g.get("id_sujeto")
    ]


def obtener_pagadores_de_deuda(deuda, max_comprobantes=3, max_hilos=3):
    """
    Mira los primeros comprobantes pendientes de un cliente y devuelve quiénes
    figuran como garantes, o sea quién paga esa cuenta. Lista sin repetidos.

    Es una MUESTRA, no un relevamiento completo: consultar los garantes de cada
    comprobante cuesta una consulta por comprobante, y un cliente puede tener
    decenas. Con tres alcanza para detectar el caso, porque cuando hay una
    entidad pagadora suele ser la misma en todos. Los tres van en paralelo, así
    que el costo es el de una sola consulta.
    """
    filas = (deuda or {}).get("filas") or []
    ids = []
    for f in filas:
        if f.get("id_comp") and f["id_comp"] not in ids:
            ids.append(f["id_comp"])
        if len(ids) >= max_comprobantes:
            break
    if not ids:
        return []

    with ThreadPoolExecutor(max_workers=max_hilos) as ejecutor:
        resultados = list(ejecutor.map(obtener_garantes, ids))

    pagadores, vistos = [], set()
    for lista in resultados:
        for g in lista:
            if g["id_sujeto"] not in vistos:
                vistos.add(g["id_sujeto"])
                pagadores.append(g)
    return pagadores


# ==========================================
# 9. AYUDAS PARA LA PANTALLA
# ==========================================
def rango_de_fechas_por_defecto(meses_atras=6):
    """
    Rango de fechas razonable para las consultas que lo exigen (cta_cte y
    listado): los últimos N meses hasta hoy. Acotar el período es la principal
    defensa contra el corte de 30 segundos del servidor.
    """
    hasta = date.today()
    desde = hasta - timedelta(days=30 * meses_atras)
    return desde, hasta


def es_anticipo(nro_comprobante):
    """
    Dice si un comprobante de la deuda es un ANTICIPO, o sea un pago que ya
    hizo el cliente y todavía no se aplicó a una factura.

    Cómo se reconoce: en el detalle de deuda, el campo "nro" viene con el tipo
    de comprobante pegado adelante, antes de la letra y el punto de venta:

        FA-00023-00045113    -> tipo "F"   (Factura)
        NDA-00025-00000625   -> tipo "ND"  (Nota de Débito)
        NDIA-00000-00000000  -> tipo "NDI" (Nota de Débito Interna)
        NCA-...              -> tipo "NC"  (Nota de Crédito)
        AnA-00000-00000000   -> tipo "An"  (Anticipo)   <-- este

    Hace falta mirar el número porque "signo_comp" no alcanza: los anticipos y
    las notas de crédito vienen los dos con signo -1, y no son lo mismo. Un
    anticipo es plata que el cliente ya pagó; una nota de crédito es un ajuste.
    """
    return bool(re.match(r"^An[A-Z]-", str(nro_comprobante or "").strip()))


def formatear_pesos(valor):
    """Formatea un importe como $ 1.234.567,89 (formato argentino)."""
    try:
        texto = f"{float(valor):,.2f}"
    except (TypeError, ValueError):
        return "$ 0,00"
    # En Python el separador de miles es "," y el decimal "."; acá los damos vuelta.
    texto = texto.replace(",", "@").replace(".", ",").replace("@", ".")
    return f"$ {texto}"
