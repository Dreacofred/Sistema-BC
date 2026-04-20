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
# 3. MÓDULO: VENTAS A CAMIONES (CORREGIDO)
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title("🚛 Registro de Carga de Camiones")
    
    col_files = st.columns(2)
    with col_files[0]:
        f_factura = st.file_uploader("1. Factura (Imagen o PDF)", type=["jpg", "png", "jpeg", "pdf"], key="u_factura")
    with col_files[1]:
        f_orden = st.file_uploader("2. Vale de Carga (Imagen)", type=["jpg", "png", "jpeg"], key="u_orden")

    if f_factura and f_orden and st.button("🔍 ANALIZAR AMBOS DOCUMENTOS"):
        with st.spinner("Procesando documentos..."):
            try:
                img_factura = Image.open(f_factura) if not f_factura.name.lower().endswith('.pdf') else f_factura
                img_orden = Image.open(f_orden)
                
                prompt = """
                Analizá estos dos documentos y extraé un JSON único:
                1. DEL VALE: 'fecha', 'entidad_pagadora', 'chofer', 'orden_litros' (nro en recuadro ORDEN a la derecha de litros), 'efectivo' (monto), 'orden_efectivo' (nro en recuadro ORDEN a la derecha de efectivo).
                2. DE LA FACTURA: 'razon_social', 'litros_factura', 'importe', 'nro_factura'.
                Devolvé ÚNICAMENTE el JSON.
                """
                
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=[prompt, img_factura, img_orden])
                raw_text = res.text.strip().replace('```json', '').replace('```', '')
                start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                st.session_state.datos_temp = json.loads(raw_text[start:end])
                
            except Exception as e:
                st.error(f"Error: {e}")

    # FORMULARIO CON PROTECCIÓN CONTRA ERRORES DE TIPO (Fix TypeError)
    if st.session_state.datos_temp:
        with st.form("validador_v5_fix"):
            st.subheader("📝 Confirmar Información")
            
            # Función auxiliar para convertir a float de forma segura
            def safe_float(val):
                try:
                    return float(val) if val is not None else 0.0
                except:
                    return 0.0

            c1, c2, c3 = st.columns([1, 1, 2])
            fecha = c1.text_input("Fecha", str(st.session_state.datos_temp.get('fecha') or ''))
            chofer = c2.text_input("Chofer", str(st.session_state.datos_temp.get('chofer') or ''))
            cliente_rs = c3.text_input("Cliente", str(st.session_state.datos_temp.get('razon_social') or ''))
            
            c4, c5, c6 = st.columns(3)
            v_litros_val = safe_float(st.session_state.datos_temp.get('litros_factura'))
            v_importe_val = safe_float(st.session_state.datos_temp.get('importe'))
            
            litros = c4.number_input("Litros", value=v_litros_val)
            importe = c5.number_input("Importe", value=v_importe_val)
            factura_nro = c6.text_input("Factura", str(st.session_state.datos_temp.get('nro_factura') or ''))
            
            entidad = st.text_input("Entidad pagadora", str(st.session_state.datos_temp.get('entidad_pagadora') or ''))
            
            with st.expander("Control de Orden y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                o_litros = ca1.text_input("Orden Litros", str(st.session_state.datos_temp.get('orden_litros') or ''))
                
                v_efec_val = safe_float(st.session_state.datos_temp.get('efectivo'))
                v_efectivo = ca2.number_input("Efectivo", value=v_efec_val)
                
                o_efectivo = ca3.text_input("Orden Efectivo", str(st.session_state.datos_temp.get('orden_efectivo') or ''))

            # EL BOTÓN QUE FALTABA PARA CERRAR EL FORMULARIO
            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                registro = {
                    "Fecha": fecha, "Chofer": chofer, "Cliente": cliente_rs,
                    "Litros": litros, "Importe": importe, "Factura": factura_nro,
                    "Entidad pagadora": entidad, 
                    "Orden Litros": o_litros if o_litros != 'None' else "",
                    "Efectivo": v_efectivo, 
                    "Orden Efectivo": o_efectivo if o_efectivo != 'None' else ""
                }
                st.session_state.resumen_ventas.append(registro)
                st.session_state.datos_temp = None
                st.rerun()
        
        # ==========================================
        # EXPORTACIÓN A EXCEL CON TOTALES Y FORMATO $
        # ==========================================
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ventas_Camiones')
            worksheet = writer.sheets['Ventas_Camiones']
            last_row = len(df) + 1 # +1 por el encabezado
            
            # Estilos
            rojo_fill = PatternFill(start_color="C8102E", end_color="C8102E", fill_type="solid")
            gris_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            font_blanca = Font(color="FFFFFF", bold=True)
            font_negra_bold = Font(bold=True)
            borde = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            
            # Formato de Moneda y Números
            formato_moneda = '"$"#,##0.00'
            formato_litros = '#,##0.00'

            # 1. Encabezados
            for cell in worksheet[1]:
                cell.fill, cell.font, cell.border, cell.alignment = rojo_fill, font_blanca, borde, Alignment(horizontal="center")

            # 2. Datos y Formatos de Columnas
            for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, max_row=last_row), 2):
                for cell in row:
                    cell.border = borde
                    # Aplicar formato moneda a columna E (Importe) e I (Efectivo)
                    if cell.column_letter in ['E', 'I']:
                        cell.number_format = formato_moneda
                    # Aplicar formato número a columna D (Litros)
                    if cell.column_letter == 'D':
                        cell.number_format = formato_litros

            # 3. FILA DE TOTALES
            total_row = last_row + 1
            worksheet.cell(row=total_row, column=3, value="TOTALES:").font = font_negra_bold
            worksheet.cell(row=total_row, column=3).alignment = Alignment(horizontal="right")
            
            # Sumas (D=Litros, E=Importe, I=Efectivo)
            for col_idx, col_let in [(4, 'D'), (5, 'E'), (9, 'I')]:
                cell_total = worksheet.cell(row=total_row, column=col_idx)
                cell_total.value = f"=SUM({col_let}2:{col_let}{last_row})"
                cell_total.font = font_negra_bold
                cell_total.fill = gris_fill
                cell_total.border = borde
                cell_total.number_format = formato_moneda if col_let in ['E', 'I'] else formato_litros

            # 4. Ajuste de columnas
            for i, col in enumerate(df.columns):
                column_len = max(df[col].astype(str).map(len).max(), len(col)) + 4
                worksheet.column_dimensions[get_column_letter(i + 1)].width = column_len
        
        col_btn1.download_button(
            label="📥 Descargar Excel con Totales", 
            data=buffer.getvalue(), 
            file_name="ventas_bc_totales.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        if col_btn2.button("🗑️ Limpiar Planilla"):
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
