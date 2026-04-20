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

st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo:
    st.sidebar.image(ruta_logo, use_container_width=True)
else:
    st.sidebar.markdown(f"<h1 style='text-align: center; color: {COLOR_ROJO};'>BC</h1>", unsafe_allow_html=True)

opcion = st.sidebar.radio("Seleccioná la tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])
st.sidebar.divider()
st.sidebar.info("Sistema v3.1 - Control de Cargas")

# ==========================================
# 3. MÓDULO: VENTAS A CAMIONES
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title("🚛 Registro de Carga de Camiones")
    
    col_files = st.columns(2)
    with col_files[0]:
        f_factura = st.file_uploader("1. Factura (Imagen o PDF)", type=["jpg", "png", "jpeg", "pdf"], key="u_factura")
    with col_files[1]:
        f_orden = st.file_uploader("2. Papel de Carga / Orden (Imagen)", type=["jpg", "png", "jpeg"], key="u_orden")

    if f_factura and f_orden and st.button("🔍 ANALIZAR AMBOS DOCUMENTOS"):
        with st.spinner("Procesando documentos y cruzando datos..."):
            try:
                img_factura = Image.open(f_factura) if not f_factura.name.lower().endswith('.pdf') else f_factura
                img_orden = Image.open(f_orden)
                
                # Prompt optimizado: Ignora la fila de litros en el papel de carga
                prompt = """
                Analizá estos dos documentos de una estación de servicio y extraé un JSON único con estas reglas estrictas:
                
                1. DEL PAPEL DE CARGA (Vale de Carga):
                   - 'fecha'
                   - 'entidad_pagadora'
                   - 'chofer'
                   - ATENCIÓN A LA ESTRUCTURA DE CASILLEROS:
                     * (Ignorar la fila de LITROS de este papel, tomaremos ese dato de la factura)
                     * 'efectivo': El valor numérico en la casilla "EFECTIVO" a la izquierda. Si está vacía, poné 0.0.
                     * 'orden_efectivo': El valor alfanumérico en la casilla "ORDEN" que está a la derecha de Efectivo. Si está vacía, dejá "".
                
                2. DE LA FACTURA:
                   - 'razon_social' (el nombre del cliente)
                   - 'litros_factura' (los litros que figuran en la factura, como número)
                   - 'importe' (monto total factura, como número)
                   - 'nro_factura'
                
                Devolvé ÚNICAMENTE el objeto JSON puro, sin texto adicional ni bloques de código.
                """
                
                res = cliente.models.generate_content(
                    model='gemini-2.5-pro',
                    contents=[prompt, img_factura, img_orden]
                )
                
                raw_text = res.text.strip().replace('```json', '').replace('```', '')
                start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                st.session_state.datos_temp = json.loads(raw_text[start:end])
                
            except Exception as e:
                st.error(f"Error en el procesamiento: {e}")

    # Formulario de validación
    if st.session_state.datos_temp:
        with st.form("validador_v3"):
            st.subheader("📝 Confirmar Información Cruzada")
            
            c1, c2, c3 = st.columns([1, 1, 2])
            fecha = c1.text_input("Fecha", str(st.session_state.datos_temp.get('fecha', '')))
            chofer = c2.text_input("Chofer", str(st.session_state.datos_temp.get('chofer', '')))
            cliente_rs = c3.text_input("Cliente (Razón Social)", str(st.session_state.datos_temp.get('razon_social', '')))
            
            c4, c5, c6 = st.columns(3)
            try: litros_val = float(st.session_state.datos_temp.get('litros_factura', 0.0))
            except: litros_val = 0.0
            
            try: importe_val = float(st.session_state.datos_temp.get('importe', 0.0))
            except: importe_val = 0.0
            
            litros = c4.number_input("Litros (Factura)", value=litros_val)
            importe = c5.number_input("Importe", value=importe_val)
            factura_nro = c6.text_input("Factura", str(st.session_state.datos_temp.get('nro_factura', '')))
            
            entidad = st.text_input("Entidad pagadora", str(st.session_state.datos_temp.get('entidad_pagadora', '')))
            
            # Fila 3: Solo datos de Efectivo del Vale de Carga
            with st.expander("Datos adicionales del Vale de Carga", expanded=True):
                ca1, ca2 = st.columns(2)
                
                try: efectivo_val = float(st.session_state.datos_temp.get('efectivo', 0.0))
                except: efectivo_val = 0.0

                v_efectivo = ca1.number_input("Efectivo", value=efectivo_val)
                o_efectivo = ca2.text_input("Orden de Efectivo", str(st.session_state.datos_temp.get('orden_efectivo', '')))

            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                registro = {
                    "Fecha": fecha,
                    "Chofer": chofer,
                    "Cliente": cliente_rs,
                    "Litros": litros,
                    "Importe": importe,
                    "Factura": factura_nro,
                    "Entidad pagadora": entidad,
                    "Efectivo": v_efectivo,
                    "Orden Efectivo": o_efectivo
                }
                st.session_state.resumen_ventas.append(registro)
                st.session_state.datos_temp = None
                st.rerun()

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        
        # Columnas actualizadas sin "Orden Litros"
        orden_columnas = [
            "Fecha", "Chofer", "Cliente", "Litros", "Importe", 
            "Factura", "Entidad pagadora", "Efectivo", "Orden Efectivo"
        ]
        df = df[orden_columnas]
        
        st.subheader(f"📋 Planilla de Control ({len(df)} registros)")
        st.dataframe(df, use_container_width=True)
        
        col_btn1, col_btn2 = st.columns(2)
        csv = df.to_csv(index=False).encode('utf-8')
        col_btn1.download_button("📥 Descargar Planilla CSV", data=csv, file_name="ventas_estacion.csv", use_container_width=True)
        
        if col_btn2.button("🗑️ Limpiar Planilla", use_container_width=True):
            st.session_state.resumen_ventas = []
            st.rerun()

# ==========================================
# 4. MÓDULO: FACTURAS DE PROVEEDORES
# ==========================================
elif opcion == "📄 Facturas de Proveedores":
    st.title("📄 Gestión de Proveedores")
    archivo_prov = st.file_uploader("Subir Factura de Proveedor (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"])
    
    if archivo_prov and st.button("🚀 PROCESAR FACTURA"):
        with st.spinner("Extrayendo datos de facturación..."):
            try:
                if archivo_prov.name.lower().endswith('.pdf'):
                    reader = PdfReader(archivo_prov)
                    text_pdf = "\n".join([page.extract_text() for page in reader.pages[:2]])
                    input_prov = [f"Texto extraído de la factura: {text_pdf}"]
                else:
                    input_prov = [Image.open(archivo_prov)]
                
                prompt_prov = "Extraé CUIT, Razón Social, Fecha, Neto Gravado, IVA y Total en formato JSON puro."
                
                res_prov = cliente.models.generate_content(
                    model='gemini-2.5-pro',
                    contents=input_prov + [prompt_prov]
                )
                
                res_text = res_prov.text.strip().replace('```json', '').replace('```', '')
                st.json(res_text[res_text.find('{'):res_text.rfind('}')+1])
            except Exception as e:
                st.error(f"Error en la lectura: {e}")
