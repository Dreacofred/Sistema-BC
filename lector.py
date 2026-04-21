import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os
import io
from datetime import datetime

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
        
        /* --- DESTACAR EL RECUADRO DEL CLIENTE --- */
        [data-testid="stSidebar"] .stTextInput div[data-baseweb="input"] {{
            border: 2px solid {COLOR_ROJO} !important;
            border-radius: 8px !important;
            box-shadow: 0px 4px 10px rgba(200, 16, 46, 0.25) !important;
            background-color: #ffffff !important;
        }}
        [data-testid="stSidebar"] .stTextInput label p {{
            color: {COLOR_ROJO} !important;
            font-size: 1.15em !important;
            font-weight: 800 !important;
            margin-bottom: 5px !important;
        }}
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

# Campo del cliente super destacado
st.sidebar.subheader("📌 Configuración del Reporte")
cliente_reporte = st.sidebar.text_input("NOMBRE DEL CLIENTE AQUÍ:", placeholder="Ej: Transportes Lopez")

st.sidebar.info("Sistema v4.1 - Prompt Guiado")

# ==========================================
# 3. MÓDULO: VENTAS A CAMIONES
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title("🚛 Registro de Carga de Camiones")
    
    st.subheader("📸 Paso 1: Capturar Documentos")
    st.success("💡 **Tip:** Colocá la Factura y el Vale juntos en el escritorio (sin superponerlos) y sacá UNA sola foto.")
    
    with st.expander("📷 ABRIR CÁMARA", expanded=True):
        cam_doc = st.camera_input("Capturar ambos documentos", key=f"cam_{st.session_state.contador_carga}")
    
    up_doc = st.file_uploader("📁 O subir imagen guardada", type=["jpg","png","jpeg","pdf"], key=f"up_{st.session_state.contador_carga}")

    doc_input = cam_doc if cam_doc else up_doc

    if doc_input and st.button("🔍 ANALIZAR DOCUMENTOS"):
        with st.spinner("Leyendo factura y vale en simultáneo..."):
            try:
                if hasattr(doc_input, 'name') and doc_input.name.lower().endswith('.pdf'):
                    reader = PdfReader(doc_input)
                    text_pdf = "\n".join([p.extract_text() for p in reader.pages[:1]])
                    input_data = f"Texto: {text_pdf}"
                else:
                    input_data = Image.open(doc_input)
                
                # ==========================================
                # NUEVO PROMPT GUIADO (Mucho más preciso)
                # ==========================================
                prompt = """
                Analizá esta imagen que contiene dos documentos distintos apoyados en una mesa: una factura impresa a la izquierda y un vale de carga escrito a mano a la derecha. 

                PASO 1: Localiza mentalmente el documento de la izquierda (el ticket/factura impresa).
                En este documento, busca y extrae los siguientes campos. Asegurate de interpretar los números usando coma como separador decimal:
                - 'razon_social' (Nombre del cliente/empresa que está en medio del ticket, bajo el CUIT)
                - 'litros_factura' (El número que aparece junto a "GASOIL G2 500", ej: "426.032")
                - 'importe' (El "TOTAL" al final del ticket, ej: "999045,04")
                - 'nro_factura' (El número bajo "Nro.", ej: "0024-00019171")

                PASO 2: Localiza mentalmente el documento de la derecha (el vale escrito a mano, pero en imprenta).
                Identifica el texto dentro de los recuadros dibujados y extrae:
                - 'fecha' (El texto en el recuadro "FECHA" arriba a la derecha, ej: "16/04/26")
                - 'chofer' (El texto en el recuadro "CHOFER", ej: "ALTAMIRANO SERGIO")
                - 'entidad_pagadora' (El texto en el recuadro "ENTIDAD PAGADORA", ej: "TRANSP. HIJOS DE MARI")
                - 'orden_litros' (El texto en el recuadro "ORDEN" que está justo a la derecha del recuadro "LITROS". ¡No extraigas la cantidad de litros manuscrita del vale, solo la orden!)
                - 'efectivo' (El número en el recuadro "EFECTIVO". Si está vacío, pon 0.0)
                - 'orden_efectivo' (El texto en el recuadro "ORDEN" que está justo a la derecha del recuadro "EFECTIVO")

                PASO 3: Unifica todos los datos extraídos en un único objeto JSON plano. Si no encuentras un dato, pon "NOT_FOUND" como valor.

                Devolvé ÚNICAMENTE el JSON puro, sin markdown ni texto extra.
                """
                
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=[prompt, input_data])
                raw_text = res.text.strip().replace('```json', '').replace('```', '')
                start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                st.session_state.datos_temp = json.loads(raw_text[start:end])
                
            except Exception as e:
                st.error(f"Error: {e}")

    # --- FORMULARIO DE VALIDACIÓN ---
    if st.session_state.datos_temp:
        with st.form("validador_v10"):
            st.subheader("📝 Paso 2: Confirmar Información")
            c1, c2, c3 = st.columns([1, 1, 2])
            
            # Helper para limpiar "NOT_FOUND" y mostrar blanco
            def get_v(field):
                val = st.session_state.datos_temp.get(field, '')
                return '' if val == 'NOT_FOUND' else str(val)

            fecha = c1.text_input("Fecha", get_v('fecha'))
            chofer = c2.text_input("Chofer", get_v('chofer'))
            cliente_rs = c3.text_input("Cliente de Factura", get_v('razon_social'))
            
            c4, c5, c6 = st.columns(3)
            def to_f(field):
                val = st.session_state.datos_temp.get(field, 0.0)
                if val == 'NOT_FOUND': return 0.0
                try: 
                    # Manejar formatos como 426.032 o 999045,04
                    val_str = str(val).replace('.', '').replace(',', '.')
                    return float(val_str)
                except: return 0.0

            litros = c4.number_input("Litros", value=to_f('litros_factura'), format="%.4f")
            importe = c5.number_input("Importe", value=to_f('importe'))
            factura_nro = c6.text_input("Factura Nº", get_v('nro_factura'))
            
            entidad = st.text_input("Entidad pagadora", get_v('entidad_pagadora'))
            
            with st.expander("Control de Órdenes y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                def clean_order(v):
                    val = str(v).strip()
                    if val == 'NOT_FOUND': return ''
                    return int(val) if val.isdigit() else val

                o_litros = ca1.text_input("Orden Litros", get_v('orden_litros'))
                v_efectivo = ca2.number_input("Efectivo", value=to_f('efectivo'))
                o_efectivo = ca3.text_input("Orden Efectivo", get_v('orden_efectivo'))

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

    # --- TABLA Y EXPORTACIÓN ---
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
        
        fecha_hoy = datetime.now().strftime("%d-%m-%Y")
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
    # Mantenemos este módulo igual
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
