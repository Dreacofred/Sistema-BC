import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os
import io
import difflib
from datetime import datetime

# Herramientas de diseño para el Excel
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ==========================================
# 1. IDENTIDAD, BASES Y ENTIDADES OFICIALES
# ==========================================
COLOR_ROJO = "#C8102E"
ARCHIVO_DB = "clientes_db.json"

# 🟢 CONFIGURACIÓN: AGREGÁ TUS ENTIDADES ACÁ 🟢
ENTIDADES_OFICIALES = [
    "TRANSP HIJOS DE MARIANO FRANCOVIG SH",
    "MUNICIPALIDAD DE RECREO",
    "CAMPO PRECISION",
    "TRANSPORTE LOPEZ SRL",
    "MUNICIPALIDAD DE SANTA FE"
]

# Funciones de Memoria de Clientes
def cargar_base_clientes():
    if os.path.exists(ARCHIVO_DB):
        with open(ARCHIVO_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def guardar_nuevo_cliente(codigo, nombre):
    db = cargar_base_clientes()
    db[codigo] = nombre
    with open(ARCHIVO_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

BASE_CLIENTES = cargar_base_clientes()

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
cliente_reporte = st.sidebar.text_input("NOMBRE DEL CLIENTE AQUÍ:", placeholder="Ej: Transportes Lopez")
st.sidebar.info(f"Sistema v5.1 - Sistema Completo\nClientes guardados: {len(BASE_CLIENTES)}")

# ==========================================
# 3. MÓDULO: VENTAS A CAMIONES
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title("🚛 Registro de Carga de Camiones")
    st.subheader("📸 Paso 1: Cargar Documentos")
    
    col_f, col_o = st.columns(2)
    with col_f:
        st.markdown("### 📄 Factura")
        doc_f = st.file_uploader("Subir Foto Factura", type=["pdf","jpg","png","jpeg"], key=f"up_f_{st.session_state.contador_carga}")
    with col_o:
        st.markdown("### 🎫 Vale de Carga")
        doc_o = st.file_uploader("Subir Foto Vale", type=["jpg","png","jpeg"], key=f"up_o_{st.session_state.contador_carga}")

    if (doc_f or doc_o) and st.button("🔍 ANALIZAR DOCUMENTOS"):
        with st.spinner("Analizando con Inteligencia Artificial..."):
            try:
                contenido_ia = []
                prompt = """
                Analizá los documentos adjuntos. Extraé un JSON único con máxima precisión.
                --- MAPA EXACTO PARA LA FACTURA ---
                - 'nro_factura': Buscá "Nro." debajo del tipo de comprobante.
                - 'codigo_cliente': El número al principio de la línea del cliente (debajo del 2do CUIT).
                - 'razon_social': El resto de esa línea sin el código numérico inicial.
                - 'litros_factura': Número a la izquierda de la 'x' matemática (ej: 116,005 x 2460).
                - 'importe': Valor a la derecha de la palabra "TOTAL".
                --- REGLAS PARA EL VALE ---
                - 'fecha', 'entidad_pagadora', 'chofer'.
                - 'numero_orden_autorizacion': Número en la casilla 'ORDEN' superior. Si está tachado con una línea, dejalo en blanco.
                - 'efectivo': ATENCIÓN: Si los casilleros tienen una raya horizontal (tachado), están vacíos, o están pisados por la firma, devolvé estrictamente 0.0. No intentes leer garabatos.
                - 'orden_efectivo': Número en la casilla 'ORDEN' inferior. Si tiene una raya de tachado, dejalo en blanco.
                Devolvé ÚNICAMENTE el JSON puro. Usa punto para decimales, sin separador de miles.
                """
                contenido_ia.append(prompt)
                
                if doc_f:
                    if hasattr(doc_f, 'name') and doc_f.name.lower().endswith('.pdf'):
                        reader = PdfReader(doc_f)
                        text_pdf = "\n".join([p.extract_text() for p in reader.pages[:1]])
                        contenido_ia.append(f"Texto de Factura: {text_pdf}")
                    else:
                        contenido_ia.append(Image.open(doc_f))
                if doc_o:
                    contenido_ia.append(Image.open(doc_o))
                
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=contenido_ia)
                raw_text = res.text.strip().replace('```json', '').replace('```', '')
                start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                st.session_state.datos_temp = json.loads(raw_text[start:end])
                
            except Exception as e:
                st.error(f"Error: {e}")

    # --- FORMULARIO DE VALIDACIÓN ---
    if st.session_state.datos_temp:
        with st.form("validador_v51"):
            st.subheader("📝 Paso 2: Confirmar Información")
            
            # 1. Lógica de Clientes (Código -> Razón Social)
            codigo_ia = str(st.session_state.datos_temp.get('codigo_cliente', '')).strip()
            nombre_ia = str(st.session_state.datos_temp.get('razon_social', '')).strip()
            
            es_nuevo = False
            if codigo_ia and codigo_ia in BASE_CLIENTES:
                nombre_sugerido = BASE_CLIENTES[codigo_ia]
            else:
                nombre_sugerido = nombre_ia
                if codigo_ia:
                    es_nuevo = True

            # 2. Lógica Difusa para Entidad Pagadora
            entidad_ia = str(st.session_state.datos_temp.get('entidad_pagadora', '')).strip().upper()
            entidad_final = entidad_ia
            if entidad_ia:
                coincidencias = difflib.get_close_matches(entidad_ia, ENTIDADES_OFICIALES, n=1, cutoff=0.5)
                if coincidencias:
                    entidad_final = coincidencias[0]

            # El Cartel de Aviso visual para el playero
            if es_nuevo:
                st.info("✨ ¡Atención! Código nuevo o no reconocido. Revisá que el Cód. Cli. sea correcto.")

            c1, c2, c3, c4 = st.columns([1.5, 2, 1, 3])
            fecha = c1.text_input("Fecha", str(st.session_state.datos_temp.get('fecha', '')))
            chofer = c2.text_input("Chofer", str(st.session_state.datos_temp.get('chofer', '')))
            codigo_final = c3.text_input("Cód. Cli.", codigo_ia)
            cliente_rs = c4.text_input("Cliente de Factura", nombre_sugerido)
            
            c5, c6, c7 = st.columns(3)
            def to_f(v):
                try: 
                    v_str = str(v).strip()
                    if ',' in v_str and '.' in v_str: v_str = v_str.replace('.', '')
                    v_str = v_str.replace(',', '.')
                    return float(v_str) if v_str else 0.0
                except: return 0.0

            litros = c5.number_input("Litros", value=to_f(st.session_state.datos_temp.get('litros_factura', 0.0)), format="%.4f")
            importe = c6.number_input("Importe", value=to_f(st.session_state.datos_temp.get('importe', 0.0)))
            factura_nro = c7.text_input("Factura Nº", str(st.session_state.datos_temp.get('nro_factura', '')))
            
            entidad = st.text_input("Entidad pagadora", entidad_final)
            
            with st.expander("Órdenes y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                o_litros = ca1.text_input("Orden Litros", str(st.session_state.datos_temp.get('numero_orden_autorizacion', '')))
                v_efectivo = ca2.number_input("Efectivo", value=to_f(st.session_state.datos_temp.get('efectivo', 0.0)))
                o_efectivo = ca3.text_input("Orden Efectivo", str(st.session_state.datos_temp.get('orden_efectivo', '')))

            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                cod_l = codigo_final.strip()
                nom_l = cliente_rs.strip()
                
                # Guarda o actualiza la memoria del sistema
                if cod_l and (cod_l not in BASE_CLIENTES or BASE_CLIENTES[cod_l] != nom_l):
                    guardar_nuevo_cliente(cod_l, nom_l)

                registro = {
                    "Fecha": fecha, "Chofer": chofer, "Cliente": f"{cod_l} {nom_l}".strip() if cod_l else nom_l,
                    "Litros": litros, "Importe": importe, "Factura": factura_nro,
                    "Entidad pagadora": entidad, "Orden Litros": o_litros,
                    "Efectivo": v_efectivo, "Orden Efectivo": o_efectivo
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
            
            # --- RECUPERADO: TODO EL DISEÑO Y FORMATO DEL EXCEL ---
            fill_header = PatternFill(start_color="C8102E", end_color="C8102E", fill_type="solid")
            f_white = Font(color="FFFFFF", bold=True)
            border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            
            # Cabeceras rojas
            for cell in ws[1]:
                cell.fill, cell.font, cell.border, cell.alignment = fill_header, f_white, border, Alignment(horizontal="center")
            
            # Formatos de números y bordes
            for row in ws.iter_rows(min_row=2, max_row=last_r):
                for cell in row:
                    cell.border = border
                    # Importe (E) y Efectivo (I)
                    if cell.column_letter in ['E', 'I']: cell.number_format = '"$"#,##0.00'
                    # Litros (D)
                    if cell.column_letter == 'D': cell.number_format = '#,##0.0000'

            # Fila de TOTALES automáticos
            row_t = last_r + 1
            ws.cell(row=row_t, column=3, value="TOTALES:").font = Font(bold=True)
            for c_idx, c_let in [(4, 'D'), (5, 'E'), (9, 'I')]:
                cell_t = ws.cell(row=row_t, column=c_idx)
                cell_t.value = f"=SUM({c_let}2:{c_let}{last_r})"
                cell_t.font, cell_t.number_format = Font(bold=True), ('"$"#,##0.00' if c_let != 'D' else '#,##0.0000')

            # Ancho de columnas ajustado
            for i, col in enumerate(df.columns):
                ws.column_dimensions[get_column_letter(i + 1)].width = max(df[col].astype(str).map(len).max(), len(col)) + 4
        
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
    st.title("📄 Gestión de Proveedores")
    archivo_prov = st.file_uploader("Subir Factura", type=["pdf", "png", "jpg", "jpeg"])
    if archivo_prov and st.button("🚀 PROCESAR"):
        with st.spinner("Analizando..."):
            try:
                res = cliente.models.generate_content(
                    model='gemini-2.5-pro',
                    contents=[Image.open(archivo_prov) if not archivo_prov.name.endswith('.pdf') else archivo_prov, "Extraé CUIT, Razón Social, Fecha, Neto, IVA y Total en JSON."]
                )
                st.json(res.text.strip().replace('```json', '').replace('```', ''))
            except Exception as e:
                st.error(f"Error: {e}")
