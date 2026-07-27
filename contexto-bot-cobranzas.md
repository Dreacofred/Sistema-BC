# Contexto del Proyecto: Bot Cobranzas / Auditoría de Cheques (BC Combustibles)

Volcado de estado migrado desde Gemini. Última actualización: 2026-07-27.

<resumen_proyecto>
El sistema "Auditoría de Cheques - BC Combustibles" tiene como propósito automatizar la digitalización, extracción de datos y auditoría de cheques físicos y comprobantes de pago.
El problema operativo que resuelve es el cuello de botella y los errores de tipeo al cargar manualmente lotes masivos de cheques.
Los usuarios finales son dos:

Los playeros/operadores en la estación (quienes envían las fotos de los cheques al bot de WhatsApp mediante un grupo).

El equipo administrativo/auditor (que revisa la información extraída por la IA en un panel web, corrige errores y exporta el lote para importarlo en el sistema de gestión "Regente").
</resumen_proyecto>

<arquitectura_y_stack>

Frontend (Panel de Auditoría): Streamlit. Desplegado para visualización y corrección de datos. Lee y actualiza la base de datos.

Backend (Bot de WhatsApp): Python con Flask y Gunicorn. Desplegado en Render (bot-sice-whatsapp.onrender.com). Expone un webhook para escuchar los eventos de WhatsApp y gestiona el flujo asíncrono.

Proveedor de API de WhatsApp: Green-API. Conectado a un celular físico (host) que recibe los mensajes y envía los webhooks al backend en Render.

Motor de Inteligencia Artificial: Google Gemini (modelo gemini-2.5-pro). Se utiliza para procesamiento multimodal (visión) y extracción estricta de entidades (JSON) a partir de las imágenes de los cheques.

Base de Datos y Almacenamiento: Supabase.

Tabla clientes (para validar si existe el lote a abrir).

Tabla cobranzas_pendientes (para alojar los cheques procesados).

Storage Bucket comprobantes (para almacenar las fotos temporales antes de mostrarlas en el frontend).
</arquitectura_y_stack>

<logica_de_negocio>

Flujo del Bot (Apertura y Carga):

El usuario envía !bot [Nombre del Cliente]. El bot busca el cliente en la tabla clientes de Supabase mediante un ilike. Si existe, abre un lote en memoria (diccionario lotes_abiertos).

El comando de apertura puede enviarse como texto plano o como epígrafe/caption adjunto a una imagen.

El usuario envía fotos (.jpg) de los cheques (varios cheques pueden estar en una sola foto). El bot almacena las imágenes localmente.

Flujo de Procesamiento (IA):

El usuario envía !procesar. El bot lanza un threading.Thread para no bloquear el webhook (evitando timeouts en Render).

Se suben las fotos a Supabase Storage y a la API de Gemini (genai.upload_file).

Reglas de Extracción Prompt: El motor debe retornar estrictamente un JSON puro. Los campos dudosos deben quedar como "". El numero_cuenta no debe contener guiones ni espacios. La razon_social_emisor se toma del texto impreso junto al CUIT (ignorando el texto manuscrito de "Páguese a").

Los cheques extraídos se insertan en cobranzas_pendientes con estado_auditoria = 'Pendiente'.

Flujo de Auditoría (Frontend):

La interfaz se distribuye dinámicamente: 65% del ancho para el visor de la imagen original y 35% para el formulario de corrección.

Se utiliza un componente expansible (acordeón) por cada cheque. Un lote puede contener múltiples cheques vinculados a la misma foto (optimizando la carga).

Al presionar "Guardar Fila", el estado se actualiza en el session_state temporalmente.

Solo cuando se auditaron todos los cheques del lote, el sistema permite descargar un CSV (formato Regente) y cerrar el lote (actualizando la base de datos).
</logica_de_negocio>

<indice_de_archivos>

bot.py (Versión final confirmada con distribución visual 65/35).

webhook.py (Versión final combinando extracción JSON robusta y lógica de epígrafes/captions, ensamblada con el boilerplate de Flask y Green-API acordado).
</indice_de_archivos>

<estructura_y_codigo>

