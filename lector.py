import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os

# ==========================================
# 1. CONFIGURACIÓN E IDENTIDAD
# ==========================================
COLOR_ROJO = "#C8102E"

st.set_page_config(
    page_title="BC Combustibles - Gestión Pro",
    page_icon="⛽",
    layout="wide"
)

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
            width: 100%;
        }}
        [data-testid="stSidebar"] {{ background-color: #f8f9fa; border-right: 1px solid #e0e0e0; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. INICIALIZACIÓN DE CLIENTE Y ESTADOS
# ==========================================
# Asegúrate de tener GEMINI_API_KEY en tus Secrets de Streamlit
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []
if 'datos_temp' not in st.session_state:
    st.session_state.datos_temp = None

# Sidebar
st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo:
    st.sidebar.image(ruta_logo, use_container_width=True)
else:
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC COMBUSTIBLES</h1>", unsafe_allow_html=True)

opcion = st.sidebar.radio("Seleccioná la tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])
st.sidebar.divider()
st.sidebar.info("Sistema v2.5 - Cruce de Datos Factura/Orden")

# ==========================================
# 3. MÓDULO: VENTAS A CAMIONES (Lógica Dual)
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title("🚛 Registro de Carga de Camiones")
    
    col_f, col_o = st.columns(2)
    with col_f:
        f_factura = st.file_uploader("1. Subir FACTURA (Imagen o PDF)", type=["jpg", "png", "jpeg", "pdf"])
    with col_o:
        f_orden = st.file_uploader("2. Subir PAPEL DE CARGA (Imagen)", type=["jpg", "png", "jpeg"])

    if f_factura and f_orden:
        if st.button("🔍 ANALIZAR Y CRUZAR DOCUMENTOS"):
            with st.spinner("Leyendo Factura y Papel de Carga..."):
                try:
                    # Preparar archivos para Gemini
                    img_orden = Image.open(f_orden)
                    if f_factura.name.lower().endswith('.pdf'):
                        reader = PdfReader(f_factura)
                        txt_f = "\n".join([p.extract_text() for p in reader.pages[:1]])
                        doc_factura = f"Contenido de la factura: {txt_f}"
                    else:
                        doc_factura = Image.open(f_factura)

                    prompt = """
                    Generá un JSON puro analizando ambos documentos:
                    1. DEL PAPEL DE CARGA: fecha, entidad_pagadora, chofer, orden_litros, efectivo, orden_efectivo.
                    2. DE LA FACTURA: razon_social, litros_factura, importe, nro_factura.
                    Si no hay efectivo, usá 0.0. Devolvé solo el JSON.
                    """
                    
                    res = cliente.models.generate_content(
                        model='gemini-2.5-pro',
                        contents=[prompt, doc_factura, img_orden]
                    )
                    
                    # Limpieza del texto JSON
                    raw = res.text.strip().replace('```json', '').replace('```', '')
                    st.session_state.datos_temp = json.loads(raw[raw.find('{'):raw.rfind('}')+1])
                    st.success("¡Datos extraídos con éxito!")
                except Exception as e:
                    st.error(f"Error en el análisis: {e}")

    # Formulario de validación (Orden de columnas solicitado)
    if st.session_state.datos_temp:
        with st.form("validador_final"):
            st.subheader("📝 Verificación de Datos")
            
            # Fila 1: Datos principales
            c1, c2, c3 = st.columns([1, 1.5, 2])
            fecha = c1.text_input("Fecha", st.session_state.datos_temp.get('fecha', ''))
            chofer = c2.text_input("Chofer", st.session_state.datos_temp.get('chofer', ''))
            cliente_rs = c3.text_input("Cliente (Razón Social)", st.session_state.datos_temp.get('razon_social', ''))
            
            # Fila 2: Valores
            c4, c5, c6, c7 = st.columns(4)
            litros = c4.number_input("Litros (Factura)", value=float(st.session_state.datos_temp.get('litros_factura', 0.0)))
            importe = c5.number_input("Importe", value=float(st.session_state.datos_temp.get('importe', 0.0)))
            factura_n = c6.text_input("Factura", st.session_state.datos_temp.get('nro_factura', ''))
            entidad = c7.text_input("Entidad pagadora", st.session_state.datos_temp.get('entidad_pagadora', ''))
            
            # Fila 3: Datos de control de orden
            with st.exp
