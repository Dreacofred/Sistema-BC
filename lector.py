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
# 2. PANEL LATERAL Y CONEXIÓN
# ==========================================
st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo:
    st.sidebar.image(ruta_logo, use_container_width=True)
else:
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

opcion = st.sidebar.radio("Seleccioná la tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])
st.sidebar.divider()
st.sidebar.success("💎 MOTOR: GEMINI 2.5 PRO")

# Cliente API
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# Inicializar estados
if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []
if 'datos_temp' not in st.session_state:
    st.session_state.datos_temp = None

# ==========================================
# 3. LÓGICA DE VENTAS A CAMIONES
# ==========================================
if "Ventas a Camiones" in opcion:
    st.title("🚛 Registro de Carga de Camiones")
    
    col1, col2 = st.columns(2)
    with col1:
        f_factura = st.file_uploader("1. Foto Factura", type=["jpg", "png", "jpeg"], key="f1")
    with col2:
        f_orden = st.file_uploader("2. Foto Orden (Opcional)", type=["jpg", "png", "jpeg"], key="f2")

    if f_factura and st.button("🔍 ANALIZAR CON IA PRO", use_container_width=True):
        with st.spinner("Procesando con la máxima precisión..."):
            try:
                img_f = Image.open(f_factura)
                material = [img_f]
                if f_orden: material.append(Image.open(f_orden))
                
                prompt = """Extraé: fecha, chofer, cliente, litros (float), importe_total (float), efectivo (float), nro_factura, nro_orden. 
                Si algo no figura o el efectivo está tachado, usá 0.0. Devolvé SOLO JSON puro."""
                
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=[prompt] + material)
                
                txt = res.text.strip().replace('```json', '').replace('```', '')
                inicio, fin = txt.find('{'), txt.rfind('}') + 1
                st.session_state.datos_temp = json.loads(txt[inicio:fin])
            except Exception as e:
                st.error(f"Error en la lectura: {e}")

    # FORMULARIO DE EDICIÓN/CONFIRMACIÓN
    if st.session_state.datos_temp:
        st.info("💡 Confirmá o corregí los datos detectados antes de guardar:")
        with st.form("confirmar_datos"):
            c1, c2, c3 = st.columns(3)
            fecha = c1.text_input("Fecha", st.session_state.datos_temp.get('fecha', ''))
            factura = c2.text_input("Nro Factura", st.session_state.datos_temp.get('nro_factura', ''))
            orden = c3.text_input("Nro Orden", st.session_state.datos_temp.get('nro_orden', ''))
            
            c4, c5 = st.columns(2)
            chofer = c4.text_input("Chofer", st.session_state.datos_temp.get('chofer', ''))
            cliente_nom = c5.text_input("Cliente", st.session_state.datos_temp.get('cliente', ''))
            
            c6, c7, c8 = st.columns(3)
            litros = c6.number_input("Litros", value=float(st.session_state.datos_temp.get('litros', 0.0)))
            total = c7.number_input("Importe Total", value=float(st.session_state.datos_temp.get('importe_total', 0.0)))
            efectivo = c8.number_input("Efectivo", value=float(st.session_state.datos_temp.get('efectivo', 0.0)))
            
            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                nueva_venta = {
                    "fecha": fecha, "nro_factura": factura, "nro_orden": orden,
                    "chofer": chofer, "cliente": cliente_nom, "litros": litros,
                    "importe_total": total, "efectivo": efectivo
                }
                st.session_state.resumen_ventas.append(nueva_venta)
                st.session_state.datos_temp = None
                st.success("¡Venta agregada!")
                st.rerun()

    # VISUALIZACIÓN DE TABLA
    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.subheader(f"📋 Planilla Acumulada ({len(df)} registros)")
        st.dataframe(df, use_container_width=True)
        
        col_down1, col_down2 = st.columns(2)
        csv = df.to_csv(index=False).encode('utf-8')
        col_down1.download_button("📥 Descargar CSV", data=csv, file_name="planilla_bc.csv", use_container_width=True)
        if col_down2.button("🗑️ Reiniciar Todo", use_container_width=True):
            st.session_state.resumen_ventas = []
            st.rerun()

# ==========================================
# 4. LÓGICA DE PROVEEDORES
# ==========================================
elif "Facturas de Proveedores" in opcion:
    st.title("📄 Carga de Proveedores")
    archivo = st.file_uploader("Subir factura (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"])
    
    if archivo and st.button("🚀 PROCESAR PROVEEDOR"):
        with st.spinner("Analizando comprobante..."):
            try:
                if archivo.name.lower().endswith('.pdf'):
                    # Leemos todas las páginas si es necesario, aquí la primera por velocidad
                    reader = PdfReader(archivo)
                    contenido = "\n".join([page.extract_text() for page in reader.pages[:2]])
                    material = [f"Texto de la factura: {contenido}"]
                else:
                    material = [Image.open(archivo)]
                
                prompt = "Extraé CUIT, Razón Social, Fecha, Total e Impuestos en JSON puro."
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=[prompt] + material)
                
                txt = res.text.strip().replace('```json', '').replace('```', '')
                st.code(txt[txt.find('{'):txt.rfind('}')+1], language="json")
            except Exception as e:
                st.error(f"Error: {e}")
