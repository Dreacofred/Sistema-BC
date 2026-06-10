import streamlit as st
import json
import tempfile
import os
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
st.markdown("Esta pantalla usa **Gemini 1.5 Pro** para leer y extraer datos reales de los comprobantes.")
st.markdown("---")

# ==========================================
# 3. MOTOR IA (GEMINI 1.5 PRO REAL)
# ==========================================
def leer_documento_con_ia(archivo_subido, cliente_tag):
    # Gemini necesita que el archivo esté guardado temporalmente para leerlo
    extension = os.path.splitext(archivo_subido.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp_file:
        tmp_file.write(archivo_subido.getvalue())
        tmp_path = tmp_file.name

    try:
        # Subimos el documento temporal al cerebro de Gemini
        archivo_gemini = genai.upload_file(tmp_path)
        
        # Invocamos al modelo estrella
        modelo = genai.GenerativeModel('gemini-1.5-pro')
        
        # El "Prompt" que entrena a la IA sobre cómo trabajamos
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
        
        # Disparamos la consulta
        respuesta = modelo.generate_content([archivo_gemini, prompt])
        
        # Limpiamos los archivos temporales para no ocupar espacio
        genai.delete_file(archivo_gemini.name)
        os.remove(tmp_path)
        
        # Limpiamos la respuesta de la IA para que sea 100% código JSON puro
        texto_json = respuesta.text.replace("```json", "").replace("```", "").strip()
        
        return json.loads(texto_json)

    except Exception as e:
        st.error(f"Error procesando con IA: {e}")
        os.remove(tmp_path)
        return None

# ==========================================
# 4. INTERFAZ VISUAL
# ==========================================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📥 1. Ingreso de Datos")
    cliente_input = st.text_input("Etiqueta del Cliente (Ej: Fochesatto)", value="Fochesatto")
    archivo = st.file_uploader("Subir foto o PDF del cheque", type=['png', 'jpeg', 'jpg', 'pdf'])

    if archivo and st.button("🧠 Procesar y Leer con IA"):
        with st.spinner("Gemini está analizando el documento..."):
            # Llamamos a nuestro motor inteligente
            datos_extraidos = leer_documento_con_ia(archivo, cliente_input)
            
            if datos_extraidos:
                st.session_state['datos_ia'] = datos_extraidos
                st.success("¡Lectura exitosa!")

with col2:
    st.subheader("📋 2. Auditoría y Guardado")
    
    if 'datos_ia' in st.session_state:
        st.write("Verificá los datos extraídos por Gemini:")
        
        # Mostramos los datos reales en pantalla
        datos_editados = st.data_editor(st.session_state['datos_ia'])
        
        if st.button("✅ Aprobar y Enviar a Supabase"):
            with st.spinner("Guardando en la base de datos..."):
                try:
                    # Rellenamos temporalmente el campo de la URL del archivo
                    # (Esto lo programaremos más adelante para que se suba a tu Storage)
                    for fila in datos_editados:
                        fila['archivo_url'] = "Pendiente_de_subida"
                        
                    respuesta = supabase.table("cobranzas_pendientes").insert(datos_editados).execute()
                    st.success("¡Guardado en Supabase perfectamente!")
                    st.balloons()
                    del st.session_state['datos_ia']
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
