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

# Estilo profesional personalizado
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
        .stDataFrame {{ border: 1px solid #e0e0e0; border-radius: 8px; }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONFIGURACIÓN Y CLIENTE API
# ==========================================
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
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

opcion = st.sidebar.radio("Seleccioná la tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])
st.sidebar.divider()
st.sidebar.info("Sistema de Gestión v2.0 - Gemini 2.5 Pro")

# ==========================================
# 3. MÓDULO: VENTAS A CAMIONES
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title("🚛 Registro de Carga de Camiones")
    st.markdown("Subí ambos documentos para cruzar la información automáticamente.")

    col_files = st.columns(2)
    with col_files[0]:
        f_factura = st.file_uploader("1. Factura (Imagen o PDF)", type=["jpg", "png", "jpeg", "pdf"], key="u_factura")
    with col_files[1]:
        f_orden = st.file_uploader("2. Papel de Carga / Orden", type=["jpg", "png", "jpeg"], key="u_orden")

    if f_factura and f_orden:
        if st.button("🔍 ANALIZAR DOCUMENTOS"):
            with st.spinner("Gemini analizando y cruzando datos..."):
                try:
                    # Preparación de imágenes para la IA
                    img_factura = Image.open(f_factura) if not f_factura.name.lower().endswith('.pdf') else f_factura
                    img_orden = Image.open(f_orden)
                    
                    prompt = """
                    Actuá como un experto contable de estación de servicio. Analizá estos dos documentos y generá un JSON puro.
                    
                    REGLAS DE EXTRACCIÓN:
                    1. Del PAPEL DE CARGA (Orden): Extraé 'fecha', 'entidad_pagadora', 'chofer'.
                    2. De la FACTURA: Extraé 'razon_social', 'litros' (número), 'importe' (número) y 'nro_factura'.
                    
                    Si hay datos de efectivo en el papel de carga, incluyelos en el análisis.
                    Devolvé SOLAMENTE el objeto JSON sin texto adicional.
                    """
                    
                    res = cliente.models.generate_content(
                        model='gemini-2.5-pro',
                        contents=[prompt, img_factura, img_orden]
                    )
                    
                    # Limpieza del JSON
                    raw_text = res.text.strip().replace('```json', '').replace('```', '')
                    start = raw_text.find('{')
                    end = raw_text.rfind('}') + 1
                    st.session_state.datos_temp = json.loads(raw_text[start:end])
                    
                except Exception as e:
                    st.error(f"Error en el procesamiento: {e}")

    # Formulario de validación
    if st.session_state.datos_temp:
        st.divider()
        with st.form("validador_ventas"):
            st.subheader("📝 Confirmar datos extraídos")
            
            c1, c2, c3 = st.columns([1, 1.5, 1.5])
            v_fecha = c1.text_input("Fecha", st.session_state.datos_temp.get('fecha', ''))
            v_chofer = c2.text_input("Chofer", st.session_state.datos_temp.get('chofer', ''))
            v_cliente = c3.text_input("Cliente (Razón Social)", st.session_state.datos_temp.get('razon_social', ''))
            
            c4, c5, c6, c7 = st.columns(4)
            v_litros = c4.number_input("Litros", value=float(st.session_state.datos_temp.get('litros', 0.0)))
            v_importe = c5.number_input("Importe", value=float(st.session_state.datos_temp.get('importe', 0.0)))
            v_factura = c6.text_input("Factura Nro", st.session_state.datos_temp.get('nro_factura', ''))
            v_entidad = c7.text_input("Entidad pagadora", st.session_state.datos_temp.get('entidad_pagadora', ''))
            
            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                registro = {
                    "Fecha": v_fecha,
                    "Chofer": v_chofer,
                    "Cliente": v_cliente,
                    "Litros": v_litros,
                    "Importe": v_importe,
                    "Factura": v_factura,
                    "Entidad pagadora": v_entidad
                }
                st.session_state.resumen_ventas.append(registro)
                st.session_state.datos_temp = None
                st.success("Registro guardado exitosamente.")
                st.rerun()

    # Tabla de resultados
    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        # Asegurar orden de columnas solicitado
        orden_cols = ["Fecha", "Chofer", "Cliente", "Litros", "Importe", "Factura", "Entidad pagadora"]
        df = df[orden_cols]
        
        st.subheader("📋 Planilla de Control Actual")
        st.dataframe(df, use_container_width=True)
        
        c_csv, c_clear = st.columns(2)
        with c_csv:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar Excel (CSV)", data=csv, file_name="planilla_ventas_bc.csv")
        with c_clear:
            if st.button("🗑️ Borrar Todo"):
                st.session_state.resumen_ventas = []
                st.rerun()

# ==========================================
# 4. MÓDULO: PROVEEDORES
# ==========================================
elif opcion == "📄 Facturas de Proveedores":
    st.title("📄 Gestión de Proveedores")
    archivo_prov = st.file_uploader("Subir Factura de Proveedor", type=["pdf", "png", "jpg", "jpeg"])
    
    if archivo_prov and st.button("🚀 PROCESAR FACTURA"):
        with st.spinner("Analizando comprobante..."):
            try:
                if archivo_prov.name.lower().
