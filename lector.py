import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os

# ==========================================
# 1. CONFIGURACIÓN VISUAL Y DE PÁGINA
# ==========================================
COLOR_ROJO = "#C8102E"
COLOR_DORADO = "#FFD700"
COLOR_FONDO_AZUL = "#F0F8FF"

st.set_page_config(page_title="BC Combustibles - Gestión", page_icon="⛽", layout="wide")

st.markdown(f"""
    <style>
        .stApp {{ background-color: white !important; }}
        p, span, div {{ color: #333333; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; }}
        .stButton>button {{
            background-color: {COLOR_ROJO}; color: white; border-radius: 20px; font-weight: bold;
        }}
        [data-testid="stFileUploader"] button {{
            background-color: {COLOR_ROJO} !important; border-radius: 20px !important;
        }}
        [data-testid="stFileUploader"] button * {{
            color: white !important; font-weight: bold !important;
        }}
        [data-testid="stSidebar"] {{ background-color: white; border-right: 2px solid {COLOR_FONDO_AZUL}; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. BARRA LATERAL
# ==========================================
st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo:
    st.sidebar.image(ruta_logo, use_container_width=True)
else:
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

opcion = st.sidebar.radio("Seleccioná tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])

# ==========================================
# 3. LÓGICA (MODELO PRO PARA EVITAR ERRORES)
# ==========================================
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

if "Ventas a Camiones" in opcion:
    st.title("🚛 Registro de Carga")
    
    f_factura = st.file_uploader("1. Foto Factura", type=["jpg", "png", "jpeg"], key="f1")
    f_orden = st.file_uploader("2. Foto Orden (Opcional)", type=["jpg", "png", "jpeg"], key="f2")

    if f_factura and st.button("🔍 Analizar Venta", use_container_width=True):
        with st.spinner("La IA (Versión Pro) está analizando..."):
            try:
                material = [Image.open(f_factura)]
                if f_orden: material.append(Image.open(f_orden))
                
                prompt = "Extraé datos en JSON: fecha, chofer, cliente, litros, importe_total, efectivo, nro_factura, nro_orden. Si el efectivo está tachado poné 0.0. Devolvé SOLO el JSON, nada de texto extra."
                
                # MODELO PRO: Más lento pero más estable ante saturación
                res = cliente.models.generate_content(model='gemini-1.5-pro', contents=[prompt] + material)
                
                texto = res.text.replace("```json", "").replace("```", "").strip()
                st.session_state.resumen_ventas.append(json.loads(texto))
                st.success("¡Venta agregada!")
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Excel", data=csv, file_name="resumen.csv")
        if st.button("🗑️ Borrar Todo"):
            st.session_state.resumen_ventas = []
            st.rerun()

elif "Facturas de Proveedores" in opcion:
    st.title("📄 Proveedores")
    archivo = st.file_uploader("Subir factura", type=["pdf", "png", "jpg", "jpeg"])
    if archivo and st.button("🚀 Extraer"):
        with st.spinner("Analizando..."):
            try:
                mat = Image.open(archivo) if not archivo.name.endswith('.pdf') else PdfReader(archivo).pages[0].extract_text()
                res = cliente.models.generate_content(model='gemini-1.5-pro', contents=["Extraé datos de esta factura en JSON puro", mat])
                st.code(res.text)
            except Exception as e:
                st.error(f"Error: {e}")
