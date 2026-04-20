import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os
import io  # <-- Librería agregada para manejar el archivo Excel en memoria

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
st.sidebar.info("Sistema v3.3 - Exportación a Excel")

# ==========================================
# 3. MÓDULO: VENTAS A CAMIONES
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title("🚛 Registro de Carga de Camiones")
    
    col_files = st.columns(2)
    with col_files[0]:
        f_factura = st.file_uploader("1. Factura (Imagen o PDF)", type=["jpg", "png", "jpeg", "pdf"], key="u_factura")
    with col_files[1]:
        f_orden = st.file_uploader("2. Vale de Carga (Imagen)", type=["jpg", "png", "jpeg"], key="u_orden")

    if f_factura and f_orden and st.button("🔍 ANALIZAR AMBOS DOCUMENTOS"):
        with st.spinner("Procesando documentos y cruzando datos..."):
            try:
                img_factura = Image.open(f_factura) if not f_factura.name.lower().endswith('.pdf') else f_factura
                img_orden = Image.open(f_orden)
                
                prompt = """
                Analizá estos dos documentos de una estación de servicio y extraé un JSON único con estas reglas:
                
                1. DEL VALE DE CARGA:
                   - 'fecha'
                   - 'entidad_pagadora'
                   - 'chofer'
                   - 'orden_litros': El número o texto que figura en el recuadro "ORDEN" justo a la derecha de los litros. 
                     (Nota: Ignorar la cantidad numérica de litros del vale).
                   - 'efectivo': El valor numérico en la casilla "EFECTIVO". Si está vacía, 0.0.
                   - 'orden_efectivo': El número o texto en el recuadro "ORDEN" a la derecha de Efectivo.
                
                2. DE LA FACTURA:
                   - 'razon_social' (nombre del cliente)
                   - 'litros_factura' (litros reales de la factura, como número)
                   - 'importe' (total factura, como número)
                   - 'nro_factura'
                
                Devolvé ÚNICAMENTE el objeto JSON puro.
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
        with st.form("validador_v4"):
            st.subheader("📝 Confirmar Información")
            
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
            
            # Datos de Control (Orden y Efectivo)
            with st.expander("Números de Orden y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                
                try: efectivo_val = float(st.session_state.datos_temp.get('efectivo', 0.0))
                except: efectivo_val = 0.0

                o_litros = ca1.text_input("Orden de Litros", str(st.session_state.datos_temp.get('orden_litros', '')))
                v_efectivo = ca2.number_input("Efectivo", value=efectivo_val)
                o_efectivo = ca3.text_input("Orden de Efectivo", str(st.session_state.datos_temp.get('orden_efectivo', '')))

            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                registro = {
                    "Fecha": fecha,
                    "Chofer": chofer,
                    "Cliente": cliente_rs,
                    "Litros": litros,
                    "Importe": importe,
                    "Factura": factura_nro,
                    "Entidad pagadora": entidad,
                    "Orden Litros": o_litros,
                    "Efectivo": v_efectivo,
                    "Orden Efectivo": o_efectivo
                }
                st.session_state.resumen_ventas.append(registro)
                st.session_state.datos_temp = None
                st.rerun()

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        
        # Orden de columnas definitivo
        orden_columnas = [
            "Fecha", "Chofer", "Cliente", "Litros", "Importe", 
            "Factura", "Entidad pagadora", "Orden Litros", "Efectivo", "Orden Efectivo"
        ]
        df = df[orden_columnas]
        
        st.subheader(f"📋 Planilla de Control ({len(df)} registros)")
        st.dataframe(df, use_container_width=True)
        
        col_btn1, col_btn2 = st.columns(2)
        
        # ==========================================
        # CÓDIGO NUEVO PARA GENERAR EXCEL REAL
        # ==========================================
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ventas_Camiones')
            
            # Auto-ajustar el ancho de las columnas
            worksheet = writer.sheets['Ventas_Camiones']
            for i, col in enumerate(df.columns):
                # Calcula el ancho basándose en el contenido más largo de la columna
                column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.column_dimensions[chr(65 + i)].width = column_len
        
        col_btn1.download_button(
            label="📥 Descargar Planilla Excel", 
            data=buffer.getvalue(), 
            file_name="ventas_bc.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        if col_btn2.button("🗑️ Limpiar Planilla", use_container_width=True):
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
                if archivo_prov.name.lower().endswith('.pdf'):
                    reader = PdfReader(archivo_prov)
                    text_pdf = "\n".join([page.extract_text() for page in reader.pages[:2]])
                    input_prov = [f"Texto: {text_pdf}"]
                else:
                    input_prov = [Image.open(archivo_prov)]
                
                res_prov = cliente.models.generate_content(
                    model='gemini-2.5-pro',
                    contents=input_prov + ["Extraé CUIT, Razón Social, Fecha, Neto, IVA y Total en JSON."]
                )
                raw = res_prov.text.strip().replace('```json', '').replace('```', '')
                st.json(raw[raw.find('{'):raw.rfind('}')+1])
            except Exception as e:
                st.error(f"Error: {e}")
