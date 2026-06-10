import streamlit as st
import json
import tempfile
import os
import time
from supabase import create_client, Client
import google.generativeai as genai

# ==========================================
# 1. CREDENCIALES
# ==========================================
URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

supabase: Client = create_client(URL_SB, KEY_SB)
genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. ENCABEZADOS
# ==========================================
st.title("🤖 Laboratorio IA - Auditoría de Cobranzas")
st.markdown("Esta pantalla usa **Gemini 2.5 Pro** para leer y extraer datos reales de los comprobantes y guardarlos en la nube.")
st.markdown("---")

# ==========================================
# 3. MOTOR IA (GEMINI 2.5 PRO)
# ==========================================
def leer_documento_con_ia(archivo_subido, cliente_tag):
    extension = os.path.splitext(archivo_subido.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp_file:
        tmp_file.write(archivo_subido.getvalue())
        tmp_path = tmp_file.name

    try:
        archivo_gemini = genai.upload_file(tmp_path)
        modelo = genai.GenerativeModel('gemini-2.5-pro')
        
        prompt = f"""
        Sos un auditor contable experto. Analizá este comprobante de pago/cheque/depósito recibido del cliente '{cliente_tag}'.
        Extraé la información solicitada y devolvé ÚNICAMENTE un array de objetos JSON con esta estructura exacta (sin formato markdown adicional ni texto previo/posterior):
        [{{
            "cliente_asociado": "{cliente_tag}",
            "tipo_comprobante": "Echeq Emisión" | "Echeq Endoso" | "Transferencia" | "Depósito SICE",
            "banco_origen": "Nombre del banco de origen",
            "numero_identificador": "Nro de cheque o Nro de comprobante",
            "monto": "Solo el numero decimal (ej: 1410435.78)",
            "fecha_pago": "YYYY-MM-DD",
            "cuit_emisor": "CUIT del emisor original o endosante",
            "firma_destino": "BC Combustibles SA" | "Florencia Bonazzola" | "Ricardo Buyatti",
            "estado_auditoria": "Pendiente",
            "regente_cliente_id": "1045"
        }}]
        Si un dato no aparece, dejalo como un string vacío "". El monto debe ser numérico.
        """
        
        respuesta = modelo.generate_content([archivo_gemini, prompt])
        
        genai.delete_file(archivo_gemini.name)
        os.remove(tmp_path)
        
        texto_json = respuesta.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_json)

    except Exception as e:
        st.error(f"Error procesando con IA: {e}")
        os.remove(tmp_path)
        return None

# ==========================================
# 4. INTERFAZ VISUAL Y GUARDADO
# ==========================================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📥 1. Ingreso de Datos")
    cliente_input = st.text_input("Etiqueta del Cliente (Ej: Fochesatto)", value="Fochesatto")
    archivo = st.file_uploader("Subir foto o PDF del cheque", type=['png', 'jpeg', 'jpg', 'pdf'])

    if archivo and st.button("🧠 Procesar y Leer con IA"):
        with st.spinner("Gemini está analizando el documento..."):
            datos_extraidos = leer_documento_con_ia(archivo, cliente_input)
            
            if datos_extraidos:
                st.session_state['datos_ia'] = datos_extraidos
                st.success("¡Lectura exitosa!")

with col2:
    st.subheader("📋 2. Auditoría y Guardado")
    
    if 'datos_ia' in st.session_state:
        st.write("Verificá los datos extraídos por Gemini:")
        datos_editados = st.data_editor(st.session_state['datos_ia'])
        
        if st.button("✅ Aprobar y Enviar a Supabase"):
            with st.spinner("Subiendo archivo y guardando en la base de datos..."):
                try:
                    # 1. Armamos un nombre único
                    timestamp = int(time.time())
                    nombre_archivo = f"{timestamp}_{archivo.name}"
                    
                    # 2. Subimos el archivo físico al Storage
                    supabase.storage.from_("comprobantes").upload(
                        path=nombre_archivo,
                        file=archivo.getvalue(),
                        file_options={"content-type": archivo.type}
                    )
                    
                    # 3. Le pedimos a Supabase el link público
                    url_publica = supabase.storage.from_("comprobantes").get_public_url(nombre_archivo)
                    
                    # 4. Inyectamos la URL real en los datos
                    for fila in datos_editados:
                        fila['archivo_url'] = url_publica
                        
                    # 5. Insertamos en la tabla
                    respuesta = supabase.table("cobranzas_pendientes").insert(datos_editados).execute()
                    
                    st.success("¡Archivo subido y base de datos actualizada perfectamente!")
                    st.balloons()
                    del st.session_state['datos_ia']
                    
                except Exception as e:
                    st.error(f"Error al subir el archivo o guardar los datos: {e}")
