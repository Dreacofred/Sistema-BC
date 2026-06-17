import requests
import time
import json
import urllib3
import re
import streamlit as st

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔑 LLAVE DE SCRAPEOPS (1.000 consultas gratuitas renovables por mes)
API_KEY_SCRAPEOPS = "d9362497-79e4-4177-97cb-11a18e8f72c7"  

# ==========================================
# 1. FUNCIÓN DE CONSULTA AL BCRA (NUEVO TÚNEL SCRAPEOPS)
# ==========================================
def consultar_bcra_completo(cuit):
    cuit = str(cuit).strip()
    url_deudas = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/{cuit}"
    url_cheques = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/ChequesRechazados/{cuit}"
    
    datos_cliente = {"situacion": 1, "entidad": "Sin Registros", "denominacion": "Cliente Desconocido", "cheques_rechazados": 0, "error_api": False}
    
    try:
        # --- CONSULTA DE DEUDAS ---
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
        
        # --- CONSULTA DE CHEQUES ---
        payload_cheques = {'api_key': API_KEY_SCRAPEOPS, 'url': url_cheques}
        res_cheque = requests.get('https://proxy.scrapeops.io/v1/', params=payload_cheques, timeout=45)
        
        if res_cheque.status_code in [401, 403]:
            return {"error_api": "HTTP 403: ScrapeOps sin créditos / Llave inválida"}

        if res_cheque.status_code == 200:
            try:
                data_ch = res_cheque.json()
                
                # PARCHE ARQUITECTURA: Conteo infalible de cheques
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
def procesar_lote_cheques_ia(cliente_ia, img_lote):
    prompt_cot = """
    Actúa como un auditor senior de BC Combustibles. Analiza esta foto que contiene un lote de cheques físicos.
    
    REGLAS DE ORO (Aislamiento de Datos):
    1. Analiza los cheques visualmente de arriba hacia abajo.
    2. El Emisor del cheque NUNCA es el nombre que sigue a "Páguese a". Ignora ese nombre gigante.
    3. Ve siempre a la parte INFERIOR del cheque (junto a la firma o el logo del banco). 
    4. Extrae de ahí el CUIT (11 dígitos, suelen empezar con 20, 23, 27, 30) and la Razón Social del EMISOR.
    5. Busca el NÚMERO DEL CHEQUE. Generalmente está en la esquina superior derecha o en la serie de números de la banda inferior.
    
    ESTRUCTURA DE RESPUESTA OBLIGATORIA:
    Devuelve ÚNICAMENTE un JSON puro (sin formato markdown) que sea una LISTA de objetos, uno por cada cheque:
    [
      {
        "id": 1,
        "numero_cheque": "84512356",
        "emisor": "RAZON SOCIAL 1",
        "cuit": "20123456789"
      }
    ]
    Si un dato no es legible con un 100% de seguridad, devuelve "ERROR_LECTURA" en ese campo específico.
    """
    try:
        res = cliente_ia.models.generate_content(
            model='gemini-2.5-pro',
            contents=[prompt_cot, img_lote]
        )
        txt = res.text.replace("```json", "").replace("```", "").strip()
        
        start = txt.find('[')
        end = txt.rfind(']') + 1
        if start != -1 and end != 0:
            return json.loads(txt[start:end])
        else:
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
