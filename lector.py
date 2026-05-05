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
# 1. IDENTIDAD, BASES Y ARCHIVOS DE SEGURIDAD
# ==========================================
COLOR_ROJO = "#C8102E"
ARCHIVO_DB = "clientes_db.json"

ENTIDADES_OFICIALES = [
    "TRANSP HIJOS DE MARIANO FRANCOVIG SH",
    "MUNICIPALIDAD DE RECREO",
    "CAMPO PRECISION",
    "TRANSPORTE LOPEZ SRL",
    "MUNICIPALIDAD DE SANTA FE"
]

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

def obtener_nombre_cache(usuario):
    usuario_limpio = "".join(x for x in usuario if x.isalnum()).lower()
    return f"cache_ventas_{usuario_limpio}.json"

def guardar_cache_ventas(lista_ventas, usuario):
    archivo = obtener_nombre_cache(usuario)
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(lista_ventas, f, indent=4, ensure_ascii=False)

def recuperar_cache_ventas(usuario):
    archivo = obtener_nombre_cache(usuario)
    if os.path.exists(archivo):
        with open(archivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

BASE_CLIENTES = cargar_base_clientes()

st.set_page_config(page_title="BC Combustibles - Gestión Pro", page_icon="⛽", layout="wide")

# Estilos Visuales
st.markdown(f"""
    <style>
        .stApp {{ background-color: white !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; }}
        .stButton>button {{
            background-color: {COLOR_ROJO}; color: white; border-radius: 12px; font-weight: bold; height: 3em; border: none; width: 100%;
        }}
        [data-testid="stSidebar"] {{ background-color: #f8f9fa; border-right: 1px solid #e0e0e0; }}
        .stDataFrame {{ border: 1px solid #e0e0e0; border-radius: 8px; }}
        [data-testid="stSidebar"] .stTextInput div[data-baseweb="input"] {{
            border: 2px solid {COLOR_ROJO} !important; border-radius: 8px !important; background-color: #ffffff !important;
        }}
        .alerta-ingreso {{
            padding: 20px; border-radius: 15px; background-color: #fff3f3; border-left: 5px solid {COLOR_ROJO};
            color: #721c24; font-weight: bold; text-align: center; font-size: 1.2em;
        }}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONFIGURACIÓN Y ESTADO DE SESIÓN
# ==========================================
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo:
    st.sidebar.image(ruta_logo, use_container_width=True)

# 🛑 CONTROL DE IDENTIDAD OBLIGATORIO 🛑
st.sidebar.subheader("👤 Identificación Requerida")
usuario_app = st.sidebar.text_input("Ingresá tu nombre para operar:", value="", placeholder="Ej: Nancy o Diego")

if not usuario_app.strip():
    st.title("⛽ Sistema de Gestión BC Combustibles")
    st.markdown("""
        <div class="alerta-ingreso">
            ⚠️ ACCESO RESTRINGIDO<br>
            Por favor, ingresá tu nombre en el panel lateral para habilitar las funciones del sistema.
        </div>
        <br>
        <p style='text-align: center; color: #666;'>
            Esto asegura que tus cargas se guarden de forma privada y no se mezclen con las de otros encargados.
        </p>
    """, unsafe_allow_html=True)
    st.stop()

if 'usuario_actual' not in st.session_state or st.session_state.usuario_actual != usuario_app:
    st.session_state.usuario_actual = usuario_app
    st.session_state.resumen_ventas = recuperar_cache_ventas(usuario_app)

if 'contador_carga' not in st.session_state:
    st.session_state.contador_carga = 0
if 'datos_temp' not in st.session_state:
    st.session_state.datos_temp = None

opcion = st.sidebar.radio("Seleccioná la tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])
st.sidebar.divider()
cliente_reporte = st.sidebar.text_input("Nombre Excel Final:", placeholder="Ej: Resumen_Sucursal")
st.sidebar.info(f"Sesión activa: {st.session_state.usuario_actual}\nCargas recuperadas: {len(st.session_state.resumen_ventas)}")

# ==========================================
# 3. MÓDULO: VENTAS A CAMIONES
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    st.title(f"🚛 Registro de Cargas - {st.session_state.usuario_actual}")
    st.subheader("📸 Paso 1: Escanear Documentación")
    
    doc_unico = st.file_uploader("Subir Fotografía", type=["pdf","jpg","png","jpeg"], key=f"up_unico_{st.session_state.contador_carga}")

    if doc_unico and st.button("🔍 ANALIZAR DOCUMENTACIÓN"):
        with st.spinner("Analizando..."):
            try:
                contenido_ia = []
                prompt = """
                Analizá la imagen adjunta. Extraé un JSON único con máxima precisión.
                --- MAPA FACTURA ---
                - 'fecha': Buscá la palabra "Hora:". A la izquierda está la Fecha impresa. Usá esta.
                - 'nro_factura', 'codigo_cliente', 'razon_social'.
                - 'litros_factura': Número exacto a la izquierda de la 'x'. No inventes dígitos.
                - 'importe': Valor a la derecha de "TOTAL".
                --- MAPA VALE ---
                - 'chofer': OBLIGATORIO extraer nombre manuscrito.
                - 'entidad_pagadora': Extraé EXACTAMENTE lo escrito.
                - 'numero_orden_autorizacion': Número en casilla 'ORDEN' superior.
                - 'efectivo': Número manuscrito. Ignora líneas de diseño. Si hay raya de anulación total, devolvé 0.0.
                - 'orden_efectivo': Número en casilla 'ORDEN' inferior.
                Devolvé ÚNICAMENTE JSON puro. Usa punto para decimales.
                """
                contenido_ia.append(prompt)
                
                if hasattr(doc_unico, 'name') and doc_unico.name.lower().endswith('.pdf'):
                    reader = PdfReader(doc_unico)
                    text_pdf = "\n".join([p.extract_text() for p in reader.pages[:1]])
                    contenido_ia.append(f"Texto del documento: {text_pdf}")
                else:
                    contenido_ia.append(Image.open(doc_unico))
                
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=contenido_ia)
                raw_text = res.text.strip().replace('```json', '').replace('```', '')
                start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                st.session_state.datos_temp = json.loads(raw_text[start:end])
                
            except Exception as e:
                st.error(f"Error: {e}")

    # --- FORMULARIO DE VALIDACIÓN ---
    if st.session_state.datos_temp:
        with st.form("validador_v69"):
            st.subheader("📝 Paso 2: Confirmar Información")
            
            def limpiar_texto(v):
                s = str(v).strip()
                return "" if s.lower() in ["none", "null", ""] else s

            def to_f(v):
                try: 
                    v_str = str(v).strip().replace('.', '').replace(',', '.') if ',' in str(v) and '.' in str(v) else str(v).strip().replace(',', '.')
                    return float(v_str) if v_str else 0.0
                except: return 0.0

            codigo_ia = limpiar_texto(st.session_state.datos_temp.get('codigo_cliente', ''))
            nombre_ia = limpiar_texto(st.session_state.datos_temp.get('razon_social', ''))
            v_fecha = limpiar_texto(st.session_state.datos_temp.get('fecha', ''))
            v_chofer = limpiar_texto(st.session_state.datos_temp.get('chofer', ''))
            v_o_litros = limpiar_texto(st.session_state.datos_temp.get('numero_orden_autorizacion', ''))
            v_efectivo = to_f(st.session_state.datos_temp.get('efectivo', 0.0))
            v_o_efectivo = limpiar_texto(st.session_state.datos_temp.get('orden_efectivo', ''))
            
            nombre_sugerido = BASE_CLIENTES.get(codigo_ia, nombre_ia)
            es_nuevo = bool(codigo_ia and codigo_ia not in BASE_CLIENTES)

            entidad_ia = limpiar_texto(st.session_state.datos_temp.get('entidad_pagadora', '')).upper()
            entidad_final = entidad_ia
            if entidad_ia:
                coincidencias = difflib.get_close_matches(entidad_ia, ENTIDADES_OFICIALES, n=1, cutoff=0.4)
                if coincidencias: entidad_final = coincidencias[0]

            if es_nuevo: st.info("✨ ¡Atención! Código nuevo detectado.")
            if bool(v_chofer or v_o_litros) and not entidad_final: 
                st.warning("⚠️ ¡Atención! Falta la Entidad Pagadora del Vale.")

            c1, c2, c3, c4 = st.columns([1.5, 2, 1, 3])
            fecha = c1.text_input("Fecha", v_fecha)
            chofer = c2.text_input("Chofer", v_chofer)
            codigo_final = c3.text_input("Cód. Cli.", codigo_ia)
            cliente_rs = c4.text_input("Cliente de Factura", nombre_sugerido)
            
            c5, c6, c7 = st.columns(3)
            litros = c5.number_input("Litros", value=to_f(st.session_state.datos_temp.get('litros_factura', 0.0)), format="%.4f")
            importe = c6.number_input("Importe", value=to_f(st.session_state.datos_temp.get('importe', 0.0)))
            factura_nro = c7.text_input("Factura Nº", limpiar_texto(st.session_state.datos_temp.get('nro_factura', '')))
            entidad = st.text_input("Entidad pagadora", entidad_final)
            
            with st.expander("Órdenes y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                o_litros = ca1.text_input("Orden Litros", v_o_litros)
                val_efectivo = ca2.number_input("Efectivo", value=v_efectivo)
                o_efectivo = ca3.text_input("Orden Efectivo", v_o_efectivo)

            if st.form_submit_button("✅ GUARDAR EN PLANILLA"):
                # 🟢 ACÁ ESTÁ EL FILTRO EMBELLECEDOR (TODO A MAYÚSCULAS) 🟢
                cod_l = codigo_final.strip().upper()
                nom_l = cliente_rs.strip().upper()
                
                if cod_l and (cod_l not in BASE_CLIENTES or BASE_CLIENTES[cod_l] != nom_l):
                    guardar_nuevo_cliente(cod_l, nom_l)

                registro = {
                    "Fecha": fecha.strip(), 
                    "Chofer": chofer.strip().upper(), 
                    "Cliente": f"{cod_l} {nom_l}".strip(),
                    "Litros": litros, 
                    "Importe": importe, 
                    "Factura": factura_nro.strip().upper(),
                    "Entidad pagadora": entidad.strip().upper(), 
                    "Orden Litros": str(o_litros).strip().upper(),
                    "Efectivo": val_efectivo, 
                    "Orden Efectivo": str(o_efectivo).strip().upper()
                }
                st.session_state.resumen_ventas.append(registro)
                guardar_cache_ventas(st.session_state.resumen_ventas, st.session_state.usuario_actual)
                st.session_state.datos_temp = None
                st.session_state.contador_carga += 1
                st.rerun()

    # --- TABLA Y EXPORTACIÓN ---
    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        cols = ["Fecha", "Chofer", "Cliente", "Litros", "Importe", "Factura", "Entidad pagadora", "Orden Litros", "Efectivo", "Orden Efectivo"]
        df = df[cols]
        
        st.subheader(f"📋 Planilla de {st.session_state.usuario_actual} ({len(df)} registros)")
        st.dataframe(df, use_container_width=True)
        
        col_ex1, col_ex2 = st.columns(2)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ventas')
            ws = writer.sheets['Ventas']
            last_r = len(df) + 1
            fill_header = PatternFill(start_color="C8102E", end_color="C8102E", fill_type="solid")
            for cell in ws[1]:
                cell.fill, cell.font, cell.border, cell.alignment = fill_header, Font(color="FFFFFF", bold=True), Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin')), Alignment(horizontal="center")
            
            for row in ws.iter_rows(min_row=2, max_row=last_r):
                for cell in row:
                    cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
                    if cell.column_letter in ['E', 'I']: cell.number_format = '"$"#,##0.00'
                    if cell.column_letter == 'D': cell.number_format = '#,##0.0000'

            row_t = last_r + 1
            ws.cell(row=row_t, column=3, value="TOTALES:").font = Font(bold=True)
            for c_idx, c_let in [(4, 'D'), (5, 'E'), (9, 'I')]:
                cell_t = ws.cell(row=row_t, column=c_idx)
                cell_t.value = f"=SUM({c_let}2:{c_let}{last_r})"
                cell_t.font, cell_t.number_format = Font(bold=True), ('"$"#,##0.00' if c_let != 'D' else '#,##0.0000')

            for i, col in enumerate(df.columns):
                ws.column_dimensions[get_column_letter(i + 1)].width = max(df[col].astype(str).map(len).max(), len(col)) + 4
        
        fecha_hoy = datetime.now().strftime("%d-%m-%Y")
        nombre_archivo = f"{cliente_reporte.strip() or 'Resumen'}_{fecha_hoy}.xlsx"
        col_ex1.download_button(label=f"📥 Descargar Excel", data=buffer.getvalue(), file_name=nombre_archivo, use_container_width=True)
        
        if col_ex2.button("🗑️ Vaciar Todo", use_container_width=True):
            st.session_state.resumen_ventas = []
            archivo_usuario = obtener_nombre_cache(st.session_state.usuario_actual)
            if os.path.exists(archivo_usuario): os.remove(archivo_usuario)
            st.rerun()

elif opcion == "📄 Facturas de Proveedores":
    st.title("📄 Gestión de Proveedores")
    archivo_prov = st.file_uploader("Subir Factura", type=["pdf", "png", "jpg", "jpeg"])
    if archivo_prov and st.button("🚀 PROCESAR"):
        with st.spinner("Analizando..."):
            try:
                res = cliente.models.generate_content(model='gemini-2.5-pro', contents=[Image.open(archivo_prov) if not archivo_prov.name.endswith('.pdf') else archivo_prov, "Extraé CUIT, Razón Social, Fecha, Neto, IVA y Total en JSON."])
                st.json(res.text.strip().replace('```json', '').replace('```', ''))
            except Exception as e: st.error(f"Error: {e}")
