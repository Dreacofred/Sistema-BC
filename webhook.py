# webhook.py
import os
import time
import uuid
import json
import base64
import threading
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
import anthropic

from core.prompts_ia import prompt_extraccion_cheques_whatsapp

# ==========================================
# 1. CREDENCIALES Y CONFIGURACIÓN
# ==========================================
URL_SB = os.environ.get("SUPABASE_URL")
KEY_SB = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL_SB, KEY_SB)

cliente_ia = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODELO_IA = "claude-sonnet-5"

GREEN_API_URL = os.environ.get("GREEN_API_URL")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN")

app = Flask(__name__)

# Memoria temporal para lotes
lotes_abiertos = {}

# ==========================================
# 2. FUNCIONES AUXILIARES
# ==========================================
def enviar_mensaje_wa(chat_id, mensaje):
    url = f"{GREEN_API_URL}/sendMessage/{GREEN_API_TOKEN}"
    payload = {"chatId": chat_id, "message": mensaje}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

def descargar_imagen(download_url, ruta_destino):
    try:
        response = requests.get(download_url)
        if response.status_code == 200:
            with open(ruta_destino, 'wb') as f:
                f.write(response.content)
            return True
        return False
    except Exception as e:
        print(f"Error descargando imagen: {e}")
        return False

# ==========================================
# 4. EL CEREBRO DE IA Y GUARDADO
# ==========================================
def procesar_y_guardar(rutas_imagenes, cliente_tag):
    urls_supabase = []
    bloques_contenido = []
    id_lote_unico = str(uuid.uuid4())

    try:
        # 1. Subir fotos o PDFs a Supabase, y armar los bloques para Claude
        for ruta in rutas_imagenes:
            nombre_archivo = f"doc_{int(time.time())}_{os.path.basename(ruta)}"
            es_pdf = ruta.lower().endswith(".pdf")
            tipo_mime = "application/pdf" if es_pdf else "image/jpeg"

            with open(ruta, "rb") as f:
                bytes_archivo = f.read()
                supabase.storage.from_("comprobantes").upload(
                    path=nombre_archivo,
                    file=bytes_archivo,
                    file_options={"content-type": tipo_mime}
                )
            url_publica = supabase.storage.from_("comprobantes").get_public_url(nombre_archivo)
            urls_supabase.append(url_publica)

            # 2. Codificar en base64 para mandarle directo a Claude (sin subida previa)
            base64_data = base64.b64encode(bytes_archivo).decode("utf-8")
            tipo_bloque = "document" if es_pdf else "image"
            bloques_contenido.append({
                "type": tipo_bloque,
                "source": {
                    "type": "base64",
                    "media_type": tipo_mime,
                    "data": base64_data
                }
            })

        fotos_juntas = ",".join(urls_supabase)

        # 3. Prompt (el mismo de siempre, centralizado en core/prompts_ia.py)
        prompt = prompt_extraccion_cheques_whatsapp(cliente_tag)
        bloques_contenido.append({"type": "text", "text": prompt})

        respuesta = cliente_ia.messages.create(
            model=MODELO_IA,
            max_tokens=4096,
            messages=[{"role": "user", "content": bloques_contenido}]
        )

        # 4. Limpieza de JSON a prueba de balas
        # Claude a veces manda primero un bloque de "pensamiento" (ThinkingBlock)
        # antes del bloque de texto con la respuesta final. Recorremos todos
        # los bloques y nos quedamos solo con los de tipo "text".
        raw_text = ""
        for bloque in respuesta.content:
            if bloque.type == "text":
                raw_text += bloque.text
        raw_text = raw_text.strip()

        start = raw_text.find('{')
        end = raw_text.rfind('}') + 1

        if start != -1 and end != 0:
            texto_json = raw_text[start:end]
            datos_ia = json.loads(texto_json)
        else:
            raise Exception("Claude no devolvió un JSON válido para leer.")

        # 5. Formatear y vincular foto individual
        for fila in datos_ia.get("cheques", []):
            fila['lote_id'] = id_lote_unico

            num_img = fila.pop('numero_imagen', None)
            if num_img and isinstance(num_img, int) and 1 <= num_img <= len(urls_supabase):
                fila['archivo_url'] = urls_supabase[num_img - 1]
            else:
                fila['archivo_url'] = fotos_juntas  # De respaldo

            if fila.get('fecha_emision') == "": fila['fecha_emision'] = None
            if fila.get('fecha_pago') == "": fila['fecha_pago'] = None

        # 6. Guardar en Base de Datos
        supabase.table("cobranzas_pendientes").insert(datos_ia["cheques"]).execute()

        return True

    except Exception as e:
        print(f"Error procesando lote: {e}")
        return False