```python
# bot.py
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import time

# ==========================================
# 1. CREDENCIALES
# ==========================================
URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL_SB, KEY_SB)

st.title("🏢 Auditoría de Cheques - BC Combustibles")
st.markdown("---")

# ==========================================
# 2. TRAER LOTES PENDIENTES
# ==========================================
@st.cache_data(ttl=10)
def obtener_datos():
    respuesta = supabase.table("cobranzas_pendientes").select("*").execute()
    return respuesta.data

datos_db = obtener_datos()
df_completo = pd.DataFrame(datos_db)

if df_completo.empty or not (df_completo['estado_auditoria'] == 'Pendiente').any():
    st.success("🎉 ¡Bandeja limpia! No hay cheques pendientes de auditoría en este momento.")
    st.stop()

# Solo trabajamos con los pendientes
df_pendientes = df_completo[df_completo['estado_auditoria'] == 'Pendiente'].copy()
lotes_disponibles = df_pendientes['cliente_asociado'].unique().tolist()

# ==========================================
# 3. VARIABLES DE MEMORIA
# ==========================================
if 'cheques_listos' not in st.session_state:
    st.session_state.cheques_listos = []
if 'datos_corregidos' not in st.session_state:
    st.session_state.datos_corregidos = {}

# ==========================================
# 4. SELECTOR DE LOTE
# ==========================================
st.subheader("📥 Bandeja de Pendientes")
cliente_sel = st.selectbox("Seleccioná un cliente para auditar su lote:", ["--- Elegí un cliente ---"] + lotes_disponibles)

if st.button("🔄 Actualizar Bandeja"):
    st.cache_data.clear()
    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 5. PANTALLA DE AUDITORÍA (ESTILO ACORDEÓN)
# ==========================================
if cliente_sel != "--- Elegí un cliente ---":
    df_lote = df_pendientes[df_pendientes['cliente_asociado'] == cliente_sel].copy()

    st.markdown(f"### 📋 Revisión de Cheques: {cliente_sel}")

    for index, fila in df_lote.iterrows():
        cid = fila['id']
        ya_listo = cid in st.session_state.cheques_listos

        # Icono dinámico según si ya lo guardamos en memoria
        icono = "✅ LISTO" if ya_listo else "🟠 PENDIENTE"

        # Mostramos los datos actualizados si ya se corrigieron, sino los de la base
        monto_display = st.session_state.datos_corregidos.get(cid, {}).get('monto', fila.get('monto', 0))
        nro_display = st.session_state.datos_corregidos.get(cid, {}).get('numero_identificador', fila.get('numero_identificador', 'S/N'))

        # ACORDEÓN EXPANDIBLE
        with st.expander(f"{icono} | Cheque Nº {nro_display} | Monto: ${float(monto_display or 0):,.2f}"):

            # ACÁ ESTÁ LA MAGIA: 1 de ancho para el form, 1.8 para la imagen (casi el doble de tamaño)
            col_datos, col_img = st.columns([1, 1.8])

            # --- MITAD DERECHA: IMAGEN GIGANTE ---
            with col_img:
                url_activa = str(fila['archivo_url']).split(',')[0].strip() if pd.notna(fila['archivo_url']) else ""

                if url_activa.startswith('http'):
                    if ".pdf" in url_activa.lower():
                        visor_url = f"https://docs.google.com/gview?url={url_activa}&embedded=true"
                        st.markdown(f'<iframe src="{visor_url}" width="100%" height="600" frameborder="0"></iframe>', unsafe_allow_html=True)
                        st.link_button("📄 Abrir PDF en pestaña grande", url_activa)
                    else:
                        st.image(url_activa, use_container_width=True)
                        st.link_button("🖼️ Ver imagen original", url_activa)
                else:
                    st.warning("Este cheque no tiene imagen adjunta.")

            # --- MITAD IZQUIERDA: FORMULARIO ESTILO LISTA ---
            with col_datos:
                if ya_listo:
                    st.success("✔️ Fila revisada y guardada temporalmente.")
                    if st.button("✏️ Editar nuevamente", key=f"btn_edit_{cid}"):
                        st.session_state.cheques_listos.remove(cid)
                        st.rerun()
                else:
                    with st.form(f"form_cheque_{cid}"):
                        st.markdown("📝 **Completá o corregí:**")

                        # Función que crea la estructura: Texto a la Izq, Caja a la Der
                        def crear_campo(etiqueta, valor, tipo="texto"):
                            c_lbl, c_inp = st.columns([1, 1.5])
                            c_lbl.markdown(f"<div style='margin-top: 8px; font-size: 14px;'>{etiqueta}</div>", unsafe_allow_html=True)
                            if tipo == "numero":
                                return c_inp.number_input(etiqueta, value=float(valor or 0.0), label_visibility="collapsed")
                            else:
                                return c_inp.text_input(etiqueta, value=str(valor), label_visibility="collapsed")

                        f_nro = crear_campo("Nº Cheque", fila.get('numero_identificador', ''))
                        f_monto = crear_campo("Monto ($)", fila.get('monto', 0.0), tipo="numero")
                        f_emi = crear_campo("Emisión", fila.get('fecha_emision', ''))
                        f_pago = crear_campo("Vencimiento", fila.get('fecha_pago', ''))
                        f_banco = crear_campo("Cód. Banco", fila.get('codigo_banco', ''))
                        f_sucursal = crear_campo("Cód. Sucursal", fila.get('codigo_sucursal', ''))
                        f_cuenta = crear_campo("Nº Cuenta", fila.get('numero_cuenta', ''))
                        f_cuit = crear_campo("CUIT Emisor", fila.get('cuit_emisor', ''))
                        f_rs = crear_campo("Razón Social", fila.get('razon_social_emisor', ''))

                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.form_submit_button("✅ Guardar Fila", type="primary", use_container_width=True):
                            # Guardamos los cambios en la memoria temporal
                            st.session_state.datos_corregidos[cid] = {
                                'numero_identificador': f_nro.strip(),
                                'monto': f_monto,
                                'fecha_emision': f_emi.strip(),
                                'fecha_pago': f_pago.strip(),
                                'codigo_banco': f_banco.strip(),
                                'codigo_sucursal': f_sucursal.strip(),
                                'numero_cuenta': f_cuenta.strip(),
                                'cuit_emisor': f_cuit.strip(),
                                'razon_social_emisor': f_rs.strip(),
                                'estado_auditoria': 'Auditado'
                            }
                            st.session_state.cheques_listos.append(cid)
                            st.rerun()

    # ==========================================
    # 6. CIERRE Y EXPORTACIÓN DEL LOTE
    # ==========================================
    st.markdown("<br><hr>", unsafe_allow_html=True)
    faltantes = len(df_lote) - len(st.session_state.cheques_listos)

    if faltantes > 0:
        st.info(f"⚠️ Faltan revisar {faltantes} cheque(s) para poder exportar y cerrar el lote.")
    else:
        st.success("🎉 ¡Excelente! Todos los cheques de este lote fueron revisados.")
        st.markdown("### 🚀 Exportación a Regente")

        # Armamos la tabla final para exportar
        filas_export = []
        suma_total = 0
        for cid in df_lote['id']:
            d = st.session_state.datos_corregidos[cid]
            suma_total += d['monto']
            filas_export.append({
                "Titular": d['razon_social_emisor'],
                "Emision": d['fecha_emision'],
                "Venc.": d['fecha_pago'],
                "Nro": d['numero_identificador'],
                "Bco.": d['codigo_banco'],
                "NCta.": d['numero_cuenta'],
                "Plaza": d['codigo_sucursal'],
                "Monto": d['monto']
            })

        df_regente = pd.DataFrame(filas_export)
        st.metric("Suma Total Auditada", f"${suma_total:,.2f}")

        col_ex1, col_ex2 = st.columns(2)

        # Botón de descarga
        csv_data = df_regente.to_csv(index=False).encode('utf-8')
        col_ex1.download_button(
            label="⬇️ 1. Descargar Archivo para Regente",
            data=csv_data,
            file_name=f"importacion_regente_{cliente_sel.replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True
        )

        # Cierre en base de datos
        st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
        confirmar = col_ex2.checkbox("Confirmo que ya descargué el archivo CSV")
        if col_ex2.button("✅ 2. CERRAR LOTE EN BASE DE DATOS", disabled=not confirmar, type="primary", use_container_width=True):
            with st.spinner("Guardando en la nube..."):
                try:
                    # Impactamos cada cheque corregido en Supabase
                    for cid in st.session_state.cheques_listos:
                        datos_finales = st.session_state.datos_corregidos[cid].copy()
                        # Limpieza de vacíos para SQL
                        for key, value in datos_finales.items():
                            if pd.isna(value) or str(value).strip() in ["None", "<NA>", ""]:
                                datos_finales[key] = None

                        supabase.table("cobranzas_pendientes").update(datos_finales).eq("id", cid).execute()

                    st.success("¡Lote cerrado y limpiado de la bandeja con éxito!")

                    # Limpiamos la memoria para el próximo lote
                    st.session_state.cheques_listos = []
                    st.session_state.datos_corregidos = {}
                    time.sleep(1.5)
                    st.cache_data.clear()
                    st.rerun()

                except Exception as e:
                    st.error(f"Error al guardar: {e}")
        st.markdown("</div>", unsafe_allow_html=True)
```

