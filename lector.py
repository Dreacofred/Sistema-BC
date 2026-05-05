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
COLOR_AMARILLO_ALERTA = "#FFE082" 
ARCHIVO_DB = "clientes_db.json"
ARCHIVO_CHOFERES = "choferes_db.json"

# 🟢 TU LISTA BLINDADA DE ENTIDADES (El sistema solo usará esta) 🟢
ENTIDADES_OFICIALES = [
    "TRANSP HIJOS DE MARIANO FRANCOVIG SH",
    "MUNICIPALIDAD DE RECREO",
    "CAMPO PRECISION",
    "TRANSPORTE LOPEZ SRL",
    "MUNICIPALIDAD DE SANTA FE",
    "RUIZ JULIAN",
    "RUIZ MARCELO"
]

def cargar_db_diccionario(archivo):
    if os.path.exists(archivo):
        with open(archivo, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def cargar_db_lista(archivo):
    if os.path.exists(archivo):
        with open(archivo, 'r', encoding='utf-8') as f: return json.load(f)
    return []

def guardar_nuevo_cliente(codigo, nombre):
    db = cargar_db_diccionario(ARCHIVO_DB)
    db[codigo] = nombre
    with open(ARCHIVO_DB, 'w', encoding='utf-8') as f: json.dump(db, f, indent=4, ensure_ascii=False)

def guardar_nuevo_item(archivo, item):
    if not item: return
    lista = cargar_db_lista(archivo)
    if item not in lista:
        lista.append(item)
        lista.sort() 
        with open(archivo, 'w', encoding='utf-8') as f: json.dump(lista, f, indent=4, ensure_ascii=False)

def borrar_item_especifico(archivo, item_a_borrar):
    if not os.path.exists(archivo): return
    lista = cargar_db_lista(archivo)
    if item_a_borrar in lista:
        lista.remove(item_a_borrar)
        with open(archivo, 'w', encoding='utf-8') as f: json.dump(lista, f, indent=4, ensure_ascii=False)
        st.rerun()

def obtener_nombre_cache(usuario):
    usuario_limpio = "".join(x for x in usuario if x.isalnum()).lower()
    return f"cache_ventas_{usuario_limpio}.json"

def guardar_cache_ventas(lista_ventas, usuario):
    archivo = obtener_nombre_cache(usuario)
    with open(archivo, 'w', encoding='utf-8') as f: json.dump(lista_ventas, f, indent=4, ensure_ascii=False)

def recuperar_cache_ventas(usuario):
    archivo = obtener_nombre_cache(usuario)
    if os.path.exists(archivo):
        with open(archivo, 'r', encoding='utf-8') as f: return json.load(f)
    return []

BASE_CLIENTES = cargar_db_diccionario(ARCHIVO_DB)
BASE_CHOFERES = cargar_db_lista(ARCHIVO_CHOFERES)

st.set_page_config(page_title="BC Combustibles - Gestión Pro", page_icon="⛽", layout="wide")

st.markdown(f"""
    <style>
        .stApp {{ background-color: white !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; }}
        .stButton>button {{ background-color: {COLOR_ROJO}; color: white; border-radius: 12px; font-weight: bold; height: 3em; border: none; width: 100%; }}
        [data-testid="stSidebar"] {{ background-color: #f8f9fa; border-right: 1px solid #e0e0e0; }}
        .stDataFrame {{ border: 1px solid #e0e0e0; border-radius: 8px; }}
        [data-testid="stSidebar"] .stTextInput div[data-baseweb="input"] {{ border: 2px solid {COLOR_ROJO} !important; border-radius: 8px !important; background-color: #ffffff !important; }}
        .alerta-ingreso {{ padding: 20px; border-radius: 15px; background-color: #fff3f3; border-left: 5px solid {COLOR_ROJO}; color: #721c24; font-weight: bold; text-align: center; font-size: 1.2em; }}
        
        .bloque-alerta {{ background-color: #fff8e1; padding: 15px; border-radius: 10px; border: 1px solid {COLOR_AMARILLO_ALERTA}; border-left: 4px solid {COLOR_AMARILLO_ALERTA}; margin-bottom: 10px; color: #856404; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

cliente_ia = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo: st.sidebar.image(ruta_logo, use_container_width=True)

st.sidebar.subheader("👤 Identificación")
usuario_app = st.sidebar.text_input("Tu nombre para operar:", value="", placeholder="Ej: Nancy o Diego")

if not usuario_app.strip():
    st.title("⛽ Sistema de Gestión BC Combustibles")
    st.markdown("""<div class="alerta-ingreso">⚠️ ACCESO RESTRINGIDO<br>Ingresá tu nombre en el panel lateral para habilitar el sistema.</div>""", unsafe_allow_html=True)
    st.stop()

if 'lote_pendientes' not in st.session_state: st.session_state.lote_pendientes = []
if 'cola_extracciones' not in st.session_state: st.session_state.cola_extracciones = []

if 'usuario_actual' not in st.session_state or st.session_state.usuario_actual != usuario_app:
    st.session_state.usuario_actual = usuario_app
    st.session_state.resumen_ventas = recuperar_cache_ventas(usuario_app)

opcion = st.sidebar.radio("Seleccioná la tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores"])
st.sidebar.divider()
cliente_reporte = st.sidebar.text_input("Nombre Excel Final:", placeholder="Ej: Resumen_Sucursal")
st.sidebar.info(f"Sesión: {st.session_state.usuario_actual}\nExcel: {len(st.session_state.resumen_ventas)} filas\nEn cola IA: {len(st.session_state.cola_extracciones)}")

# 🟢 PANEL DE MANTENIMIENTO MEJORADO 🟢
with st.sidebar.expander("🛠️ Mantenimiento de Memorias"):
    st.write("Si el sistema autocompleta mal un chofer, podés borrarlo acá.")
    if st.button("🗑️ Limpiar TODAS las bases (Choferes y Clientes)"):
        for arch in [ARCHIVO_DB, ARCHIVO_CHOFERES]:
            if os.path.exists(arch): os.remove(arch)
        st.success("✅ Bases limpiadas.")
        st.rerun()

    st.markdown("---")
    st.write("📋 **Choferes Aprendidos**")
    base_choferes_sidebar = cargar_db_lista(ARCHIVO_CHOFERES)
    if base_choferes_sidebar:
        for ch in base_choferes_sidebar:
            col_ch1, col_ch2 = st.columns([4, 1])
            col_ch1.markdown(f"<div style='font-size: 0.9em; padding-top: 5px;'>{ch}</div>", unsafe_allow_html=True)
            if col_ch2.button("🗑️", key=f"borrar_ch_{ch}"):
                borrar_item_especifico(ARCHIVO_CHOFERES, ch)
    else: st.write("*La lista está vacía.*")

if opcion == "🚛 Ventas a Camiones":
    if len(st.session_state.cola_extracciones) > 0:
        st.title(f"🔄 Cinta Transportadora - {st.session_state.usuario_actual}")
        total_restantes = len(st.session_state.cola_extracciones)
        st.warning(f"Tienes {total_restantes} documento(s) esperando tu revisión.")
        
        datos_actuales = st.session_state.cola_extracciones[0]
        st.subheader(f"📝 Revisando: {datos_actuales.get('_origen', 'Documento desconocido')}")

        with st.form("validador_lote"):
            def limpiar_texto(v): return "" if str(v).strip().lower() in ["none", "null", ""] else str(v).strip()
            def to_f(v):
                try: 
                    v_str = str(v).strip().replace('.', '').replace(',', '.') if ',' in str(v) and '.' in str(v) else str(v).strip().replace(',', '.')
                    return float(v_str) if v_str else 0.0
                except: return 0.0

            codigo_ia = limpiar_texto(datos_actuales.get('codigo_cliente', ''))
            nombre_ia = limpiar_texto(datos_actuales.get('razon_social', ''))
            v_fecha = limpiar_texto(datos_actuales.get('fecha', ''))
            v_chofer = limpiar_texto(datos_actuales.get('chofer', '')).upper()
            v_o_litros = limpiar_texto(datos_actuales.get('numero_orden_autorizacion', ''))
            v_efectivo = to_f(datos_actuales.get('efectivo', 0.0))
            v_o_efectivo = limpiar_texto(datos_actuales.get('orden_efectivo', ''))
            
            nombre_sugerido = BASE_CLIENTES.get(codigo_ia, nombre_ia)
            es_nuevo_cli = bool(codigo_ia and codigo_ia not in BASE_CLIENTES)

            chofer_final = v_chofer
            if v_chofer and BASE_CHOFERES:
                coincidencias_c = difflib.get_close_matches(v_chofer, BASE_CHOFERES, n=1, cutoff=0.5)
                if coincidencias_c: chofer_final = coincidencias_c[0]

            # 🟢 LA ENTIDAD SE COMPARA SOLO CON TU LISTA DEL CÓDIGO 🟢
            entidad_ia = limpiar_texto(datos_actuales.get('entidad_pagadora', '')).upper()
            entidad_final = entidad_ia
            if entidad_ia and ENTIDADES_OFICIALES:
                coincidencias_e = difflib.get_close_matches(entidad_ia, ENTIDADES_OFICIALES, n=1, cutoff=0.4)
                if coincidencias_e: entidad_final = coincidencias_e[0]

            es_novedad_chofer = bool(chofer_final and chofer_final not in BASE_CHOFERES)

            if es_nuevo_cli: st.info("✨ ¡Atención! Código de cliente nuevo detectado.")
            
            if es_novedad_chofer:
                st.markdown(f"""
                    <div class="bloque-alerta">
                        ⚠️ ATENCIÓN NANCY:<br>
                        El chofer en pantalla no figura en la memoria del sistema.<br>
                        Por favor, revisá que esté BIEN escrito antes de guardar.
                    </div>
                """, unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns([1.5, 2, 1, 3])
            fecha = c1.text_input("Fecha", v_fecha)
            chofer = c2.text_input("Chofer", chofer_final)
            codigo_final = c3.text_input("Cód. Cli.", codigo_ia)
            cliente_rs = c4.text_input("Cliente de Factura", nombre_sugerido)
            
            c5, c6, c7 = st.columns(3)
            litros = c5.number_input("Litros", value=to_f(datos_actuales.get('litros_factura', 0.0)), format="%.4f")
            importe = c6.number_input("Importe", value=to_f(datos_actuales.get('importe', 0.0)))
            factura_nro = c7.text_input("Factura Nº", limpiar_texto(datos_actuales.get('nro_factura', '')))
            entidad = st.text_input("Entidad pagadora", entidad_final)
            
            with st.expander("Órdenes y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                o_litros = ca1.text_input("Orden Litros", v_o_litros)
                val_efectivo = ca2.number_input("Efectivo", value=v_efectivo)
                o_efectivo = ca3.text_input("Orden Efectivo", v_o_efectivo)

            st.markdown("<br>", unsafe_allow_html=True)
            col_b1, col_b2 = st.columns(2)
            btn_guardar = col_b1.form_submit_button("✅ GUARDAR Y VER SIGUIENTE")
            btn_descartar = col_b2.form_submit_button("🗑️ DESCARTAR (Mala foto/Error)")

            if btn_guardar:
                cod_l = codigo_final.strip().upper()
                nom_l = cliente_rs.strip().upper()
                chofer_l = chofer.strip().upper()
                entidad_l = entidad.strip().upper()

                if cod_l and (cod_l not in BASE_CLIENTES or BASE_CLIENTES[cod_l] != nom_l): guardar_nuevo_cliente(cod_l, nom_l)
                # 🟢 ACÁ SE GUARDA EL CHOFER PERO YA NO LA ENTIDAD 🟢
                if chofer_l: guardar_nuevo_item(ARCHIVO_CHOFERES, chofer_l)

                registro = {
                    "Fecha": fecha.strip(), "Chofer": chofer_l, "Cliente": f"{cod_l} {nom_l}".strip(),
                    "Litros": litros, "Importe": importe, "Factura": factura_nro.strip().upper(),
                    "Entidad pagadora": entidad_l, "Orden Litros": str(o_litros).strip().upper(),
                    "Efectivo": val_efectivo, "Orden Efectivo": str(o_efectivo).strip().upper()
                }
                st.session_state.resumen_ventas.append(registro)
                guardar_cache_ventas(st.session_state.resumen_ventas, st.session_state.usuario_actual)
                st.session_state.cola_extracciones.pop(0) 
                st.rerun()
            
            if btn_descartar:
                st.session_state.cola_extracciones.pop(0)
                st.rerun()

    else:
        st.title(f"🚛 Registro de Cargas - {st.session_state.usuario_actual}")
        st.subheader("📸 Paso 1: Recolectar Documentos")
        
        tab1, tab2 = st.tabs(["📁 Subir Archivos (PC)", "📸 Cámara en Vivo"])
        
        with tab1:
            fotos_disco = st.file_uploader("Seleccionar comprobantes", type=["pdf","jpg","png","jpeg"], accept_multiple_files=True)
            if fotos_disco:
                if st.button("➕ Sumar archivos a la Pila"):
                    for f in fotos_disco: st.session_state.lote_pendientes.append({'nombre': f.name, 'data': f.getvalue(), 'tipo': f.type})
                    st.success(f"✅ Se sumaron los archivos. Ya tenés {len(st.session_state.lote_pendientes)} comprobantes en la pila.")

        with tab2:
            foto_camara = st.camera_input("Enfocar documento")
            if foto_camara:
                if st.button("➕ Sumar captura a la Pila"):
                    st.session_state.lote_pendientes.append({'nombre': f"Captura_{len(st.session_state.lote_pendientes)+1}.jpg", 'data': foto_camara.getvalue(), 'tipo': foto_camara.type})
                    st.success(f"✅ ¡Agregado! Pila: {len(st.session_state.lote_pendientes)}")
        
        st.divider()
        st.subheader("📦 Pila de Trabajo")
        if st.session_state.lote_pendientes:
            col_lote1, col_lote2 = st.columns([3, 1])
            
            if col_lote1.button("🚀 INICIAR ANÁLISIS DE LOTE COMPLETO"):
                with st.spinner("La Inteligencia Artificial está leyendo..."):
                    prompt = """
                    Analizá la imagen adjunta. Hay DOS comprobantes en la foto: un ticket largo (Factura) y un papel con casilleros (Vale de Carga). Extraé un JSON único.
                    --- MAPA FACTURA ---
                    - 'fecha': Fecha impresa junto a "Hora:".
                    - 'nro_factura': Buscá "Nro." debajo del tipo de comprobante.
                    - 'codigo_cliente': Número CORTO al inicio del nombre del cliente. NO ES EL CUIT.
                    - 'razon_social': Nombre del cliente (sin el código).
                    - 'litros_factura': Número exacto a la izquierda de la 'x'.
                    - 'importe': Valor a la derecha de "TOTAL".
                    --- MAPA VALE DE CARGA ---
                    ATENCIÓN: Buscá en la foto el papel que tiene escrito "VALE DE CARGA". Leé EXCLUSIVAMENTE los datos escritos a mano dentro de ese papel. Prohibido sacar el nombre de firmas en el ticket blanco.
                    - 'chofer': Extraé el nombre escrito en los casilleros del renglón "CHOFER".
                    - 'entidad_pagadora': Texto en el renglón "ENTIDAD PAGADORA".
                    - 'numero_orden_autorizacion': Número en la casilla "ORDEN" superior.
                    - 'efectivo': Mirá el renglón "EFECTIVO". Hay números que cruzan las líneas verticales del diseño de la grilla. LAS LÍNEAS IMPRESAS DEL PAPEL NO SON TACHADURAS. Extraé el número exacto. Solo poné 0.0 si la cajita de efectivo está completamente vacía.
                    - 'orden_efectivo': Número en la casilla "ORDEN" inferior.
                    Devolvé ÚNICAMENTE JSON puro. Usa punto para decimales.
                    """
                    for doc in st.session_state.lote_pendientes:
                        try:
                            contenido_ia = [prompt]
                            if 'pdf' in doc['tipo']:
                                reader = PdfReader(io.BytesIO(doc['data']))
                                contenido_ia.append(f"Texto del documento: {' '.join([p.extract_text() for p in reader.pages[:1]])}")
                            else:
                                contenido_ia.append(Image.open(io.BytesIO(doc['data'])))
                                
                            res = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=contenido_ia)
                            raw_text = res.text.strip().replace('```json', '').replace('```', '')
                            start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                            datos_extraidos = json.loads(raw_text[start:end])
                            datos_extraidos['_origen'] = doc['nombre']
                            st.session_state.cola_extracciones.append(datos_extraidos)
                        except Exception as e:
                            st.session_state.cola_extracciones.append({'_origen': f"⚠️ ERROR DE LECTURA en {doc['nombre']} (Completar manual)"})
                    
                    st.session_state.lote_pendientes = [] 
                    st.rerun() 
            
            if col_lote2.button("🗑️ Vaciar Pila"):
                st.session_state.lote_pendientes = []
                st.rerun()

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        cols = ["Fecha", "Chofer", "Cliente", "Litros", "Importe", "Factura", "Entidad pagadora", "Orden Litros", "Efectivo", "Orden Efectivo"]
        df = df[cols]
        
        st.subheader(f"📋 Planilla Final de {st.session_state.usuario_actual} ({len(df)} registros)")
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
        
        if col_ex2.button("🗑️ Vaciar Planilla Final", use_container_width=True):
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
                res = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[Image.open(archivo_prov) if not archivo_prov.name.endswith('.pdf') else archivo_prov, "Extraé CUIT, Razón Social, Fecha, Neto, IVA y Total en JSON."])
                st.json(res.text.strip().replace('```json', '').replace('```', ''))
            except Exception as e: st.error(f"Error: {e}")
