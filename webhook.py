import os
import time
import uuid
import json
from flask import Flask, request, jsonify
import google.generativeai as genai
from supabase import create_client, Client

# ==========================================
# 1. CREDENCIALES (Para la Nube / Render)
# ==========================================
URL_SB = os.environ.get("SUPABASE_URL")
KEY_SB = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if URL_SB and KEY_SB:
    supabase: Client = create_client(URL_SB, KEY_SB)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)

# ==========================================
# 2. LA MEMORIA DEL BOT (El "Carrito")
# ==========================================
lotes_abiertos = {}

# ==========================================
# 3. EL CEREBRO DE IA Y GUARDADO
# ==========================================
def procesar_y_guardar(rutas_imagenes, cliente_tag):
    archivos_gemini = []
    urls_supabase = []
    
    # Creamos el código único para que este lote no se mezcle con otros
    id_lote_unico = str(uuid.uuid4()) 
    
    try:
        # 1. Subir fotos a Supabase (Para que la oficina las vea en la web)
        for ruta in rutas_imagenes:
            nombre_archivo = f"img_{int(time.time())}_{os.path.basename(ruta)}"
            with open(ruta, "rb") as f:
                supabase.storage.from_("comprobantes").upload(
                    path=nombre_archivo,
                    file=f,
                    file_options={"content-type": "image/jpeg"}
                )
            url_publica = supabase.storage.from_("comprobantes").get_public_url(nombre_archivo)
            urls_supabase.append(url_publica)
            
            # 2. Subir también a Gemini para que piense
            archivos_gemini.append(genai.upload_file(ruta))

        # Unimos las URLs separadas por coma para la base de datos
        fotos_juntas = ",".join(urls_supabase)

        # 3. El Súper Prompt
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
        
        # 4. Generar Respuesta
        respuesta = modelo.generate_content(archivos_gemini + [prompt])
        texto_json = respuesta.text.replace("```json", "").replace("```", "").strip()
        datos_ia = json.loads(texto_json)
        
        # 5. Inyectar Lote ID, Fotos y Limpiar Fechas Vacías
        for fila in datos_ia.get("cheques", []):
            fila['lote_id'] = id_lote_unico
            fila['archivo_url'] = fotos_juntas
            if fila.get('fecha_emision') == "": fila['fecha_emision'] = None
            if fila.get('fecha_pago') == "": fila['fecha_pago'] = None

        # 6. Guardar en Base de Datos (Estado 'Pendiente')
        supabase.table("cobranzas_pendientes").insert(datos_ia["cheques"]).execute()
        
        # Limpiar memoria de Google
        for g_file in archivos_gemini:
            genai.delete_file(g_file.name)
            
        return True, id_lote_unico

    except Exception as e:
        print(f"Error procesando lote: {e}")
        return False, str(e)

# ==========================================
# 4. EL EMBUDO DE WHATSAPP
# ==========================================
@app.route('/webhook', methods=['POST'])
def recibir_whatsapp():
    datos = request.json
    print("Recibido de WhatsApp:", datos)
    
    # Acá conectaremos la lectura de mensajes cuando definamos la API (GreenAPI/Evolution)
    
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    # El puerto lo define Render automáticamente
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