```python
# webhook.py
import os
import time
import uuid
import json
import threading
import requests
from flask import Flask, request, jsonify
from supabase import create_client, Client
import google.generativeai as genai

# ==========================================
# 1. CREDENCIALES Y CONFIGURACIÓN (PENDIENTE DE DEFINIR VARIABLES DE ENTORNO EXACTAS)
# ==========================================
URL_SB = os.environ.get("SUPABASE_URL")
KEY_SB = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL_SB, KEY_SB)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

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

            # 2. Subir a Gemini y ESPERAR (Crucial para PDFs y Múltiples fotos)
            archivo_subido = genai.upload_file(ruta)
            while archivo_subido.state.name == 'PROCESSING':
                time.sleep(2)
                archivo_subido = genai.get_file(archivo_subido.name)
            archivos_gemini.append(archivo_subido)

        fotos_juntas = ",".join(urls_supabase)

        # 3. Prompt
        modelo = genai.GenerativeModel('gemini-2.5-pro')
        prompt = f"""
        Sos un auditor contable experto de BC Combustibles. Analizá este lote de imágenes. Cliente: '{cliente_tag}'.

        PASO 1: Observá y razoná internamente qué datos hay en las fotos.
        PASO 2: Extraé los datos.
        - REGLA 1: Si dudás, dejalo vacío (""). NO inventes.
        - REGLA 2: Para 'razon_social_emisor', buscá el texto impreso junto al CUIT. Ignorá el 'Páguese a' manuscrito.
        - REGLA 3: Para 'numero_cuenta', extraé los números crudos SIN guiones ni espacios.
        - REGLA 4: Indicá obligatoriamente a qué número de archivo/imagen corresponde este cheque en 'numero_imagen' (1 para el primer archivo enviado, 2 para el segundo, etc.).

        Devolvé ÚNICAMENTE un objeto JSON con este formato exacto:
        {{
            "cheques": [
                {{
                    "cliente_asociado": "{cliente_tag}",
                    "numero_imagen": 1,
                    "tipo_comprobante": "Cheque Físico",
                    "banco_origen": "Nombre del banco",
                    "codigo_banco": "014",
                    "codigo_sucursal": "1842",
                    "numero_cuenta": "12345678",
                    "numero_identificador": "90000052",
                    "monto": 150000.50,
                    "fecha_emision": "2026-06-10",
                    "fecha_pago": "2026-08-15",
                    "cuit_emisor": "20-12345678-9",
                    "razon_social_emisor": "Razón social impresa",
                    "estado_auditoria": "Pendiente",
                    "regente_cliente_id": "1045"
                }}
            ]
        }}
        """

        respuesta = modelo.generate_content(archivos_gemini + [prompt])

        # 4. Limpieza de JSON a prueba de balas (El mismo método robusto de lector.py)
        raw_text = respuesta.text.strip()
        start = raw_text.find('{')
        end = raw_text.rfind('}') + 1

        if start != -1 and end != 0:
            texto_json = raw_text[start:end]
            datos_ia = json.loads(texto_json)
        else:
            raise Exception("Gemini no devolvió un JSON válido para leer.")

        # 5. Formatear y vincular foto individual
        for fila in datos_ia.get("cheques", []):
            fila['lote_id'] = id_lote_unico

            num_img = fila.pop('numero_imagen', None)
            if num_img and isinstance(num_img, int) and 1 <= num_img <= len(urls_supabase):
                fila['archivo_url'] = urls_supabase[num_img - 1]
            else:
                fila['archivo_url'] = fotos_juntas # De respaldo

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
# 5. ENDPOINT WEBHOOK GREEN-API
# ==========================================
@app.route('/webhook', methods=['POST'])
def recibir_whatsapp():
    try:
        datos = request.json
        # GreenAPI puede enviar el payload directamente o dentro de 'body'
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
        # Nota: Va como IF separado para que procese la foto en el mismo mensaje que abrió el lote
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
```
</estructura_y_codigo>

