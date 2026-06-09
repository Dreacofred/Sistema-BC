import streamlit as st
import json
from supabase import create_client, Client

# ==========================================
# 1. CONEXIÓN A SUPABASE
# ==========================================
# Idealmente, traé esto de st.secrets en producción
SUPABASE_URL = "TU_URL_DE_SUPABASE"
SUPABASE_KEY = "TU_SERVICE_ROLE_KEY" # Usar la Service Role para ignorar el RLS interno
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(page_title="Laboratorio IA - Cobranzas", layout="wide")
st.title("🤖 Laboratorio IA - Auditoría de Cobranzas")
st.markdown("Esta pantalla es un entorno de prueba para validar que la IA lee bien y que Supabase guarda perfecto.")
st.markdown("---")

# ==========================================
# 3. MOTOR DE IA (Simulado para la primera prueba)
# ==========================================
def leer_documento_con_ia(cliente_tag):
    """
    Acá irá la conexión real a la API de la IA. 
    Por ahora, para probar que el 'caño' hasta Supabase funciona, 
    devolvemos un JSON simulando la lectura perfecta del Echeq del Santander.
    """
    return [{
        "cliente_asociado": cliente_tag,
        "tipo_comprobante": "Echeq Emisión",
        "banco_origen": "Santander",
        "numero_identificador": "16226837",
        "monto": 865432.20,
        "fecha_pago": "2026-07-13",
        "cuit_emisor": "30-70783721-3",
        "firma_destino": "BC Combustibles SA",
        "archivo_url": "https://ejemplo.com/cheque_temporal.jpg", # Luego será tu Supabase Storage
        "estado_auditoria": "Pendiente",
        "regente_cliente_id": "1045" # El código de cliente simulado para Regente
    }]

# ==========================================
# 4. INTERFAZ VISUAL
# ==========================================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📥 1. Ingreso de Datos")
    cliente_input = st.text_input("Etiqueta del Cliente (Ej: Fochesatto)", value="Fochesatto")
    archivo_subido = st.file_uploader("Subir foto o PDF del cheque", type=['png', 'jpeg', 'jpg', 'pdf'])

    if archivo_subido and st.button("🧠 Procesar y Leer con IA"):
        with st.spinner("La IA está escaneando los píxeles..."):
            # Llamamos a nuestro motor
            datos_extraidos = leer_documento_con_ia(cliente_input)
            
            # Lo guardamos en la memoria temporal de Streamlit
            st.session_state['datos_ia'] = datos_extraidos
            st.success("¡Lectura exitosa!")

with col2:
    st.subheader("📋 2. Auditoría y Guardado")
    
    # Si la IA ya procesó algo, lo mostramos
    if 'datos_ia' in st.session_state:
        st.write("Verificá los datos antes de inyectarlos a Supabase:")
        
        # Mostramos los datos en una tabla editable nativa de Streamlit
        datos_editados = st.data_editor(st.session_state['datos_ia'])
        
        if st.button("✅ Aprobar y Enviar a Supabase"):
            with st.spinner("Guardando en la base de datos..."):
                try:
                    # Inserción directa en la tabla que creaste recién
                    respuesta = supabase.table("cobranzas_pendientes").insert(datos_editados).execute()
                    st.success("¡Guardado en Supabase perfectamente! Revisá tu base de datos.")
                    st.balloons() # Festejo en pantalla
                    
                    # Limpiamos la pantalla
                    del st.session_state['datos_ia']
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
