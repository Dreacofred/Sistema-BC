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
    Busca un sujeto en Regente por CUIT (sin guiones ni espacios).
    Devuelve el diccionario del sujeto si lo encuentra, o None si no existe.

    Esta función NO crea nada — es de solo lectura. Se usa como el primer
    paso del flujo (ver si el emisor de un cheque ya existe antes de decidir
    si hace falta darlo de alta).
    """
    base_url, _, _ = _obtener_credenciales()
    cuit_limpio = "".join(c for c in str(cuit) if c.isdigit())

    respuesta = requests.get(
        f"{base_url}/api/v1/rgSujetoNg",
        params={"cuit": cuit_limpio},
        headers=_headers(),
        timeout=15,
    )
    respuesta.raise_for_status()
    resultados = respuesta.json()

    # PENDIENTE DE VERIFICAR: no tenemos confirmado todavía el formato exacto
    # de la respuesta (si es una lista directa, o un objeto con una clave
    # "datos"/"resultados" adentro). Este código asume que es una lista
    # directa de sujetos que hacen match. Hay que confirmarlo con un GET real
    # antes de usar esta función en la integración de verdad.
    if isinstance(resultados, list):
        return resultados[0] if resultados else None
    return resultados or None


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
