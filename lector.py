import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os # Nuevo: para verificar si está el logo

# ==========================================
# 1. CONFIGURACIÓN VISUAL Y DE PÁGINA
# ==========================================
# Definimos los colores de BC Combustibles (aproximados de la captura)
COLOR_ROJO = "#C8102E"  # Rojo BC
COLOR_DORADO = "#FFD700" # Gota dorada
COLOR_FONDO_AZUL = "#F0F8FF" # Azul clarito de fondo

st.set_page_config(
    page_title="BC Combustibles - Gestión",
    page_icon="⛽", # O podés poner la gota dorada si tenés el emoji
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- ESTILOS CSS PERSONALIZADOS (El "Maquillaje") ---
st.markdown(f"""
    <style>
        /* Pintamos los títulos principales de Rojo */
        h1, h2, h3 {{
            color: {COLOR_ROJO} !important;
            font-family: 'Montserrat', sans-serif;
        }}
        
        /* Estilo para los botones principales */
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
        
        /* Fondo de la barra lateral */
        [data-testid="stSidebar"] {{
            background-color: white;
            border-right: 2px solid {COLOR_FONDO_AZUL};
        }}
        
        /* Ajuste de tipografía general */
        .stApp {{
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        }}
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 2. BARRA LATERAL CON LOGO
# ==========================================
st.sidebar.markdown("<br>", unsafe_allow_html=True) # Espacio arriba

# Intentamos cargar el logo si existe en el repo
if os.path.exists("logo.png"):
    # Usamos columnas para centrarlo un poco
    col_logo1, col_logo2, col_logo3 = st.sidebar.columns([1, 2, 1])
    with col_logo2:
        st.image("logo.png", use_container_width=True)
else:
    # Si no está el logo, ponemos el nombre en grande
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

st.sidebar.markdown(f"<h3 style='text-align: center;'>Panel de Gestión</h3>", unsafe_allow_html=True)
st.sidebar.divider()

opcion = st.sidebar.radio(
    "Seleccioná tarea:",
    ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"],
    key="menu_principal"
)

# Espacio publicitario/institucional abajo en el menú
st.sidebar.v_spacer(height=100)
st.sidebar.info("Combustibles diseñados para rendir. Calidad garantizada.")


# ==========================================
# 3. LÓGICA DEL SISTEMA (Lo de ayer, intacto)
# ==========================================
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

# --- SECCIÓN: VENTAS A CAMIONES ---
if "Ventas a Camiones" in opcion:
    st.title("🚛 Registro de Resumen de Carga")
    st.write("Herramienta exclusiva para la administración de BC Combustibles.")
    
    # ... (Aquí va EXACTAMENTE EL MISMO CÓDIGO de lógica que teníamos ayer para esta sección) ...
    # ... (Cargadores de fotos, botón Analizar, tabla, descarga CSV, etc.) ...
    
    # NOTA PARA DIEGO: Para no hacer este mensaje gigante, no pegué la lógica de ayer.
    # Simplemente asegurate de pegar el código lógico que ya tenías dentro de este IF.
    st.warning("Falta pegar aquí la lógica de procesamiento de fotos de ayer.")


# --- SECCIÓN: PROVEEDORES ---
elif "Facturas de Proveedores" in opcion:
    st.title("📄 Carga de Facturas de Proveedores")
    # ... (Aquí va la lógica original de proveedores) ...
    st.warning("Falta pegar aquí la lógica de proveedores original.")
