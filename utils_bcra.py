import requests
import time
import json
import base64
import io
import urllib3
import re
import streamlit as st

from core.prompts_ia import HERRAMIENTA_LECTURA_CHEQUES_BCRA, instrucciones_lectura_cheques_bcra

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔑 LLAVE DE SCRAPEOPS (ahora se lee desde los Secrets de Streamlit)
API_KEY_SCRAPEOPS = st.secrets["SCRAPEOPS_API_KEY"]

MODELO_CLAUDE = "claude-sonnet-5"

# ==========================================
# 1. FUNCIÓN DE CONSULTA AL BCRA (NUEVO TÚNEL SCRAPEOPS)
# ==========================================
@st.cache_data(ttl=60 * 60 * 24)
def _obtener_mapa_entidades():
    """
    Trae el listado de entidades financieras del BCRA (código -> nombre) desde
    /cheques/v1.0/entidades y lo cachea por 24hs, para no gastar una consulta
    de ScrapeOps extra por cada CUIT consultado. Se usa para traducir el
    código numérico de entidad que devuelve el endpoint de Cheques Rechazados
    a un nombre de banco legible. Si falla, devuelve un diccionario vacío
    (los códigos se muestran tal cual, sin romper nada).
    """
    mapa = {}
    try:
        url_entidades = "https://api.bcra.gob.ar/cheques/v1.0/entidades"
        payload = {'api_key': API_KEY_SCRAPEOPS, 'url': url_entidades}
        res = requests.get('https://proxy.scrapeops.io/v1/', params=payload, timeout=30)
        if res.status_code == 200:
            data = res.json()
            for e in data.get("results", []):
                codigo = str(e.get("codigoEntidad", ""))
                nombre = e.get("denominacion", codigo)
                if codigo:
                    mapa[codigo] = nombre
    except Exception:
        pass
    return mapa


def _parsear_detalle_cheques(data_ch, mapa_entidades=None):
    """
    Recorre la estructura real que devuelve el BCRA para
    /Deudas/ChequesRechazados/{cuit} (agrupada por causal y entidad) y la
    aplana en una lista simple de cheques, uno por fila, para mostrar en
    tabla. Devuelve lista vacía si no hay resultados o la estructura no es
    la esperada. Si se pasa "mapa_entidades" (código -> nombre), traduce el
    código de entidad a nombre de banco; si no lo encuentra en el mapa, deja
    el código tal cual.
    """
    mapa_entidades = mapa_entidades or {}
    detalle = []
    try:
        resultados = data_ch.get("results", {})
        for bloque_causal in resultados.get("causales", []):
            causal = bloque_causal.get("causal", "Sin especificar")
            for bloque_entidad in bloque_causal.get("entidades", []):
                codigo_entidad = str(bloque_entidad.get("entidad", "Desconocida"))
                nombre_entidad = mapa_entidades.get(codigo_entidad, f"Entidad {codigo_entidad}")
                for cheque in bloque_entidad.get("detalle", []):
                    detalle.append({
                        "Nº Cheque": cheque.get("nroCheque", "-"),
                        "Causal": causal,
                        "Fecha Rechazo": cheque.get("fechaRechazo", "-"),
                        "Fecha Pago": cheque.get("fechaPago") or "Sin pagar",
                        "Monto": cheque.get("monto", "-"),
                        "Entidad": nombre_entidad,
                    })
    except Exception:
        pass
    return detalle


def _parsear_detalle_entidades(entidades_periodo):
    """
    Recibe la lista de entidades del período más reciente (tal cual la
    devuelve el BCRA en /Deudas/{cuit} -> results.periodos[0].entidades) y
    arma una tabla con una fila por banco/entidad: situación, monto y días
    de atraso. Antes solo se miraba la primera entidad de la lista; esto
    trae el detalle completo de todos los bancos donde el CUIT tiene deuda
    informada en el último período.
    """
    detalle = []
    try:
        for e in entidades_periodo:
            detalle.append({
                "Entidad": e.get("entidad", "Desconocida"),
                "Situación": e.get("situacion", "-"),
                "Monto (miles $)": e.get("monto", "-"),
                "Días Atraso": e.get("diasAtrasoPago", "-"),
            })
    except Exception:
        pass
    return detalle


