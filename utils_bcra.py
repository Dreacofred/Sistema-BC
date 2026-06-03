import requests
import time
import json
import urllib3
import re
from PIL import Image
import streamlit as st

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuración única
API_KEY_SCRAPER = "cf3ae8aaf0457292c6e2f8983b207139"

def consultar_bcra_completo(cuit):
    cuit = str(cuit).strip()
    url_deudas = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/{cuit}"
    url_cheques = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/ChequesRechazados/{cuit}"
    
    datos_cliente = {"situacion": 1, "entidad": "Sin Registros", "denominacion": "Cliente Desconocido", "cheques_rechazados": 0, "error_api": False}
    
    try:
        payload_deudas = {'api_key': API_KEY_SCRAPER, 'url': url_deudas, 'render': 'false'}
        res_deuda = requests.get('https://api.scraperapi.com/', params=payload_deudas, timeout=45)
        
        if res_deuda.status_code == 403: return {"error_api": "HTTP 403: ScraperAPI sin créditos"}
            
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
        
        payload_cheques = {'api_key': API_KEY_SCRAPER, 'url': url_cheques, 'render': 'false'}
        res_cheque = requests.get('https://api.scraperapi.com/', params=payload_cheques, timeout=45)
        
        if res_cheque.status_code == 403: return {"error_api": "HTTP 403: ScraperAPI sin créditos"}

        if res_cheque.status_code == 200:
            try:
                data_ch = res_cheque.json()
                json_str = json.dumps(data_ch).lower()
                conteo_real = max(json_str.count('"nrocheque"'), json_str.count('"fecharechazo"'), json_str.count('"numerocheque"'))
                if conteo_real == 0 and data_ch.get("results"): conteo_real = 1
                datos_cliente['cheques_rechazados'] = conteo_real
            except Exception: datos_cliente['cheques_rechazados'] = -1
        elif res_cheque.status_code == 404: datos_cliente['cheques_rechazados'] = 0
        else: datos_cliente['cheques_rechazados'] = -1
            
        return datos_cliente
    except Exception as e:
        return {"error_api": str(e)}

def procesar_lote_cheques_ia(cliente_ia, img_lote):
    prompt_cot = """
    Analiza este lote de cheques. Devuelve JSON: [{"id": 1, "numero_cheque": "...", "emisor": "...", "cuit": "..."}]
    """
    try:
        res = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[prompt_cot, img_lote])
        txt = res.text.replace("```json", "").replace("```", "").strip()
        start, end = txt.find('['), txt.rfind(']') + 1
        return json.loads(txt[start:end]) if start != -1 else []
    except: return []

def guardar_en_lista_negra(supabase, cuit, situacion, nombre, obs):
    try:
        supabase.table("cuits_afectados").insert({
            "cuit": cuit, "situacion_bcra": situacion, "observaciones": f"Titular: {nombre} | {obs}"
        }).execute()
        return True
    except: return False