# ==========================================
# 5. ENDPOINT WEBHOOK GREEN-API
# ==========================================
@app.route('/webhook', methods=['POST'])
def recibir_whatsapp():
    try:
        datos = request.json
        payload = datos.get('body', datos)

        if payload.get('typeWebhook') != 'incomingMessageReceived':
            return jsonify({"status": "ok"})

        chat_id = payload['senderData']['chatId']
        message_data = payload.get('messageData', {})
        type_message = message_data.get('typeMessage')

        # 1. EXTRAER EL TEXTO (Venga solo o como epígrafe de una foto/pdf)
        mensaje_texto = ""
        if type_message == "textMessage":
            mensaje_texto = message_data.get('textMessageData', {}).get('textMessage', '').strip().lower()
        elif type_message == "extendedTextMessage":
            mensaje_texto = message_data.get('extendedTextMessageData', {}).get('text', '').strip().lower()
        elif type_message == "imageMessage":
            mensaje_texto = message_data.get('imageMessageData', {}).get('caption', '').strip().lower()
        elif type_message == "documentMessage":
            mensaje_texto = message_data.get('documentMessageData', {}).get('caption', '').strip().lower()

        # 2. EVALUAR COMANDOS DE APERTURA O CIERRE
        if mensaje_texto.startswith("!bot "):
            texto_busqueda = mensaje_texto.replace("!bot ", "").strip()
            try:
                respuesta_db = supabase.table("clientes").select("nombre").ilike("nombre", f"%{texto_busqueda}%").execute()
                if len(respuesta_db.data) > 0:
                    nombre_oficial = respuesta_db.data[0]['nombre']
                    lotes_abiertos[chat_id] = {"cliente": nombre_oficial, "fotos": []}
                    enviar_mensaje_wa(chat_id, f"🟢 Lote abierto para: *{nombre_oficial}*.")
                else:
                    enviar_mensaje_wa(chat_id, f"❌ No encontré a '{texto_busqueda}'.")
                    return jsonify({"status": "ok"})
            except Exception as e:
                enviar_mensaje_wa(chat_id, "⚠️ Error buscando al cliente.")
                return jsonify({"status": "ok"})

        elif mensaje_texto == "!procesar":
            if chat_id in lotes_abiertos:
                lote = lotes_abiertos[chat_id]
                fotos = lote["fotos"]
                cliente = lote["cliente"]

                if len(fotos) == 0:
                    enviar_mensaje_wa(chat_id, "❌ No subiste archivos. Lote cancelado.")
                    del lotes_abiertos[chat_id]
                    return jsonify({"status": "ok"})

                cantidad = len(fotos)
                if cantidad <= 4: msg_t = "Esto sale al toque! 😜"
                elif cantidad <= 8: msg_t = "Bancame un minutito 😉"
                else: msg_t = "Una banda... 🤨 bancame 2 o 3 minuttos"

                enviar_mensaje_wa(chat_id, f"⏳ Evaluando {cantidad} archivos para *{cliente}*. {msg_t}")

                def trabajo_pesado(fotos_a_procesar, cliente_a_procesar, chat_destino):
                    exito = procesar_y_guardar(fotos_a_procesar, cliente_a_procesar)
                    if exito:
                        enviar_mensaje_wa(chat_destino, "🎉 ¡Listo! Ya está en la oficina pendiente de auditoría.")
                    else:
                        enviar_mensaje_wa(chat_destino, "⚠️ Hubo un error procesando el lote.")
                    import os
                    for f in fotos_a_procesar:
                        if os.path.exists(f): os.remove(f)

                hilo = threading.Thread(target=trabajo_pesado, args=(fotos, cliente, chat_id))
                hilo.start()
                del lotes_abiertos[chat_id]
            return jsonify({"status": "ok"})

        # 3. EVALUAR SI HAY ARCHIVOS ADJUNTOS (Y guardarlos en el carrito)
        if type_message in ["imageMessage", "documentMessage"]:
            if chat_id in lotes_abiertos:
                datos_archivo = message_data.get('documentMessageData') or message_data.get('fileMessageData') or message_data.get('imageMessageData') or {}
                download_url = datos_archivo.get('downloadUrl')

                if download_url:
                    ext = ".pdf" if type_message == "documentMessage" else ".jpg"
                    nombre_temp = f"tmp_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"

                    if descargar_imagen(download_url, nombre_temp):
                        lotes_abiertos[chat_id]["fotos"].append(nombre_temp)
                        enviar_mensaje_wa(chat_id, f"✅ Archivo {len(lotes_abiertos[chat_id]['fotos'])} recibido.")

        return jsonify({"status": "ok"})

    except Exception as e:
        print(f"Error en webhook: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