def consultar_bcra_completo(cuit):
    cuit = str(cuit).strip()
    url_deudas = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/{cuit}"
    url_cheques = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/ChequesRechazados/{cuit}"
    
    datos_cliente = {"situacion": 1, "entidad": "Sin Registros", "denominacion": "Cliente Desconocido", "cheques_rechazados": 0, "detalle_cheques": [], "detalle_entidades": [], "error_api": False}
    
    try:
        payload_deudas = {'api_key': API_KEY_SCRAPEOPS, 'url': url_deudas}
        res_deuda = requests.get('https://proxy.scrapeops.io/v1/', params=payload_deudas, timeout=45)
        
        if res_deuda.status_code in [401, 403]:
            return {"error_api": "HTTP 403: ScrapeOps sin créditos / Llave inválida"}
            
        if res_deuda.status_code == 200:
            try:
                data = res_deuda.json()
                if data.get('status') == 200 and 'results' in data:
                    res = data['results']
                    datos_cliente['denominacion'] = res.get('denominacion', 'Cliente')
                    periodos = res.get('periodos', [])
                    if periodos and 'entidades' in periodos[0] and periodos[0]['entidades']:
                        entidades_periodo = periodos[0]['entidades']
                        datos_cliente['detalle_entidades'] = _parsear_detalle_entidades(entidades_periodo)

                        # Situación = la PEOR de todas las entidades del período (más
                        # conservador que mirar solo la primera de la lista, como
                        # se hacía antes).
                        peor_entidad = max(entidades_periodo, key=lambda e: e.get("situacion", 1))
                        datos_cliente['situacion'] = peor_entidad.get("situacion", 1)
                        datos_cliente['entidad'] = peor_entidad.get("entidad", "Entidad Financiera")
            except Exception: pass
        
        time.sleep(1) 
        
        payload_cheques = {'api_key': API_KEY_SCRAPEOPS, 'url': url_cheques}
        res_cheque = requests.get('https://proxy.scrapeops.io/v1/', params=payload_cheques, timeout=45)
        
        if res_cheque.status_code in [401, 403]:
            return {"error_api": "HTTP 403: ScrapeOps sin créditos / Llave inválida"}

        if res_cheque.status_code == 200:
            try:
                data_ch = res_cheque.json()
                mapa_entidades = _obtener_mapa_entidades()
                detalle_cheques = _parsear_detalle_cheques(data_ch, mapa_entidades)
                datos_cliente['detalle_cheques'] = detalle_cheques
                datos_cliente['cheques_rechazados'] = len(detalle_cheques)
            except Exception: 
                datos_cliente['cheques_rechazados'] = -1
                datos_cliente['detalle_cheques'] = []
                
        elif res_cheque.status_code == 404: 
            datos_cliente['cheques_rechazados'] = 0
        elif res_cheque.status_code == 429: 
            datos_cliente['cheques_rechazados'] = -429
        else: 
            datos_cliente['cheques_rechazados'] = -1
            
        return datos_cliente
        
    except requests.exceptions.RequestException as e:
        return {"error_api": f"Caída de red: {str(e)[:40]}..."}
    except Exception as e:
        return {"error_api": str(e)}

# ==========================================
# 2. FUNCIÓN DE INTELIGENCIA ARTIFICIAL (ESCANEO DE CHEQUES)
# ==========================================
# MIGRADO A CLAUDE (agosto 2026): antes usaba Gemini con un prompt de texto
# libre y parseo manual de JSON (buscando "[" y "]"). Ahora usa Claude con la
# herramienta forzada "registrar_cheques_para_verificacion" (ver
# core/prompts_ia.py). El primer parámetro ahora tiene que ser un cliente de
# Anthropic (anthropic.Anthropic), no un cliente de Gemini como antes.
def _bloque_imagen_claude(imagen_pil):
    """Convierte una imagen PIL (ya redimensionada con .thumbnail() en
    modulos/verificacion_bcra.py) al formato de bloque de imagen que espera
    la API de Claude: base64 + media_type."""
    buffer = io.BytesIO()
    formato = (imagen_pil.format or "JPEG").upper()
    if formato not in ("JPEG", "PNG", "GIF", "WEBP"):
        formato = "JPEG"
    imagen_pil.save(buffer, format=formato)
    media_type = f"image/{formato.lower()}"
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(buffer.getvalue()).decode("utf-8"),
        },
    }


def procesar_lote_cheques_ia(cliente_claude, img_lote):
    """
    Lee un lote de cheques físicos de una foto usando Claude. Devuelve una
    lista de diccionarios con las claves "numero_cheque", "emisor" y "cuit"
    — la misma forma que devolvía antes con Gemini, para no romper el código
    que la consume en modulos/verificacion_bcra.py.
    """
    try:
        respuesta = cliente_claude.messages.create(
            model=MODELO_CLAUDE,
            max_tokens=2048,
            system=instrucciones_lectura_cheques_bcra(),
            tools=[HERRAMIENTA_LECTURA_CHEQUES_BCRA],
            tool_choice={"type": "tool", "name": "registrar_cheques_para_verificacion"},
            messages=[{
                "role": "user",
                "content": [_bloque_imagen_claude(img_lote)],
            }],
        )

        for bloque in respuesta.content:
            if bloque.type == "tool_use":
                return bloque.input.get("cheques") or []

        st.error("Falla en el motor de IA: Claude no devolvió los datos con la herramienta esperada.")
        return []

    except Exception as e:
        st.error(f"Falla en el motor de IA: {str(e)}")
        return []

# ==========================================
# 3. FUNCIÓN DE BASE DE DATOS (LISTA NEGRA COOPERATIVA)
# ==========================================
def guardar_en_lista_negra(supabase, cuit, situacion, nombre, obs):
    try:
        supabase.table("cuits_afectados").insert({
            "cuit": cuit, "situacion_bcra": situacion, "observaciones": f"Titular: {nombre} | {obs}"
        }).execute()
        st.success(f"✅ CUIT {cuit} guardado en Lista Negra exitosamente.")
        return True
    except Exception as e:
        st.error(f"Error en BD: {e}")
        return False
