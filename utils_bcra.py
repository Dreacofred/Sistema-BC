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
def consultar_bcra_completo(cuit):
    cuit = str(cuit).strip()
    url_deudas = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/{cuit}"
    url_cheques = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/ChequesRechazados/{cuit}"
    
    datos_cliente = {"situacion": 1, "entidad": "Sin Registros", "denominacion": "Cliente Desconocido", "cheques_rechazados": 0, "error_api": False}
    
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
                        entity_info = periodos[0]['entidades'][0]
                        datos_cliente['situacion'] = entity_info.get("situacion", 1)
                        datos_cliente['entidad'] = entity_info.get("entidad", "Entidad Financiera")
            except Exception: pass
        
        time.sleep(1) 
        
        payload_cheques = {'api_key': API_KEY_SCRAPEOPS, 'url': url_cheques}
        res_cheque = requests.get('https://proxy.scrapeops.io/v1/', params=payload_cheques, timeout=45)
        
        if res_cheque.status_code in [401, 403]:
            return {"error_api": "HTTP 403: ScrapeOps sin créditos / Llave inválida"}

        if res_cheque.status_code == 200:
            try:
                data_ch = res_cheque.json()
                json_str = json.dumps(data_ch).lower()
                conteo_real = max(
                    json_str.count('"nrocheque"'),
                    json_str.count('"fecharechazo"'),
                    json_str.count('"numerocheque"')
                )
                if conteo_real == 0 and data_ch.get("results"):
                    conteo_real = 1
                datos_cliente['cheques_rechazados'] = conteo_real
            except Exception: 
                datos_cliente['cheques_rechazados'] = -1
                
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
