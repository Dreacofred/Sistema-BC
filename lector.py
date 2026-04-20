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
        [data-testid="stSidebar"] {{
            background-color: white;
            border-right: 2px solid {COLOR_FONDO_AZUL};
        }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. BARRA LATERAL CON LOGO
# ==========================================
st.sidebar.markdown("<br>", unsafe_allow_html=True)

# Buscamos automáticamente el archivo sin importar si es mayúscula o JPG/JPEG
ruta_logo = None
for variante in ["Logo.jpeg", "Logo.jpg", "logo.jpeg", "logo.jpg"]:
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

# ==========================================
# 3. LÓGICA DEL SISTEMA
# ==========================================
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

# --- SECCIÓN: VENTAS A CAMIONES ---
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
                        img_orden = Image.open(f_orden)
                        cosas_para_ia.append(img_orden)
                        instruccion = """
                        Sos un experto administrativo contable. Te paso dos imágenes: factura y orden manual.
                        Extraé y cruzá los datos. 
                        Si el campo de Efectivo está tachado, rayado o en blanco en la orden, devolvé 0.0.
                        Devolveme SOLO un JSON puro con:
                        {"fecha": "...", "chofer": "...", "cliente": "...", "litros": 0.0, "importe_total": 0.0, "efectivo": 0.0, "nro_factura": "...", "nro_orden": "..."}
                        """
                    else:
                        instruccion = """
                        Sos un experto administrativo contable. Te paso SOLO una factura de surtidor (esta venta no tiene orden manual).
                        Extraé de la factura la fecha, cliente, litros (si figuran, si no poné 0), total y nro de factura.
                        Como no hay orden, en chofer y nro_orden poné "Sin orden" y en efectivo 0.0.
                        Devolveme SOLO un JSON puro con:
                        {"fecha": "...", "chofer": "Sin orden", "cliente": "...", "litros": 0.0, "importe_total": 0.0, "efectivo": 0.0, "nro_factura": "...", "nro_orden": "Sin orden"}
                        """

                    cosas_para_ia.insert(0, instruccion)

                    res = cliente.models.generate_content(
                        model='gemini-2.0-flash', 
                        contents=cosas_para_ia
                    )
                    
                    limpio = res.text.replace("```json", "").replace("```", "").strip()
                    datos = json.loads(limpio)
                    
                    st.session_state.resumen_ventas.append(datos)
                    st.success("¡Venta agregada al resumen!")
                
                except Exception as e:
                    st.error(f"Error al leer los datos. Detalle: {e}")

    # Mostrar tabla acumulada
    if st.session_state.resumen_ventas:
        st.divider()
        st.subheader("📋 Resumen Acumulado del Día")
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.dataframe(df, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar Excel (CSV)", data=csv, file_name="resumen_carga.csv", mime="text/csv")
        with col_b:
            if st.button("🗑️ Borrar todo y empezar de nuevo"):
                st.session_state.resumen_ventas = []
                st.rerun()

# --- SECCIÓN: PROVEEDORES ---
elif "Facturas de Proveedores" in opcion:
    st.title("📄 Carga de Facturas de Proveedores")
    st.write("Subí el PDF o la foto de la factura para extraer los datos.")
    
    archivo_subido = st.file_uploader("Arrastrá archivo aquí", type=["pdf", "png", "jpg", "jpeg"], key="prov")

    if archivo_subido and st.button("🚀 Extraer Datos Proveedor"):
        with st.spinner("Analizando..."):
            try:
                if archivo_subido.name.lower().endswith('.pdf'):
                    lector = PdfReader(archivo_subido)
                    material = lector.pages[0].extract_text()
                else:
                    material = Image.open(archivo_subido)

                orden = "Analizá esta factura de proveedor de Argentina. Devolveme un JSON puro con proveedor_nombre, proveedor_cuit, numero_comprobante, fecha_emision, importe_total y articulos."
                
                respuesta = cliente.models.generate_content(model='gemini-2.0-flash', contents=[orden, material])
                st.success("¡Datos extraídos!")
                
                # Limpiamos el texto por si Gemini devuelve markdown
                texto_limpio = respuesta.text.replace("```json", "").replace("```", "").strip()
                st.code(texto_limpio, language="json")
            except Exception as e:
                st.error(f"Error al procesar el archivo: {e}")
