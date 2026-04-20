import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os
import io

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
st.sidebar.info("Sistema v3.5 - Reporte con Totales")

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
                Analizá estos dos documentos y extraé un JSON único:
                1. DEL VALE: 'fecha', 'entidad_pagadora', 'chofer', 'orden_litros' (nro en recuadro ORDEN a la derecha de litros), 'efectivo' (monto), 'orden_efectivo' (nro en recuadro ORDEN a la derecha de efectivo).
                2. DE LA FACTURA: 'razon_social', 'litros_factura', 'importe', 'nro_factura'.
                Devolvé ÚNICAMENTE el objeto JSON puro.
                """
                
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=[prompt, img_factura, img_orden])
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
            # Conversión segura a float
            def to_f(v): 
                try: return float(v)
                except: return 0.0

            litros = c4.number_input("Litros (Factura)", value=to_f(st.session_state.datos_temp.get('litros_factura', 0.0)))
            importe = c5.number_input("Importe", value=to_f(st.session_state.datos_temp.get('importe', 0.0)))
            factura_nro = c6.text_input("Factura", str(st.session_state.datos_temp.get('nro_factura', '')))
            
            entidad = st.text_input("Entidad pagadora", str(st.session_state.datos_temp.get('entidad_pagadora', '')))
            
            with st.expander("Números de Orden y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                o_litros = ca1.text_input("Orden de Litros", str(st.session_state.datos_temp.get('orden_litros', '')))
                v_efectivo = ca2.number_input("Efectivo", value=to_f(st.session_state.datos_temp.get('efectivo', 0.0)))
                o_efectivo = ca3.text_input("Orden de Efectivo", str(st.session_state.datos_temp.get('orden_efectivo', '')))

            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                registro = {
                    "Fecha": fecha, "Chofer": chofer, "Cliente": cliente_rs,
                    "Litros": litros, "Importe": importe, "Factura": factura_nro,
                    "Entidad pagadora": entidad, 
                    "Orden Litros": o_litros if o_litros != "None" else "",
                    "Efectivo": v_efectivo, 
                    "Orden Efectivo": o_efectivo if o_efectivo != "None" else ""
                }
                st.session_state.resumen_ventas.append(registro)
                st.session_state.datos_temp = None
                st.rerun()

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        orden_columnas = ["Fecha", "Chofer", "Cliente", "Litros", "Importe", "Factura", "Entidad pagadora", "Orden Litros", "Efectivo", "Orden Efectivo"]
        df = df[orden_columnas]
        
        st.subheader(f"📋 Planilla de Control ({len(df)} registros)")
        st.dataframe(df, use_container_width=True)
        
        col_btn1, col_btn2 = st.columns(2)
        
        # ==========================================
        # EXPORTACIÓN A EXCEL CON TOTALES Y FORMATO $
        # ==========================================
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ventas_Camiones')
            worksheet = writer.sheets['Ventas_Camiones']
            last_row = len(df) + 1
            
            # Estilos
            color_rojo = PatternFill(start_color="C8102E", end_color="C8102E", fill_type="solid")
            color_totales = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            font_blanca = Font(color="FFFFFF", bold=True)
            font_negra_bold = Font(bold=True)
            borde = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            
            # Formatos de número (Excel)
            fmt_moneda = '"$"#,##0.00'
            fmt_litros = '#,##0.00'

            # 1. Encabezados
            for cell in worksheet[1]:
                cell.fill, cell.font, cell.border, cell.alignment = color_rojo, font_blanca, borde, Alignment(horizontal="center")

            # 2. Datos y Bordes
            for row in worksheet.iter_rows(min_row=2, max_row=last_row):
                for cell in row:
                    cell.border = borde
                    # Aplicar formato $ a columnas Importe (E) y Efectivo (I)
                    if cell.column_letter in ['E', 'I']:
                        cell.number_format = fmt_moneda
                    # Formato a Litros (D)
                    if cell.column_letter == 'D':
                        cell.number_format = fmt_litros

            # 3. FILA DE TOTALES
            row_tot = last_row + 1
            worksheet.cell(row=row_tot, column=3, value="TOTALES:").font = font_negra_bold
            worksheet.cell(row=row_tot, column=3).alignment = Alignment(horizontal="right")

            # Columnas a sumar: D(4), E(5), I(9)
            for col_num, col_let in [(4, 'D'), (5, 'E'), (9, 'I')]:
                c = worksheet.cell(row=row_tot, column=col_num)
                c.value = f"=SUM({col_let}2:{col_let}{last_row})"
                c.font, c.fill, c.border = font_negra_bold, color_totales, borde
                c.number_format = fmt_moneda if col_let in ['E', 'I'] else fmt_litros

            # 4. Ajustar Ancho
            for i, col in enumerate(df.columns):
                column_len = max(df[col].astype(str).map(len).max(), len(col)) + 4
                worksheet.column_dimensions[get_column_letter(i + 1)].width = column_len
        
        col_btn1.download_button(
            label="📥 Descargar Excel con Totales", 
            data=buffer.getvalue(), 
            file_name="ventas_bc_final.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        if col_btn2.button("🗑️ Limpiar Planilla", use_container_width=True):
            st.session_state.resumen_ventas = []
            st.rerun()

# ==========================================
# 4. MÓDULO: PROVEEDORES (Estable)
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
                    mat = [f"Texto: {text_pdf}"]
                else:
                    mat = [Image.open(archivo_prov)]
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=mat + ["Extraé CUIT, Razón Social, Fecha, Neto, IVA y Total en JSON."])
                raw = res.text.strip().replace('```json', '').replace('```', '')
                st.json(raw[raw.find('{'):raw.rfind('}')+1])
            except Exception as e:
                st.error(f"Error: {e}")
