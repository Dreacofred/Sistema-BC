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

st.set_page_config(
    page_title="BC Combustibles - Gestión",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
    <style>
        .stApp {{
            background-color: white !important;
        }}
        p, span, div {{
            color: #333333;
        }}
        h1, h2, h3 {{
            color: {COLOR_ROJO} !important;
            font-family: 'Montserrat', sans-serif;
        }}
        .stButton>button {{
            background-color: {COLOR_ROJO};
            color: white;
            border-radius: 20px;
            border: none;
            font-weight: bold;
            transition: all 0.3s;
        }}
        .stButton>button:hover {{
            background-color: {COLOR_DORADO};
            color: black;
            transform: scale(1.05);
        }}
        [data-testid="stFileUploader"] button {{
            background-color: {COLOR_ROJO} !important;
            border-radius: 20px !important;
            border: none !important;
        }}
        [data-testid="stFileUploader"] button,
        [data-testid="stFileUploader"] button * {{
            color: white !important;
            fill: white !important;
            font-weight: bold !important;
        }}
        [data-testid="stSidebar"] {{
            background-color: white;
            border-right: 2px solid {COLOR_FONDO_AZUL};
        }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. BARRA LATERAL CON LOGO Y MENÚ
# ==========================================
st.sidebar.markdown("<br>", unsafe_allow_html=True)

ruta_logo = None
for variante in ["Logo.jpeg", "Logo.jpg", "logo.jpeg", "logo.jpg", "logo.png"]:
    if os.path.exists(variante):
        ruta_logo = variante
        break

if ruta_logo:
    col_logo1, col_logo2, col_logo3 = st.sidebar.columns([1, 2, 1])
    with col_logo2:
        st.image(ruta_logo, use_container_width=True)
else:
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

st.sidebar.markdown(f"<h3 style='text-align: center;'>Panel de Gestión</h3>", unsafe_allow_html=True)
st.sidebar.divider()

opcion = st.sidebar.radio(
    "Seleccioná tarea:",
    ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"],
    key="menu_principal"
)

st.sidebar.markdown("<br><br><br><br>", unsafe_allow_html=True)
st.sidebar.info("Combustibles diseñados para rendir. Calidad garantizada.")

# ==========================================
# 3. LÓGICA DEL SISTEMA
# ==========================================
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

if "Ventas a Camiones" in opcion:
    st.title("🚛 Registro de Resumen de Carga")
    st.write("Herramienta exclusiva para la administración de BC Combustibles.")
    
    col1, col2 = st.columns(2)
    with col1:
        f_factura = st.file_uploader("1. Foto Factura (Obligatorio)", type=["jpg", "png", "jpeg"], key="f1")
    with col2:
        f_orden = st.file_uploader("2. Foto Orden Manual (Opcional)", type=["jpg", "png", "jpeg"], key="f2")

    if f_factura:
        if st.button("🔍 Analizar Venta", use_container_width=True):
            with st.spinner("La IA está leyendo los datos..."):
                try:
                    img_factura = Image.open(f_factura)
                    cosas_para_ia = [img_factura] 

                    if f_orden:
                        img_orden = Image.open(
