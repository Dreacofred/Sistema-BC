import os
import time
import pandas as pd
from flask import Flask, request, jsonify
import google.generativeai as genai
from supabase import create_client, Client

# ==========================================
# 1. CREDENCIALES (Ajustadas para la Nube)
# ==========================================
# En Render, esto se lee desde las Variables de Entorno, no desde st.secrets
URL_SB = os.environ.get("SUPABASE_URL")
KEY_SB = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

supabase: Client = create_client(URL_SB, KEY_SB)
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)

# ==========================================
# 2. LA MEMORIA DEL BOT (El "Carrito")
# ==========================================
# Acá guardamos quién está mandando qué. 
# Ejemplo: {"5493421234567": {"cliente": "fochesatto", "fotos": ["ruta1.jpg", "ruta2.jpg"]}}
lotes_abiertos = {}

# ==========================================
# 3. EL EMBUDO DE WHATSAPP (El Webhook)
# ==========================================
@app.route('/webhook', methods=['POST'])
def recibir_mensaje():
    datos = request.json
    
    # 1. Extraer quién manda el mensaje y qué dice (Esto se ajustará según la API que usemos)
    remitente = datos.get('remitente_id') 
    mensaje_texto = datos.get('texto', '').strip().lower()
    tiene_imagen = datos.get('es_imagen', False)
    
    # ---------------------------------------------------------
    # CASO A: COMANDO DE APERTURA (!bot cliente)
    # ---------------------------------------------------------
    if mensaje_texto.startswith("!bot "):
        nombre_cliente = mensaje_texto.replace("!bot ", "").strip().upper()
        
        # Le abrimos un "carrito" a este número de teléfono
        lotes_abiertos[remitente] = {
            "cliente": nombre_cliente,
            "fotos": []
        }
        
        respuesta = f"🟢 Lote abierto para *{nombre_cliente}*.\nPor favor, reenviá las fotos de los comprobantes. Cuando termines, escribí *!procesar*."
        enviar_whatsapp(remitente, respuesta)
        return jsonify({"status": "ok"})

    # ---------------------------------------------------------
    # CASO B: RECIBIENDO FOTOS
    # ---------------------------------------------------------
    elif tiene_imagen:
        # Si el usuario mandó una foto, verificamos si tiene un lote abierto
        if remitente in lotes_abiertos:
            ruta_imagen = descargar_imagen_de_whatsapp(datos.get('url_imagen'))
            lotes_abiertos[remitente]["fotos"].append(ruta_imagen)
            
            # Le mandamos un tilde para que sepa que la foto entró al carrito
            enviar_whatsapp(remitente, "✅ Imagen agregada.")
        return jsonify({"status": "ok"})

    # ---------------------------------------------------------
    # CASO C: COMANDO DE EJECUCIÓN (!procesar)
    # ---------------------------------------------------------
    elif mensaje_texto == "!procesar":
        if remitente in lotes_abiertos:
            lote = lotes_abiertos[remitente]
            cliente = lote["cliente"]
            fotos_rutas = lote["fotos"]
            
            if len(fotos_rutas) == 0:
                enviar_whatsapp(remitente, "❌ Error: No enviaste ninguna foto para procesar. Lote cancelado.")
                del lotes_abiertos[remitente]
                return jsonify({"status": "error"})
                
            enviar_whatsapp(remitente, f"⏳ Analizando {len(fotos_rutas)} imágenes para {cliente}. Dame unos 20 segundos...")
            
            # --- ACÁ ENTRA LA MAGIA DE GEMINI QUE YA CREAMOS ---
            datos_ia = procesar_lote_con_ia(fotos_rutas, cliente) 
            # ---------------------------------------------------
            
            if datos_ia:
                # Armamos el Excel con Pandas
                ruta_excel = armar_excel_regente(datos_ia)
                
                # Devolvemos el archivo al grupo de WhatsApp
                enviar_archivo_whatsapp(remitente, ruta_excel, "Acá tenés el Excel listo para importar a Regente.")
                
            # Vaciamos el carrito para el próximo vendedor
            del lotes_abiertos[remitente]
            
        else:
            enviar_whatsapp(remitente, "❌ No tenés ningún lote abierto. Escribí '!bot NombreCliente' para empezar.")
            
        return jsonify({"status": "ok"})

    return jsonify({"status": "ignorado"})

# ==========================================
# 4. FUNCIONES AUXILIARES (Motor IA y Excel)
# ==========================================
# Acá pegaremos las funciones exactas que ya validamos en bot.py:
# def procesar_lote_con_ia()
# def armar_excel_regente()
# def enviar_whatsapp()

if __name__ == '__main__':
    # Esto mantiene el servidor prendido
    app.run(host='0.0.0.0', port=5000)
