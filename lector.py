import streamlit as st
import google.generativeai as genai # Cambiamos la forma de importar
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os

# ==========================================
# 1. CONFIGURACIÓN VISUAL
# ==========================================
COLOR_ROJO = "#C8102E"
COLOR_DORADO = "#FFD700"
COLOR_FONDO_AZUL = "#F0F8FF"

st.set_page_config(page_title="BC Combustibles - Gestión", layout="wide")

st.markdown(f"""
    <style>
        .stApp {{ background-color: white !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; }}
        .stButton>button {{ background-color: {COLOR_ROJO}; color: white; border-radius: 20px; font-weight: bold; width: 100%; }}
        [data-testid="stFileUploader"] button {{ background-color: {COLOR_ROJO} !important; color: white !important; font-weight: bold !important; }}
        [data-testid="stSidebar"] {{ background-color: white; border-right: 2px solid {COLOR_FONDO_AZUL}; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. BARRA LATERAL
# ==========================================
st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo: st.sidebar.image(ruta_logo, use_container_width=True)
else: st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

opcion = st.sidebar.radio("Seleccioná tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])

# ==========================================
# 3. CONEXIÓN A GOOGLE (MÉTODO ESTABLE)
# ==========================================
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-pro')

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

if "Ventas a Camiones" in opcion:
    st.title("🚛 Registro de Carga")
    f_factura = st.file_uploader("1. Foto Factura", type=["jpg", "png", "jpeg"], key="f1")
    f_orden = st.file_uploader("2. Foto Orden (Opcional)", type=["jpg", "png", "jpeg"], key="f2")

    if f_factura and st.button("🔍 Analizar Venta"):
        with st.spinner("Analizando con IA Pro..."):
            try:
                img_f = Image.open(f_factura)
                material = [img_f]
                if f_orden: material.append(Image.open(f_orden))
                
                prompt = "Extraé datos en JSON puro: fecha, chofer, cliente, litros, importe_total, efectivo, nro_factura, nro_orden. Si el efectivo está tachado poné 0.0."
                
                res = model.generate_content([prompt] + material)
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
                res = model.generate_content(["Extraé datos de esta factura en JSON puro", mat])
                st.code(res.text)
            except Exception as e:
                st.error(f"Error: {e}")
