import os
import time
import json
import pandas as pd
from flask import Flask, request, jsonify
import google.generativeai as genai
from supabase import create_client, Client

# ==========================================
# 1. CREDENCIALES (Ajustadas para la Nube)
# ==========================================
URL_SB = os.environ.get("SUPABASE_URL", "tu_url_supabase_aqui")
KEY_SB = os.environ.get("SUPABASE_KEY", "tu_key_supabase_aqui")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "tu_key_gemini_aqui")

supabase: Client = create_client(URL_SB, KEY_SB)
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)

# ==========================================
# 2. LA MEMORIA DEL BOT (El "Carrito")
# ==========================================
lotes_abiertos = {}

# ==========================================
# 3. FUNCIONES AUXILIARES (El Cerebro)
# ==========================================
def procesar_lote_con_ia(rutas_imagenes, cliente_tag):
    archivos_gemini_creados = []
    try:
        # Subir imágenes temporales a Gemini
        for ruta in rutas_imagenes:
            archivo_g = genai.upload_file(ruta)
            archivos_gemini_creados.append(archivo_g)

        modelo = genai.GenerativeModel('gemini-2.5-pro')
        
        prompt = f"""
        Sos un auditor contable experto de BC Combustibles. Analizá este lote: UN ticket S.I.C.E. y VARIAS fotos de cheques. Cliente: '{cliente_tag}'.
        
        PASO 1 (RAZONAMIENTO): Detallá qué ves en cada cheque en el campo 'razonamiento_en_voz_alta'. Si hay garabatos ilegibles, dejalo por escrito.
        
        PASO 2 (EXTRACCIÓN ESTRICTA): Completá los datos. 
        - REGLA 1: Si dudás sobre un dato manuscrito, dejalo vacío (""). NO inventes.
        - REGLA 2: Para 'razon_social_emisor', buscá el texto impreso junto al CUIT. Ignorá el 'Páguese a' manuscrito.
        - REGLA 3: Para 'numero_cuenta', buscá en el recuadro superior derecho o en la banda magnética y extraé los números crudos, SIN guiones, ni barras, ni espacios (ej: 03800111186).
        
        Devolvé ÚNICAMENTE un objeto JSON con esta estructura exacta:
        {{
            "razonamiento_en_voz_alta": "Tu análisis...",
            "resumen_lote": {{
                "total_declarado_ticket": numero_decimal,
                "efectivo_declarado": numero_decimal
            }},
            "cheques": [
                {{
                    "cliente_asociado": "{cliente_tag}",
                    "tipo_comprobante": "Cheque Físico",
                    "banco_origen": "Nombre del banco",
                    "codigo_banco": "Código banco (ej: 014)",
                    "codigo_sucursal": "Código sucursal/plaza (ej: 1842)",
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
        
        contenido_a_procesar = archivos_gemini_creados + [prompt]
        respuesta = modelo.generate_content(contenido_a_procesar)
        
        # Limpiar la memoria de Google
        for g_file in archivos_gemini_creados:
            genai.delete_file(g_file.name)
            
        texto_json = respuesta.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_json)

    except Exception as e:
        print(f"Error en IA: {e}")
        return None

def armar_excel_regente(datos_ia):
    try:
        cheques = datos_ia.get("cheques", [])
        if not cheques:
            return None
            
        df_exportar = pd.DataFrame(cheques)
        df_regente = pd.DataFrame({
            "Titular": df_exportar.get("razon_social_emisor", ""),
            "Emision": df_exportar.get("fecha_emision", ""),
            "Venc.": df_exportar.get("fecha_pago", ""),
            "Nro": df_exportar.get("numero_identificador", ""),
            "Bco.": df_exportar.get("codigo_banco", ""),
            "NCta.": df_exportar.get("numero_cuenta", ""),
            "Plaza": df_exportar.get("codigo_sucursal", ""),
            "Monto": df_exportar.get("monto", 0.0)
        })
        
        nombre_archivo = f"importacion_regente_{int(time.time())}.csv"
        df_regente.to_csv(nombre_archivo, index=False, encoding='utf-8')
        return nombre_archivo
    except Exception as e:
        print(f"Error armando Excel: {e}")
        return None

# ==========================================
# 4. EL EMBUDO DE WHATSAPP (El Webhook)
# ==========================================
@app.route('/webhook', methods=['POST'])
def recibir_mensaje():
    datos = request.json
    remitente = datos.get('remitente_id') 
    mensaje_texto = datos.get('texto', '').strip().lower()
    tiene_imagen = datos.get('es_imagen', False)
    
    # A. COMANDO DE APERTURA (!bot cliente)
    if mensaje_texto.startswith("!bot "):
        nombre_cliente = mensaje_texto.replace("!bot ", "").strip().upper()
        lotes_abiertos[remitente] = {"cliente": nombre_cliente, "fotos": []}
        print(f"🟢 Lote abierto para: {nombre_cliente}")
        # enviar_whatsapp(remitente, "🟢 Lote abierto...")
        return jsonify({"status": "ok"})

    # B. RECIBIENDO FOTOS
    elif tiene_imagen:
        if remitente in lotes_abiertos:
            ruta_imagen = "ruta_simulada.jpg" # descargar_imagen_de_whatsapp()
            lotes_abiertos[remitente]["fotos"].append(ruta_imagen)
            print(f"✅ Foto agregada. Total: {len(lotes_abiertos[remitente]['fotos'])}")
            # enviar_whatsapp(remitente, "✅ Imagen agregada.")
        return jsonify({"status": "ok"})

    # C. COMANDO DE EJECUCIÓN (!procesar)
    elif mensaje_texto == "!procesar":
        if remitente in lotes_abiertos:
            lote = lotes_abiertos[remitente]
            cliente = lote["cliente"]
            fotos_rutas = lote["fotos"]
            
            if len(fotos_rutas) == 0:
                print("❌ Lote sin fotos.")
                del lotes_abiertos[remitente]
                return jsonify({"status": "error"})
                
            print(f"⏳ Procesando para {cliente}...")
            
            # --- LA MAGIA ---
            datos_ia = procesar_lote_con_ia(fotos_rutas, cliente) 
            
            if datos_ia:
                # Guardar en Supabase
                try:
                    supabase.table("cobranzas_pendientes").insert(datos_ia["cheques"]).execute()
                except Exception as e:
                    print(f"Error Supabase: {e}")

                # Armar el Excel y enviarlo
                ruta_excel = armar_excel_regente(datos_ia)
                if ruta_excel:
                    print(f"✅ Excel listo en: {ruta_excel}")
                    # enviar_archivo_whatsapp(remitente, ruta_excel)
                
            del lotes_abiertos[remitente]
            
        return jsonify({"status": "ok"})

    return jsonify({"status": "ignorado"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
