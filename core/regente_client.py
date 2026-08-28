"""
core/regente_client.py

Módulo de conexión con la API REST de Regente (el ERP de BC Combustibles).

IMPORTANTE — alcance de este archivo (Etapa 1 del plan):
Este módulo, por ahora, SOLO sabe loguearse y hacer consultas de lectura (GET).
NO tiene ninguna función que mande datos (POST) a Regente todavía. Eso se va a
agregar en una etapa posterior, una vez que este módulo esté probado y Diego
haya dado el OK explícito para avanzar.

Regla de oro de este proyecto: NUNCA se hace un POST de prueba contra la API
real de Regente sin el OK explícito de Diego, porque es producción y no hay
ambiente de pruebas separado.

Dónde se usan las credenciales:
Este módulo puede correr tanto en Streamlit (bot.py, lector.py — que usan
`st.secrets`) como en Flask (webhook.py, en Render — que usa variables de
entorno del sistema). Por eso, `_obtener_credenciales()` prueba primero con
variables de entorno, y si no las encuentra, intenta con `st.secrets` como
respaldo.

Variables/secretos necesarios (mismo nombre en ambos lados):
- REGENTE_API_URL       -> ej: "https://outshine-extrovert-numeric.ngrok-free.dev"
  (OJO: esta URL es un túnel ngrok y puede cambiar con el tiempo — si algún día
  las consultas empiezan a fallar todas, lo primero a revisar es si Damián
  avisó una URL nueva)
- REGENTE_API_USUARIO   -> ej: "ia_client"
- REGENTE_API_TOKEN     -> el token fijo que dio Damián para el login (OJO: no
  es el JWT — el JWT se pide dinámicamente con este token, y expira solo)
"""
import os
import time
import requests


# ==========================================
# 1. CREDENCIALES Y CONFIGURACIÓN
# ==========================================
def _obtener_credenciales():
    """
    Devuelve (base_url, usuario, token) leyendo primero de variables de
    entorno (Render/Flask) y, si falta alguna, de st.secrets (Streamlit).
    Lanza un error claro si no encuentra alguna en ningún lado.
    """
    base_url = os.environ.get("REGENTE_API_URL")
    usuario = os.environ.get("REGENTE_API_USUARIO")
    token = os.environ.get("REGENTE_API_TOKEN")

    if not (base_url and usuario and token):
        try:
            import streamlit as st
            base_url = base_url or st.secrets.get("REGENTE_API_URL")
            usuario = usuario or st.secrets.get("REGENTE_API_USUARIO")
            token = token or st.secrets.get("REGENTE_API_TOKEN")
        except Exception:
            pass

    faltantes = [
        nombre for nombre, valor in [
            ("REGENTE_API_URL", base_url),
            ("REGENTE_API_USUARIO", usuario),
            ("REGENTE_API_TOKEN", token),
        ] if not valor
    ]
    if faltantes:
        raise RuntimeError(
            "Faltan credenciales de Regente: " + ", ".join(faltantes) +
            ". Hay que cargarlas como variable de entorno (Render) o como "
            "secreto de Streamlit (st.secrets), según dónde corra este código."
        )

    return base_url.rstrip("/"), usuario, token


# ==========================================
# 2. LOGIN Y CACHE DEL TOKEN (JWT)
# ==========================================
# El JWT que devuelve Regente expira aproximadamente a la hora. Lo guardamos
# en memoria (variables a nivel de módulo) para no pedir uno nuevo en cada
# consulta — solo se renueva cuando falta poco para que venza.
_token_cache = {"jwt": None, "vence_en": 0}


