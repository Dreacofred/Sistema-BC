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
COLOR_DORADO = "#FFD700"

st.set_page_config(page_title="BC Combustibles - Gestión", layout="wide")

st.markdown(f"""
    <style>
        .stApp {{ background-color: white !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; }}
        .stButton>button {{ background-color: {COLOR_ROJO}; color: white; border-radius: 20px; font-weight: bold; width: 100%; }}
        [data-testid="stFileUploader"] button {{ background-color: {COLOR_ROJO} !important; color: white !important; font-weight: bold !important; }}
        [data-testid="stSidebar"] {{ background-color: white; border-right: 2px solid #F0F8FF; }}
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
# 3. CONEXIÓN (MODELO AJUSTADO)
# ==========================================
# IMPORTANTE: Usamos el nombre del modelo sin el prefijo 'models/' que es lo que estaba dando error 404
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

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
                
                # Le pedimos el JSON de forma muy directa
                prompt = "Extraé estos datos de la factura/orden y devolvé SOLO un JSON con: fecha, chofer, cliente, litros, importe_total, efectivo, nro_factura, nro_orden. Si el efectivo está tachado o vacío poné 0.0."
                
                # El cambio está acá: 'gemini-1.5-flash' es el más compatible hoy
                res = cliente.models.generate_content(
                    model='gemini-1.5-flash', 
                    contents=[prompt] + material
                )
                
                # Limpiamos la respuesta para que solo quede el JSON
                texto_sucio = res.text
                inicio = texto_sucio.find('{')
                fin = texto_sucio.rfind('}') + 1
                texto_limpio = texto_sucio[inicio:fin]
                
                st.session_state.resumen_ventas.append(json.loads(texto_limpio))
                st.success("¡Venta agregada con éxito!")
            except Exception as e:
                st.error(f"Error en el proceso: {e}")

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Excel para Nancy", data=csv, file_name="resumen_carga_bc.csv")
        if st.button("🗑️ Borrar Todo"):
            st.session_state.resumen_ventas = []
            st.rerun()

elif "Facturas de Proveedores" in opcion:
    st.title("📄 Proveedores")
    archivo = st.file_uploader("Subir factura", type=["pdf", "png", "jpg", "jpeg"])
    if archivo and st.button("🚀 Extraer Datos"):
        with st.spinner("Analizando..."):
            try:
                if archivo.name.lower().endswith('.pdf'):
                    mat = PdfReader(archivo).pages[0].extract_text()
                else:
                    mat = Image.open(archivo)
                
                res = cliente.models.generate_content(model='gemini-1.5-flash', contents=["Extraé datos de esta factura en JSON puro", mat])
                st.code(res.text)
            except Exception as e:
                st.error(f"Error: {e}")
