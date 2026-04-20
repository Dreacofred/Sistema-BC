import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os

# ==========================================
# 1. ESTILO CORPORATIVO BC
# ==========================================
COLOR_ROJO = "#C8102E"
st.set_page_config(page_title="BC Combustibles - Gestión", layout="wide")

st.markdown(f"""
    <style>
        .stApp {{ background-color: white !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; }}
        .stButton>button {{ background-color: {COLOR_ROJO}; color: white; border-radius: 20px; font-weight: bold; width: 100%; }}
        [data-testid="stFileUploader"] button {{ background-color: {COLOR_ROJO} !important; color: white !important; }}
        [data-testid="stSidebar"] {{ background-color: white; border-right: 2px solid #F0F8FF; }}
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
# 3. LÓGICA DE PROCESAMIENTO
# ==========================================
# Quitamos cualquier configuración de versión y dejamos que el cliente elija la mejor vía
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

if "Ventas a Camiones" in opcion:
    st.title("🚛 Registro de Carga")
    f_factura = st.file_uploader("1. Foto Factura", type=["jpg", "png", "jpeg"], key="f1")
    f_orden = st.file_uploader("2. Foto Orden (Opcional)", type=["jpg", "png", "jpeg"], key="f2")

    if f_factura and st.button("🔍 Analizar Venta"):
        with st.spinner("Procesando datos..."):
            try:
                # Cargamos las imágenes
                img_f = Image.open(f_factura)
                material = [img_f]
                if f_orden:
                    material.append(Image.open(f_orden))
                
                # Pedimos el JSON. Usamos 'gemini-1.5-flash' a secas, sin prefijos.
                prompt = "Sos un experto administrativo. Extraé: fecha, chofer, cliente, litros, importe_total, efectivo, nro_factura, nro_orden. Devolvé SOLO un JSON. Si el efectivo es nulo poné 0.0."
                
                # Este método es el más robusto de la librería genai
                res = cliente.models.generate_content(
                    model='gemini-1.5-flash', 
                    contents=[prompt] + material
                )
                
                # Limpieza de texto por si la IA devuelve markdown
                clean_text = res.text.strip().replace('```json', '').replace('```', '')
                st.session_state.resumen_ventas.append(json.loads(clean_text))
                st.success("¡Venta registrada!")
                
            except Exception as e:
                st.error(f"Hubo un problema al leer las fotos: {e}")

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Reporte (Excel)", data=csv, file_name="reporte_bc.csv")
        if st.button("🗑️ Limpiar Tabla"):
            st.session_state.resumen_ventas = []
            st.rerun()

elif "Facturas de Proveedores" in opcion:
    st.title("📄 Proveedores")
    archivo = st.file_uploader("Subir factura", type=["pdf", "png", "jpg", "jpeg"])
    if archivo and st.button("🚀 Extraer Datos"):
        with st.spinner("Analizando..."):
            try:
                mat = Image.open(archivo) if not archivo.name.lower().endswith('.pdf') else PdfReader(archivo).pages[0].extract_text()
                res = cliente.models.generate_content(model='gemini-1.5-flash', contents=["Extraé datos de esta factura en JSON puro", mat])
                st.code(res.text)
            except Exception as e:
                st.error(f"Error: {e}")