def _obtener_jwt():
    """
    Devuelve un JWT válido, pidiendo uno nuevo si no hay uno en memoria o si
    el que hay está por vencer (con 5 minutos de margen de seguridad).
    """
    ahora = time.time()
    if _token_cache["jwt"] and ahora < _token_cache["vence_en"] - 300:
        return _token_cache["jwt"]

    base_url, usuario, token = _obtener_credenciales()

    respuesta = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"usuario": usuario, "token": token},
        timeout=15,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()
    jwt = datos.get("access_token")
    if not jwt:
        raise RuntimeError(
            "Regente no devolvió un access_token al loguearse. "
            f"Respuesta cruda: {datos}"
        )

    # Asumimos que dura ~1 hora, como confirmó Damián. Guardamos con margen.
    _token_cache["jwt"] = jwt
    _token_cache["vence_en"] = ahora + 55 * 60
    return jwt


def _headers():
    return {"Authorization": f"Bearer {_obtener_jwt()}"}


# ==========================================
# 3. CONSULTAS DE LECTURA (GET) — sin ningún riesgo
# ==========================================
def buscar_sujeto_por_cuit(cuit: str):
    """
    Intenta buscar un sujeto en Regente por CUIT.

    OJO — LIMITACIÓN CONFIRMADA (28/08/2026): Damián probó esto de su lado y
    confirmó que el parámetro "q" de este endpoint SOLO busca por el
    descriptor/nombre del sujeto, no por CUIT. Está agendado para agregarse
    en una futura versión de la API, pero hoy esta función NO va a encontrar
    nada buscando por CUIT. Se deja implementada (con el formato de
    respuesta ya corregido) para cuando esa mejora esté disponible — hasta
    entonces, usar `buscar_cuenta_por_numero` y `buscar_sujetos_por_apellido`
    (más abajo) para resolver el emisor.
    """
    base_url, _, _ = _obtener_credenciales()
    cuit_limpio = "".join(c for c in str(cuit) if c.isdigit())

    respuesta = requests.get(
        f"{base_url}/api/v1/rgSujetoNg",
        params={"q": cuit_limpio, "limite": 0},
        headers=_headers(),
        timeout=15,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()
    resultados = datos.get("data") or []
    return resultados[0] if resultados else None


def buscar_cuenta_por_numero(numero_cuenta: str, id_adm_esperado=None):
    """
    Busca en rgSujetoCuentaNg (tabla sujetos_bancos_cuentas de Regente) por
    número de cuenta bancaria. CONFIRMADO Y PROBADO el 28/08/2026 en Swagger
    contra un caso real (cuenta 1234/5 -> id_sujeto 2158).

    Regente busca por "contiene" (con % adelante), así que acá filtramos
    nosotros mismos por coincidencia EXACTA del número de cuenta (y, si se
    pasa, también del banco) para evitar falsos positivos de ese "contiene".

    Devuelve una lista (puede tener 0, 1, o más de 1 resultado — lo normal
    es 0 o 1; más de 1 sería un caso raro a revisar a mano).
    """
    base_url, _, _ = _obtener_credenciales()
    cuenta_limpia = str(numero_cuenta or "").strip()
    if not cuenta_limpia:
        return []

    respuesta = requests.get(
        f"{base_url}/api/v1/rgSujetoCuentaNg",
        params={"q": f"%{cuenta_limpia}", "limite": 0},
        headers=_headers(),
        timeout=15,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()
    resultados = datos.get("data") or []

    exactos = [r for r in resultados if str(r.get("cuenta", "")).strip() == cuenta_limpia]
    if id_adm_esperado is not None:
        exactos = [r for r in exactos if str(r.get("id_adm")) == str(id_adm_esperado)]
    return exactos


def buscar_sujetos_por_apellido(apellido: str):
    """
    Busca en rgSujetoNg por apellido/nombre (búsqueda por "contiene", con %).
    CONFIRMADO Y PROBADO el 26/08/2026 (caso real: %FOCHESATTO -> 2 resultados).

    Devuelve la lista cruda de resultados tal cual los da Regente. Cada
    resultado trae, además de "id_sujeto" y "sujeto" (nombre), un campo sin
    nombre propio (aparece como "?column?" en la respuesta) con el domicilio,
    la localidad y el CUIT todos concatenados en un solo texto — hay que
    parsearlo para sacar el CUIT (ver core/regente_resolucion.py).
    """
    base_url, _, _ = _obtener_credenciales()
    texto = str(apellido or "").strip()
    if not texto:
        return []

    respuesta = requests.get(
        f"{base_url}/api/v1/rgSujetoNg",
        params={"q": f"%{texto}", "limite": 0},
        headers=_headers(),
        timeout=15,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()
    return datos.get("data") or []


# ==========================================
# 4. CATÁLOGOS Y VALORES FIJOS YA CONFIRMADOS CON DAMIÁN
# ==========================================
# Estos valores salen de las respuestas de Damián (21/08 y 26/08) y de mirar
# la pantalla real de Regente. No son un invento nuestro.

# rgSujetoNg — al dar de alta un emisor de cheque nuevo:
ID_CONDICION_RESPONSABLE_INSCRIPTO = 1   # Default que usa la pantalla manual
ID_TIPO_DOC_CUIT = 1                      # El bot siempre tiene el CUIT del emisor

# rgValorNg — estado de un cheque recién cargado:
ID_ESTADO_DISPONIBLE = 1

# rgValorNg — tipo de pago para cheques físicos y electrónicos (genéricos,
# no dependen del banco — el banco va aparte, en id_adm):
ID_TIPO_PAGO_CHEQUE_FISICO = 9
ID_TIPO_PAGO_CHEQUE_ELECTRONICO = 66
ID_TIPO_PAGO_EFECTIVO = 1

# rgValorNg — tipo de pago para transferencias, según el banco de DESTINO
# (la cuenta de BC Combustibles a la que entró la plata). Clave = código
# BCRA de 3 dígitos, tal como lo extrae hoy el bot en "codigo_banco".
# Fuente: tipos_pago.csv, mandado por Damián el 26/08/2026.
TRANSFERENCIAS_POR_CODIGO_BCRA = {
    "011": {"id_tipo_pago": 27, "id_adm": 11, "administradora": "Banco Nacion"},
    "017": {"id_tipo_pago": 52, "id_adm": 17, "administradora": "BBVA Banco Frances"},
    "072": {"id_tipo_pago": 6, "id_adm": 72, "administradora": "Banco Santander Rio s.a."},
    "191": {"id_tipo_pago": 60, "id_adm": 191, "administradora": "Banco Credicoop"},
    "285": {"id_tipo_pago": 87, "id_adm": 285, "administradora": "Banco Macro s.a."},
    "330": {"id_tipo_pago": 115, "id_adm": 330, "administradora": "Nuevo Banco de Sta Fe"},
    "426": {"id_tipo_pago": 76, "id_adm": 426, "administradora": "Banco Bica"},
    # PENDIENTE DE DEFINIR: Mercado Pago (id_adm=435) y Mutual Malabrigo
    # (id_adm=436) no tienen un código BCRA de 3 dígitos tradicional (no son
    # bancos). Si en algún momento llega una transferencia por Mercado Pago,
    # hay que resolver este caso aparte — no encaja en este diccionario tal
    # como está armado.
}


def resolver_id_adm_desde_codigo_bcra(codigo_bcra: str):
    """
    Dado el código BCRA de 3 dígitos que ya extrae el bot (ej: "072"),
    devuelve el id_adm correspondiente en Regente.

    PENDIENTE DE VERIFICAR: esta función asume que id_adm en Regente es
    siempre igual al código BCRA sin los ceros adelante (ej: "072" -> 72).
    Se confirmó para 6 bancos (011, 017, 072, 191, 285, 330) cruzando contra
    tipos_pago.csv, pero no está probado con una consulta real a
    rgAdministradoraNg para el resto de los bancos. Antes de confiar en esto
    a ciegas para un banco nuevo, conviene hacer un GET de prueba.
    """
    codigo_limpio = str(codigo_bcra).strip().lstrip("0") or "0"
    return int(codigo_limpio)
