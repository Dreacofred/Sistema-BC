import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os

# ==========================================
# 1. IDENTIDAD CORPORATIVA BC COMBUSTIBLES
# ==========================================
COLOR_ROJO = "#C8102E"

st.set_page_config(
    page_title="BC Combustibles - Gestión Pro",
    page_icon="⛽",
    layout="wide"
)

# Estilo profesional para la interfaz
st.markdown(f"""
    <style>
        .stApp {{ background-color: white !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; }}
        .stButton>button {{
            background-color: {COLOR_ROJO};
            color: white;
            border-radius: 12px;
            font-weight: bold;
            height: 3em;
            border: none;
        }}
        [data-testid="stSidebar"] {{ background-color: #f8f9fa; border-right: 1px solid #e0e0e0; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. PANEL LATERAL
# ==========================================
st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo:
    st.sidebar.image(ruta_logo, use_container_width=True)
else:
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

opcion = st.sidebar.radio("Seleccioná la tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])
st.sidebar.divider()
st.sidebar.success("💎 NIVEL: GEMINI 1.5 PRO (PAGO ACTIVO)")

# ==========================================
# 3. CONEXIÓN PRO (VERSIÓN ESTABLE V1)
# ==========================================
# Configuración blindada para evitar errores de conexión
cliente = genai.Client(
    api_key=st.secrets["GEMINI_API_KEY"],
    http_options={'api_version': 'v1'}
)

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

if "Ventas a Camiones" in opcion:
    st.title("🚛 Registro de Carga de Camiones")
    
    f_factura = st.file_uploader("1. Foto Factura", type=["jpg", "png", "jpeg"], key="f1")
    f_orden = st.file_uploader("2. Foto Orden (Opcional)", type=["jpg", "png", "jpeg"], key="f2")

    if f_factura and st.button("🔍 ANALIZAR CON IA PRO", use_container_width=True):
        with st.spinner("Procesando con la máxima precisión..."):
            try:
                img_f = Image.open(f_factura)
                material = [img_f]
                if f_orden: material.append(Image.open(f_orden))
                
                prompt = """Sos un experto administrativo. Extraé: fecha, chofer, cliente, litros, importe_total, efectivo, nro_factura, nro_orden. 
                Si el efectivo está tachado o no figura, poné 0.0. 
                Devolvé ÚNICAMENTE un objeto JSON puro."""
                
                # MODELO 1.5-PRO ACTIVO
                res = cliente.models.generate_content(
                    model='gemini-1.5-pro', 
                    contents=[prompt] + material
                )
                
                # Limpieza de respuesta para asegurar que la tabla no se rompa
                txt = res.text.strip().replace('```json', '').replace('```', '')
                inicio = txt.find('{')
                fin = txt.rfind('}') + 1
                datos = json.loads(txt[inicio:fin])
                
                st.session_state.resumen_ventas.append(datos)
                st.success("¡Venta cargada correctamente en la planilla!")
            except Exception as e:
                st.error(f"Error en la lectura: {e}")

    if st.session_state.resumen_ventas:
        st.divider()
        st.subheader("📋 Planilla Acumulada")
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Excel para la Estación", data=csv, file_name="planilla_bc_pro.csv")
        
        if st.button("🗑️ Borrar Planilla y Reiniciar"):
            st.session_state.resumen_ventas = []
            st.rerun()

elif "Facturas de Proveedores" in opcion:
    st.title("📄 Proveedores")
    archivo = st.file_uploader("Subir factura", type=["pdf", "png", "jpg", "jpeg"])
    if archivo and st.button("🚀 Extraer Datos con Pro"):
        with st.spinner("Analizando con motor Pro..."):
            try:
                if archivo.name.lower().endswith('.pdf'):
                    mat = PdfReader(archivo).pages[0].extract_text()
                else:
                    mat = Image.open(archivo)
                
                res = cliente.models.generate_content(model='gemini-1.5-pro', contents=["Extraé datos de esta factura en JSON puro", mat])
                st.code(res.text)
            except Exception as e:
                st.error(f"Error: {e}")
