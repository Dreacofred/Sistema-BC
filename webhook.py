import os
import time
import uuid
import json
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai
from supabase import create_client, Client

# ==========================================
# 1. CREDENCIALES
# ==========================================
URL_SB = os.environ.get("SUPABASE_URL")
KEY_SB = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GREEN_ID = os.environ.get("GREENAPI_ID")
GREEN_TOKEN = os.environ.get("GREENAPI_TOKEN")

if URL_SB and KEY_SB:
    supabase: Client = create_client(URL_SB, KEY_SB)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)

# ==========================================
# 2. EL CARRITO DE COMPRAS
# ==========================================
lotes_abiertos = {}

# ==========================================
# 3. FUNCIONES DE WHATSAPP (GreenAPI)
# ==========================================
def enviar_mensaje_wa(chat_id, mensaje):
    if not GREEN_ID or not GREEN_TOKEN:
        return
    url = f"https://api.green-api.com/waInstance{GREEN_ID}/sendMessage/{GREEN_TOKEN}"
    payload = {"chatId": chat_id, "message": mensaje}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

def descargar_imagen(url_descarga, nombre_archivo):
    try:
        respuesta = requests.get(url_descarga)
        if respuesta.status_code == 200:
            with open(nombre_archivo, 'wb') as f:
                f.write(respuesta.content)
            return True
    except Exception as e:
        print(f"Error descargando imagen: {e}")
    return False

# ==========================================
# 4. EL CEREBRO DE IA Y GUARDADO
# ==========================================
def procesar_y_guardar(rutas_imagenes, cliente_tag):
    archivos_gemini = []
    urls_supabase = []
    id_lote_unico = str(uuid.uuid4()) 
    
    try:
        # 1. Subir fotos o PDFs a Supabase con el formato correcto
        for ruta in rutas_imagenes:
            nombre_archivo = f"doc_{int(time.time())}_{os.path.basename(ruta)}"
            es_pdf = ruta.lower().endswith(".pdf")
            tipo_mime = "application/pdf" if es_pdf else "image/jpeg"
            
            with open(ruta, "rb") as f:
                supabase.storage.from_("comprobantes").upload(
                    path=nombre_archivo,
                    file=f,
                    file_options={"content-type": tipo_mime}
                )
            url_publica = supabase.storage.from_("comprobantes").get_public_url(nombre_archivo)
            urls_supabase.append(url_publica)
            
            # 2. Subir a Gemini y ESPERAR (Crucial para PDFs)
            archivo_subido = genai.upload_file(ruta)
            while archivo_subido.state.name == 'PROCESSING':
                time.sleep(2) # Espera 2 segundos antes de volver a preguntar
                archivo_subido = genai.get_file(archivo_subido.name)
            archivos_gemini.append(archivo_subido)

        fotos_juntas = ",".join(urls_supabase)

        # 3. Prompt
        modelo = genai.GenerativeModel('gemini-2.5-pro')
        prompt = f"""
        Sos un auditor contable experto de BC Combustibles. Analizá este lote: UN ticket S.I.C.E. y VARIAS fotos de cheques. Cliente: '{cliente_tag}'.
        
        PASO 1: Detallá qué ves en cada cheque en 'razonamiento_en_voz_alta'.
        PASO 2: Extraé los datos. 
        - REGLA 1: Si dudás, dejalo vacío (""). NO inventes.
        - REGLA 2: Para 'razon_social_emisor', buscá el texto impreso junto al CUIT. Ignorá el 'Páguese a' manuscrito.
        - REGLA 3: Para 'numero_cuenta', extraé los números crudos SIN guiones ni espacios.
        
        Devolvé ÚNICAMENTE un objeto JSON:
        {{
            "cheques": [
                {{
                    "cliente_asociado": "{cliente_tag}",
                    "tipo_comprobante": "Cheque Físico",
                    "banco_origen": "Nombre del banco",
                    "codigo_banco": "Código banco (ej: 014)",
                    "codigo_sucursal": "Código sucursal (ej: 1842)",
                    "numero_cuenta": "Número de cuenta limpio",
                    "numero_identificador": "Número del cheque",
                    "monto": numero_decimal,
                    "fecha_emision": "YYYY-MM-DD",
                    "fecha_pago": "YYYY-MM-DD",
                    "cuit_emisor": "CUIT con guiones",
                    "razon_social_emisor": "Razón social impresa",
                    "estado_auditoria": "Pendiente",
                    "regente_cliente_id": "1045"
                }}
            ]
        }}
        """
        
        respuesta = modelo.generate_content(archivos_gemini + [prompt])
        
        # 4. Limpieza de JSON a prueba de balas (sin el espacio traicionero)
        texto_json = respuesta.text.replace("```json", "").replace("```", "").strip()
        datos_ia = json.loads(texto_json)
        
        # 5. Formatear y limpiar
        for fila in datos_ia.get("cheques", []):
            fila['lote_id'] = id_lote_unico
            fila['archivo_url'] = fotos_juntas
            if fila.get('fecha_emision') == "": fila['fecha_emision'] = None
            if fila.get('fecha_pago') == "": fila['fecha_pago'] = None

        # 6. Guardar en Base de Datos
        supabase.table("cobranzas_pendientes").insert(datos_ia["cheques"]).execute()
        
        # Limpiar Gemini
        for g_file in archivos_gemini:
            genai.delete_file(g_file.name)
            
        return True

    except Exception as e:
        print(f"Error procesando lote: {e}")
        return False

