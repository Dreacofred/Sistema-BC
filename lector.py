import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os
import io
from datetime import datetime # Para obtener la fecha actual

# Herramientas de diseño para el Excel
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

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

if 'contador_carga' not in st.session_state:
    st.session_state.contador_carga = 0
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

# Nuevo campo para identificar el resumen
st.sidebar.subheader("📌 Configuración del Reporte")
cliente_reporte = st.sidebar.text_input("Nombre del Cliente para el Excel:", placeholder="Ej: Transportes Lopez")

st.sidebar.info("Sistema v3.9 - Nombramiento Dinámico")

# ==========================================
# 3. MÓDULO: VENTAS A CAMIONES
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title("🚛 Registro de Carga de Camiones")
    
    st.subheader("📸 Paso 1: Cargar Documentos")
    col_f, col_o = st.columns(2)
    
    with col_f:
        st.markdown("### 📄 Factura")
        with st.expander("📷 Abrir Cámara para Factura"):
            cam_f = st.camera_input("Capturar", key=f"cam_f_{st.session_state.contador_carga}")
        up_f = st.file_uploader("O subir archivo", type=["pdf","jpg","png","jpeg"], key=f"up_f_{st.session_state.contador_carga}")

    with col_o:
        st.markdown("### 🎫 Vale de Carga")
        with st.expander("📷 Abrir Cámara para Vale"):
            cam_o = st.camera_input("Capturar", key=f"cam_o_{st.session_state.contador_carga}")
        up_o = st.file_uploader("O subir archivo", type=["jpg","png","jpeg"], key=f"up_o_{st.session_state.contador_carga}")

    doc_f = cam_f if cam_f else up_f
    doc_o = cam_o if cam_o else up_o

    if doc_f and doc_o and st.button("🔍 ANALIZAR DOCUMENTOS"):
        with st.spinner("Analizando con Inteligencia Artificial..."):
            try:
                if hasattr(doc_f, 'name') and doc_f.name.lower().endswith('.pdf'):
                    reader = PdfReader(doc_f)
                    text_pdf = "\n".join([p.extract_text() for p in reader.pages[:1]])
                    input_f = f"Texto de Factura: {text_pdf}"
                else:
                    input_f = Image.open(doc_f)
                
                input_o = Image.open(doc_o)
                
                prompt = """
                Analizá estos dos documentos y extraé un JSON único:
                1. DEL VALE: 'fecha', 'entidad_pagadora', 'chofer', 'orden_litros', 'efectivo', 'orden_efectivo'.
                2. DE LA FACTURA: 'razon_social', 'litros_factura', 'importe', 'nro_factura'.
                Devolvé ÚNICAMENTE el JSON puro.
                """
                
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=[prompt, input_f, input_o])
                raw_text = res.text.strip().replace('```json', '').replace('```', '')
                start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                st.session_state.datos_temp = json.loads(raw_text[start:end])
                
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.datos_temp:
        with st.form("validador_v9"):
            st.subheader("📝 Paso 2: Confirmar Información")
            c1, c2, c3 = st.columns([1, 1, 2])
            fecha = c1.text_input("Fecha", str(st.session_state.datos_temp.get('fecha', '')))
            chofer = c2.text_input("Chofer", str(st.session_state.datos_temp.get('chofer', '')))
            cliente_rs = c3.text_input("Cliente", str(st.session_state.datos_temp.get('razon_social', '')))
            
            c4, c5, c6 = st.columns(3)
            def to_f(v):
                try: return float(v)
                except: return 0.0

            litros = c4.number_input("Litros", value=to_f(st.session_state.datos_temp.get('litros_factura', 0.0)), format="%.4f")
            importe = c5.number_input("Importe", value=to_f(st.session_state.datos_temp.get('importe', 0.0)))
            factura_nro = c6.text_input("Factura Nº", str(st.session_state.datos_temp.get('nro_factura', '')))
            
            entidad = st.text_input("Entidad pagadora", str(st.session_state.datos_temp.get('entidad_pagadora', '')))
            
            with st.expander("Control de Órdenes y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                def clean_order(v):
                    val = str(v).strip()
                    return int(val) if val.isdigit() else val

                o_litros = ca1.text_input("Orden Litros", str(st.session_state.datos_temp.get('orden_litros', '')))
                v_efectivo = ca2.number_input("Efectivo", value=to_f(st.session_state.datos_temp.get('efectivo', 0.0)))
                o_efectivo = ca3.text_input("Orden Efectivo", str(st.session_state.datos_temp.get('orden_efectivo', '')))

            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                registro = {
                    "Fecha": fecha, "Chofer": chofer, "Cliente": cliente_rs,
                    "Litros": litros, "Importe": importe, "Factura": factura_nro,
                    "Entidad pagadora": entidad, 
                    "Orden Litros": clean_order(o_litros) if o_litros != "None" else "",
                    "Efectivo": v_efectivo, 
                    "Orden Efectivo": clean_order(o_efectivo) if o_efectivo != "None" else ""
                }
                st.session_state.resumen_ventas.append(registro)
                st.session_state.datos_temp = None
                st.session_state.contador_carga += 1
                st.rerun()

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        cols = ["Fecha", "Chofer", "Cliente", "Litros", "Importe", "Factura", "Entidad pagadora", "Orden Litros", "Efectivo", "Orden Efectivo"]
        df = df[cols]
        
        st.subheader(f"📋 Planilla Acumulada ({len(df)} registros)")
        st.dataframe(df, use_container_width=True)
        
        col_ex1, col_ex2 = st.columns(2)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ventas')
            ws = writer.sheets['Ventas']
            last_r = len(df) + 1
            
            fill_header = PatternFill(start_color="C8102E", end_color="C8102E", fill_type="solid")
            fill_tot = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            f_white = Font(color="FFFFFF", bold=True)
            f_bold = Font(bold=True)
            border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            
            for cell in ws[1]:
                cell.fill, cell.font, cell.border, cell.alignment = fill_header, f_white, border, Alignment(horizontal="center")

            for row in ws.iter_rows(min_row=2, max_row=last_r):
                for cell in row:
                    cell.border = border
                    if cell.column_letter in ['E', 'I']: cell.number_format = '"$"#,##0.00'
                    if cell.column_letter == 'D': cell.number_format = '#,##0.0000'
                    if cell.column_letter in ['H', 'J']: cell.number_format = '0'

            row_t = last_r + 1
            ws.cell(row=row_t, column=3, value="TOTALES:").font = f_bold
            for c_idx, c_let in [(4, 'D'), (5, 'E'), (9, 'I')]:
                cell_t = ws.cell(row=row_t, column=c_idx)
                cell_t.value = f"=SUM({c_let}2:{c_let}{last_r})"
                cell_t.font, cell_t.fill, cell_t.border = f_bold, fill_tot, border
                cell_t.number_format = '"$"#,##0.00' if c_let != 'D' else '#,##0.0000'

            for i, col in enumerate(df.columns):
                w = max(df[col].astype(str).map(len).max(), len(col)) + 4
                ws.column_dimensions[get_column_letter(i + 1)].width = w
        
        # --- LÓGICA DE NOMBRE DINÁMICO ---
        fecha_hoy = datetime.now().strftime("%d-%m-%Y")
        # Si el usuario no puso nombre, usamos 'Resumen' por defecto
        nombre_limpio = cliente_reporte.strip() if cliente_reporte.strip() else "Resumen"
        nombre_archivo = f"{nombre_limpio}_{fecha_hoy}.xlsx"

        col_ex1.download_button(
            label=f"📥 Descargar Excel: {nombre_archivo}", 
            data=buffer.getvalue(), 
            file_name=nombre_archivo, 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        if col_ex2.button("🗑️ Vaciar Todo", use_container_width=True):
            st.session_state.resumen_ventas = []
            st.rerun()

# ==========================================
# 4. MÓDULO: PROVEEDORES
# ==========================================
elif opcion == "📄 Facturas de Proveedores":
    st.title("📄 Gestión de Proveedores")
    archivo_prov = st.file_uploader("Subir Factura", type=["pdf", "png", "jpg", "jpeg"])
    if archivo_prov and st.button("🚀 PROCESAR"):
        with st.spinner("Analizando..."):
            try:
                if archivo_prov.name.lower().endswith('.pdf'):
                    reader = PdfReader(archivo_prov)
                    text_pdf = "\n".join([page.extract_text() for page in reader.pages[:2]])
                    input_data = [f"Texto: {text_pdf}"]
                else:
                    input_data = [Image.open(archivo_prov)]
                
                res = cliente.models.generate_content(
                    model='gemini-2.5-pro',
                    contents=input_data + ["Extraé CUIT, Razón Social, Fecha, Neto, IVA y Total en JSON."]
                )
                raw = res.text.strip().replace('```json', '').replace('```', '')
                st.json(raw[raw.find('{'):raw.rfind('}')+1])
            except Exception as e:
                st.error(f"Error: {e}")