<estado_actual_y_pendientes>
Estado Actual:

El panel de Streamlit está finalizado, permitiendo visualizar imágenes al 65% de ancho y corregir datos mediante un acordeón.

El motor de IA y el formateo de JSON es robusto y puede procesar lotes complejos (ej. una imagen conteniendo múltiples cheques).

El Webhook procesa comandos en texto plano o incrustados como epígrafes (captions) en las imágenes.

Bug Crítico y Pendiente (Punto de pausa de hoy):
Existe un bloqueo a nivel de hardware/software en el teléfono físico (host) que soporta la instancia de Green-API. Al enviar imágenes (formato .jpg) en grupos de WhatsApp, el teléfono no las descarga automáticamente, dejándolas en estado "borroso". Como resultado, Green-API no obtiene el archivo y el atributo downloadUrl no se genera o el bot no reacciona al adjunto.

Trabajos intentados y descartados:

Limpieza de memoria, borrado de caché de WhatsApp y reinicio del teléfono.

Revisión de permisos de almacenamiento.

Envío de imágenes en formato documento PDF (funciona perfectamente y el bot lo procesa, pero fue descartado porque el usuario indicó que dificulta la operatoria de los playeros).

Próximo Paso (Pendiente de definir mañana):
Encontrar una solución definitiva, configuración o workaround técnico (fuera de la conversión manual a PDF por parte de los playeros) para forzar al dispositivo host de Green-API a descargar las imágenes estándar enviadas a los grupos de WhatsApp, logrando que el flujo sea transparente para los operadores en pista.
</estado_actual_y_pendientes>