# ==========================================
# 5. EL EMBUDO DE RECEPCIÓN (Webhook GreenAPI)
# ==========================================
@app.route('/webhook', methods=['POST'])
def recibir_whatsapp():
    datos = request.json
    if not datos: return jsonify({"status": "ok"})
    
    try:
        # GreenAPI puede enviar el payload directamente o dentro de 'body'
        payload = datos.get('body', datos)
        
        # Solo procesamos si es un mensaje recibido
        if payload.get('typeWebhook') != 'incomingMessageReceived':
            return jsonify({"status": "ok"})
            
        chat_id = payload['senderData']['chatId']
        message_data = payload.get('messageData', {})
        type_message = message_data.get('typeMessage')
        
        mensaje_texto = ""
        if type_message == "textMessage":
            mensaje_texto = message_data.get('textMessageData', {}).get('textMessage', '').strip().lower()
        elif type_message == "extendedTextMessage":
            mensaje_texto = message_data.get('extendedTextMessageData', {}).get('text', '').strip().lower()

        # --- A. COMANDO DE APERTURA ---
        if mensaje_texto.startswith("!bot "):
            texto_busqueda = mensaje_texto.replace("!bot ", "").strip()
            
            try:
                # BÚSQUEDA INTELIGENTE EN SUPABASE
                # Busca cualquier cliente que contenga el texto (ignorando mayúsculas/minúsculas)
                respuesta_db = supabase.table("clientes").select("nombre").ilike("nombre", f"%{texto_busqueda}%").execute()
                
                if len(respuesta_db.data) > 0:
                    # ¡Lo encontró! Usamos el nombre oficial exacto que está en la tabla
                    nombre_oficial = respuesta_db.data[0]['nombre']
                    
                    lotes_abiertos[chat_id] = {"cliente": nombre_oficial, "fotos": []}
                    enviar_mensaje_wa(chat_id, f"🟢 Lote abierto para: *{nombre_oficial}*.\nMandá las fotos de los cheques y el ticket SICE. Cuando termines escribí *!procesar*")
                else:
                    # Si escribís mal el nombre o no existe, te avisa en el acto
                    enviar_mensaje_wa(chat_id, f"❌ No encontré a ningún cliente que coincida con '{texto_busqueda}' en la base de datos. Revisá cómo está escrito o cargalo primero en Supabase.")
            
            except Exception as e:
                print(f"Error buscando al cliente en Supabase: {e}")
                enviar_mensaje_wa(chat_id, "⚠️ Hubo un error de conexión buscando al cliente en la base de datos.")
                
            return jsonify({"status": "ok"})
            
        # --- B. RECIBIENDO FOTOS Y ARCHIVOS PDF ---
        elif type_message in ["imageMessage", "documentMessage"]:
            if chat_id in lotes_abiertos:
                # GreenAPI guarda la URL en distintos lugares según si es foto o documento
                datos_archivo = message_data.get('documentMessageData') or message_data.get('fileMessageData') or message_data.get('imageMessageData') or {}
                download_url = datos_archivo.get('downloadUrl')
                
                if download_url:
                    ext = ".pdf" if type_message == "documentMessage" else ".jpg"
                    nombre_temp = f"tmp_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
                    
                    if descargar_imagen(download_url, nombre_temp):
                        lotes_abiertos[chat_id]["fotos"].append(nombre_temp)
                        cant = len(lotes_abiertos[chat_id]["fotos"])
                        palabra = "PDF" if type_message == "documentMessage" else "Foto"
                        enviar_mensaje_wa(chat_id, f"✅ {palabra} {cant} recibido en el carrito.")
                else:
                    print("Error: No se encontró la URL de descarga en el mensaje.")
                    
            return jsonify({"status": "ok"})
            
        # --- C. COMANDO DE EJECUCIÓN ---
        elif mensaje_texto == "!procesar":
            if chat_id in lotes_abiertos:
                lote = lotes_abiertos[chat_id]
                cliente = lote["cliente"]
                fotos = lote["fotos"]
                
                if len(fotos) == 0:
                    enviar_mensaje_wa(chat_id, "❌ No subiste ninguna foto. Se canceló el lote.")
                    del lotes_abiertos[chat_id]
                    return jsonify({"status": "ok"})
                    
                enviar_mensaje_wa(chat_id, f"⏳ Evaluando {len(fotos)} imágenes para *{cliente}*. Esto puede tardar unos segundos...")
                
                # Ejecutar la extracción de datos
                exito = procesar_y_guardar(fotos, cliente)
                
                if exito:
                    enviar_mensaje_wa(chat_id, "🎉 ¡Listo! Lote procesado con éxito. Ya está en la oficina pendiente de auditoría.")
                else:
                    enviar_mensaje_wa(chat_id, "⚠️ Hubo un error procesando el lote. Por favor, avisale a administración.")
                    
                # Borrar fotos temporales del servidor
                for f in fotos:
                    if os.path.exists(f): os.remove(f)
                    
                del lotes_abiertos[chat_id]
                
    except Exception as e:
        print(f"Error en webhook general: {e}")
        
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
