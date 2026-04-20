import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os

# ==========================================
# 1. ESTILO BC COMBUSTIBLES
# ==========================================
COLOR_ROJO = "#C8102E"

st.set_page_config(
    page_title="BC Combustibles - Gestión Pro",
    page_icon="⛽",
    layout="wide"
)

# Diseño de interfaz profesional
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
# 2. BARRA LATERAL
# ==========================================
st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo:
    st.sidebar.image(ruta_logo, use_container_width=True)
else:
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

opcion = st.sidebar.radio("Tareas:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])
st.sidebar.divider()
st.sidebar.success("✅ Modo Pro Habilitado")

# ==========================================
# 3. CONEXIÓN PRO (CON VERSIÓN ESTABLE)
# ==========================================
# Al usar api_version='v1' nos aseguramos de no usar versiones beta que fallan
cliente = genai.Client(
    api_key=st.secrets["GEMINI_API_KEY"],
    http_options={'api_version': 'v1'}
)

if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

if "Ventas a Camiones" in opcion:
    st.title("🚛 Registro de Carga")
    
    f_factura = st.file_uploader("1. Foto Factura", type=["jpg", "png", "jpeg"], key="f1")
    f_orden = st.file_uploader("2. Foto Orden (Opcional)", type=["jpg", "png", "jpeg"], key="f2")

    if f_factura and st.button("🔍 ANALIZAR VENTA", use_container_width=True):
        with st.spinner("La IA Pro está leyendo los documentos..."):
            try:
                img_f = Image.open(f_factura)
                material = [img_f]
                if f_orden: material.append(Image.open(f_orden))
                
                prompt = """Sos un experto administrativo de estaciones de servicio. 
                Extraé: fecha, chofer, cliente, litros, importe_total, efectivo, nro_factura, nro_orden. 
                Si el efectivo está tachado o vacío poné 0.0. 
                Devolvé SOLO un JSON puro, sin texto extra."""
                
                # MOTOR PRO: Máxima precisión para tu plan pago
                res = cliente.models.generate_content(
                    model='gemini-1.5-pro', 
                    contents=[prompt] + material
                )
                
                # Limpieza de la respuesta para evitar errores de formato
                txt = res.text.strip().replace('```json', '').replace('```', '')
                inicio = txt.find('{')
                fin = txt.rfind('}') + 1
                datos = json.loads(txt[inicio:fin])
                
                st.session_state.resumen_ventas.append(datos)
                st.success("¡Venta registrada!")
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Planilla Excel", data=csv, file_name="planilla_bc.csv")
        if st.button("🗑️ Reiniciar Planilla"):
            st.session_state.resumen_ventas = []
            st.rerun()

elif "Facturas de Proveedores" in opcion:
    st.title("📄 Proveedores")
    archivo = st.file_uploader("Subir factura", type=["pdf", "png", "jpg", "jpeg"])
    if archivo and st.button("🚀 Extraer Datos"):
        with st.spinner("Analizando con Pro..."):
            try:
                if archivo.name.lower().endswith('.pdf'):
                    mat = PdfReader(archivo).pages[0].extract_text()
                else:
                    mat = Image.open(archivo)
                res = cliente.models.generate_content(model='gemini-1.5-pro', contents=["Extraé datos de esta factura en JSON puro", mat])
                st.code(res.text)
            except Exception as e:
                st.error(f"Error: {e}")
