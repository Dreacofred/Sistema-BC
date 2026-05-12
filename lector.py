import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd
import json
import os
import io
import difflib
import time
from datetime import datetime
from supabase import create_client, Client

# Herramientas de diseño para el Excel
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ==========================================
# 1. IDENTIDAD, CONEXIÓN Y SEGURIDAD
# ==========================================
COLOR_ROJO = "#C8102E"
COLOR_AMARILLO_ALERTA = "#FFE082" 
ARCHIVO_DB = "clientes_db.json"
ARCHIVO_CHOFERES = "choferes_db.json"

# Credenciales de Supabase
URL_SB = "https://bjhykcdhafoqpfkpngvw.supabase.co"
KEY_SB = "sb_publishable_OvXN3LjawazkF5GNpsslUQ_SQOhTakr"
supabase: Client = create_client(URL_SB, KEY_SB)

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
        [data-testid="stSidebarNav"] {{display: none !important;}}
        .stApp {{ background-color: white !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; }}
        .stButton>button {{ background-color: {COLOR_ROJO}; color: white; border-radius: 12px; font-weight: bold; height: 3em; border: none; width: 100%; }}
        [data-testid="stSidebar"] {{ background-color: #f8f9fa; border-right: 1px solid #e0e0e0; }}
        .alerta-ingreso {{ padding: 20px; border-radius: 15px; background-color: #fff3f3; border-left: 5px solid {COLOR_ROJO}; color: #721c24; font-weight: bold; text-align: center; font-size: 1.2em; }}
        .bloque-alerta {{ background-color: #fff8e1; padding: 15px; border-radius: 10px; border: 1px solid {COLOR_AMARILLO_ALERTA}; border-left: 4px solid {COLOR_AMARILLO_ALERTA}; margin-bottom: 10px; color: #856404; font-weight: bold; }}
    </style>
""", unsafe_allow_html=True)

cliente_ia = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

st.sidebar.markdown("<br>", unsafe_allow_html=True)
ruta_logo = next((v for v in ["Logo.jpeg", "Logo.jpg", "logo.png"] if os.path.exists(v)), None)
if ruta_logo: st.sidebar.image(ruta_logo, use_container_width=True)

# ==========================================
# 2. IDENTIFICACIÓN
# ==========================================
st.sidebar.subheader("👤 Identificación")

if 'usuario_actual' not in st.session_state:
    st.session_state.usuario_actual = ""

usuario_app = st.sidebar.text_input(
    "Tu nombre para operar:", 
    value=st.session_state.usuario_actual, 
    placeholder="Ej: Nancy o Diego"
)

if usuario_app != st.session_state.usuario_actual:
    st.session_state.usuario_actual = usuario_app
    st.session_state.resumen_ventas = recuperar_cache_ventas(usuario_app)

if not st.session_state.usuario_actual.strip():
    st.title("⛽ Sistema de Gestión BC Combustibles")
    st.markdown("""<div class="alerta-ingreso">⚠️ ACCESO RESTRINGIDO<br>Ingresá tu nombre en el panel lateral para habilitar el sistema.</div>""", unsafe_allow_html=True)
    st.stop()

st.sidebar.info(f"Operador activo: {st.session_state.usuario_actual}")

# Inicializar estados
if 'lote_pendientes' not in st.session_state: st.session_state.lote_pendientes = []
if 'cola_extracciones' not in st.session_state: st.session_state.cola_extracciones = []
if 'resumen_ventas' not in st.session_state: st.session_state.resumen_ventas = []
if 'lote_pendientes_prov' not in st.session_state: st.session_state.lote_pendientes_prov = []
if 'cola_extracciones_prov' not in st.session_state: st.session_state.cola_extracciones_prov = []
if 'resumen_prov' not in st.session_state: st.session_state.resumen_prov = []
if 'resumen_para_cliente' not in st.session_state: st.session_state.resumen_para_cliente = []

opcion = st.sidebar.radio("Seleccioná la tarea:", ["🚛 Ventas a Camiones", "📄 Facturas de Proveedores", "🔍 Auditoría de Remitos"])
st.sidebar.divider()

# ==========================================
# 3. MÓDULO VENTAS A CAMIONES
# ==========================================
if opcion == "🚛 Ventas a Camiones":
    if len(st.session_state.cola_extracciones) > 0:
        st.title(f"🔄 Revisión de Cargas - {st.session_state.usuario_actual}")
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

            entidad_ia = limpiar_texto(datos_actuales.get('entidad_pagadora', '')).upper()
            entidad_final = entidad_ia
            if entidad_ia and ENTIDADES_OFICIALES:
                coincidencias_e = difflib.get_close_matches(entidad_ia, ENTIDADES_OFICIALES, n=1, cutoff=0.4)
                if coincidencias_e: entidad_final = coincidencias_e[0]

            if es_nuevo_cli: st.info("✨ ¡Atención! Código de cliente nuevo detectado.")
            if chofer_final and chofer_final not in BASE_CHOFERES:
                st.markdown(f"""<div class="bloque-alerta">⚠️ ATENCIÓN {st.session_state.usuario_actual.upper()}:<br>El chofer no figura en la memoria. Revisá que esté bien escrito.</div>""", unsafe_allow_html=True)

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
            if col_b1.form_submit_button("✅ GUARDAR Y VER SIGUIENTE"):
                cod_l, nom_l, chofer_l, entidad_l = codigo_final.strip().upper(), cliente_rs.strip().upper(), chofer.strip().upper(), entidad.strip().upper()
                if cod_l and (cod_l not in BASE_CLIENTES or BASE_CLIENTES[cod_l] != nom_l): guardar_nuevo_cliente(cod_l, nom_l)
                if chofer_l: guardar_nuevo_item(ARCHIVO_CHOFERES, chofer_l)
                registro = {"Fecha": fecha.strip(), "Chofer": chofer_l, "Cliente": f"{cod_l} {nom_l}".strip(), "Litros": litros, "Importe": importe, "Factura": factura_nro.strip().upper(), "Entidad pagadora": entidad_l, "Orden Litros": str(o_litros).strip().upper(), "Efectivo": val_efectivo, "Orden Efectivo": str(o_efectivo).strip().upper()}
                st.session_state.resumen_ventas.append(registro)
                guardar_cache_ventas(st.session_state.resumen_ventas, st.session_state.usuario_actual)
                st.session_state.cola_extracciones.pop(0) 
                st.rerun()
            
            if col_b2.form_submit_button("🗑️ DESCARTAR"):
                st.session_state.cola_extracciones.pop(0)
                st.rerun()

    else:
        st.title(f"🚛 Registro de Cargas - {st.session_state.usuario_actual}")
        tab1, tab2 = st.tabs(["📁 Subir Archivos", "📸 Cámara"])
        with tab1:
            fotos_disco = st.file_uploader("Seleccionar comprobantes", type=["pdf","jpg","png","jpeg"], accept_multiple_files=True)
            if fotos_disco and st.button("➕ Sumar archivos a la Pila"):
                for f in fotos_disco: st.session_state.lote_pendientes.append({'nombre': f.name, 'data': f.getvalue(), 'tipo': f.type})
                st.success(f"✅ Se sumaron {len(fotos_disco)} archivos.")

        with tab2:
            foto_camara = st.camera_input("Enfocar documento")
            if foto_camara and st.button("➕ Sumar captura a la Pila"):
                st.session_state.lote_pendientes.append({'nombre': f"Captura_{len(st.session_state.lote_pendientes)+1}.jpg", 'data': foto_camara.getvalue(), 'tipo': foto_camara.type})
                st.success("✅ ¡Agregado!")
        
        st.divider()
        if st.session_state.lote_pendientes:
            st.subheader(f"📦 Pila de Trabajo ({len(st.session_state.lote_pendientes)} archivos)")
            if st.button("🚀 INICIAR ANÁLISIS DE LOTE COMPLETO"):
                barra_progreso, status_text = st.progress(0), st.empty()
                for i, doc in enumerate(st.session_state.lote_pendientes):
                    status_text.text(f"Analizando {doc['nombre']}...")
                    exito, intentos = False, 3
                    while intentos > 0 and not exito:
                        try:
                            prompt = "Analizá la imagen. Extraé JSON con: fecha, nro_factura, codigo_cliente (corto, no CUIT), razon_social, litros_factura, importe. Del VALE DE CARGA extraé: chofer (de los casilleros), entidad_pagadora, numero_orden_autorizacion, efectivo (ignorá líneas de diseño), orden_efectivo. Solo JSON puro."
                            res = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[prompt, Image.open(io.BytesIO(doc['data']))])
                            raw_text = res.text.strip().replace('```json', '').replace('```', '')
                            start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                            datos_extraidos = json.loads(raw_text[start:end])
                            datos_extraidos['_origen'] = doc['nombre']
                            st.session_state.cola_extracciones.append(datos_extraidos)
                            exito = True
                        except:
                            intentos -= 1
                            time.sleep(2)
                    if not exito: st.session_state.cola_extracciones.append({'_origen': f"⚠️ Error en {doc['nombre']}"})
                    barra_progreso.progress((i + 1) / len(st.session_state.lote_pendientes))
                st.session_state.lote_pendientes = [] 
                st.rerun() 
            if st.button("🗑️ Vaciar Pila"):
                st.session_state.lote_pendientes = []
                st.rerun()

    if st.session_state.resumen_ventas:
        st.divider()
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.subheader(f"📋 Planilla Final ({len(df)} registros)")
        st.dataframe(df[["Fecha", "Chofer", "Cliente", "Litros", "Importe", "Factura", "Entidad pagadora"]], use_container_width=True)
        
        col_ex1, col_ex2 = st.columns(2)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Ventas')
            ws = writer.sheets['Ventas']
            for i, col in enumerate(df.columns): ws.column_dimensions[get_column_letter(i + 1)].width = 20
        
        if col_ex1.download_button(label="📥 Descargar Excel y Reiniciar", data=buffer.getvalue(), file_name=f"Resumen_Camiones_{datetime.now().strftime('%d-%m-%Y')}.xlsx", use_container_width=True):
            st.session_state.resumen_ventas = []
            st.session_state.cola_extracciones = []
            st.session_state.lote_pendientes = []
            archivo_usuario = obtener_nombre_cache(st.session_state.usuario_actual)
            if os.path.exists(archivo_usuario): os.remove(archivo_usuario)
            st.rerun()

        if col_ex2.button("🗑️ Vaciar sin descargar", use_container_width=True):
            st.session_state.resumen_ventas = []
            if os.path.exists(obtener_nombre_cache(st.session_state.usuario_actual)): os.remove(obtener_nombre_cache(st.session_state.usuario_actual))
            st.rerun()

# ==========================================
# 4. MÓDULO FACTURAS DE PROVEEDORES
# ==========================================
elif opcion == "📄 Facturas de Proveedores":
    if len(st.session_state.cola_extracciones_prov) > 0:
        st.title(f"🔄 Revisión de Proveedores - {st.session_state.usuario_actual}")
        total_restantes = len(st.session_state.cola_extracciones_prov)
        st.warning(f"Tienes {total_restantes} factura(s) esperando tu revisión.")
        
        datos_actuales = st.session_state.cola_extracciones_prov[0]
        st.subheader(f"📝 Revisando: {datos_actuales.get('_origen', 'Documento desconocido')}")

        with st.form("validador_proveedores"):
            def limpiar_texto(v): return "" if str(v).strip().lower() in ["none", "null", ""] else str(v).strip()
            def to_f(v):
                try: 
                    v_str = str(v).strip().replace('.', '').replace(',', '.') if ',' in str(v) and '.' in str(v) else str(v).strip().replace(',', '.')
                    return float(v_str) if v_str else 0.0
                except: return 0.0

            v_fecha = limpiar_texto(datos_actuales.get('fecha', ''))
            v_cuit = limpiar_texto(datos_actuales.get('cuit_proveedor', ''))
            v_razon_social = limpiar_texto(datos_actuales.get('razon_social_proveedor', ''))
            v_nro_factura = limpiar_texto(datos_actuales.get('nro_factura', ''))
            v_concepto = limpiar_texto(datos_actuales.get('concepto', ''))
            
            c1, c2, c3 = st.columns([1, 1.5, 2])
            fecha = c1.text_input("Fecha", v_fecha)
            cuit = c2.text_input("CUIT Proveedor", v_cuit)
            razon_social = c3.text_input("Razón Social / Nombre", v_razon_social)
            
            c4, c5, c6, c7 = st.columns([1.5, 1, 1, 1])
            nro_factura = c4.text_input("Factura / Remito Nº", v_nro_factura)
            neto = c5.number_input("Importe Neto", value=to_f(datos_actuales.get('importe_neto', 0.0)))
            iva = c6.number_input("IVA", value=to_f(datos_actuales.get('importe_iva', 0.0)))
            total = c7.number_input("Total Factura", value=to_f(datos_actuales.get('importe_total', 0.0)))
            
            concepto = st.text_input("Concepto / Detalle", v_concepto)

            st.markdown("<br>", unsafe_allow_html=True)
            col_b1, col_b2 = st.columns(2)
            
            if col_b1.form_submit_button("✅ GUARDAR Y VER SIGUIENTE"):
                registro_prov = {
                    "Fecha": fecha.strip(), 
                    "Proveedor": razon_social.strip().upper(), 
                    "CUIT": cuit.strip(), 
                    "Factura": nro_factura.strip(), 
                    "Neto": neto, 
                    "IVA": iva, 
                    "Total": total, 
                    "Concepto": concepto.strip()
                }
                st.session_state.resumen_prov.append(registro_prov)
                st.session_state.cola_extracciones_prov.pop(0) 
                st.rerun()
            
            if col_b2.form_submit_button("🗑️ DESCARTAR"):
                st.session_state.cola_extracciones_prov.pop(0)
                st.rerun()

    else:
        st.title(f"📄 Carga de Proveedores - {st.session_state.usuario_actual}")
        tab1, tab2 = st.tabs(["📁 Subir Facturas", "📸 Cámara"])
        with tab1:
            fotos_disco = st.file_uploader("Seleccionar facturas o remitos", type=["pdf","jpg","png","jpeg"], accept_multiple_files=True, key="up_prov")
            if fotos_disco and st.button("➕ Sumar facturas a la Pila"):
                for f in fotos_disco: st.session_state.lote_pendientes_prov.append({'nombre': f.name, 'data': f.getvalue(), 'tipo': f.type})
                st.success(f"✅ Se sumaron {len(fotos_disco)} facturas.")

        with tab2:
            foto_camara = st.camera_input("Enfocar factura", key="cam_prov")
            if foto_camara and st.button("➕ Sumar captura a la Pila"):
                st.session_state.lote_pendientes_prov.append({'nombre': f"Factura_{len(st.session_state.lote_pendientes_prov)+1}.jpg", 'data': foto_camara.getvalue(), 'tipo': foto_camara.type})
                st.success("✅ ¡Factura Agregada!")
        
        st.divider()
        if st.session_state.lote_pendientes_prov:
            st.subheader(f"📦 Pila de Facturas ({len(st.session_state.lote_pendientes_prov)} documentos)")
            if st.button("🚀 INICIAR LECTURA DE PROVEEDORES"):
                barra_progreso, status_text = st.progress(0), st.empty()
                for i, doc in enumerate(st.session_state.lote_pendientes_prov):
                    status_text.text(f"Analizando {doc['nombre']}...")
                    exito, intentos = False, 3
                    error_interno = ""
                    while intentos > 0 and not exito:
                        try:
                            prompt_proveedores = """Eres un auditor contable automatizado. Tu única tarea es leer esta factura y devolver un JSON puro.
REGLAS VITALES PARA NO ROMPER EL SISTEMA:
1. NINGÚN valor debe contener comillas dobles (") ni simples ('). Si un artículo dice 5/16", pon solo 5/16.
2. Devuelve estrictamente el código JSON, sin texto de saludo ni formato markdown.

MAPA EXACTO DE LA FACTURA PARA LA IA:
- "razon_social_proveedor": Nombre del emisor principal arriba a la izquierda (Ej: BERGAMINI LUIS). ¡ATENCIÓN! El cliente receptor es BC COMBUSTIBLES S.A., NO lo confundas ni lo pongas como proveedor.
- "cuit_proveedor": Buscar "CUIT:" en la parte superior central (Ej: 20-22684885-2).
- "nro_factura": Buscar bajo la palabra FACTURA a la derecha (Ej: 0002-00018226).
- "fecha": Buscar la fecha de emisión arriba a la derecha (Ej: 30/03/2026).
- "importe_neto": Buscar "SUBTOTAL" en el pie de página, abajo a la izquierda (Ej: 1122,00).
- "importe_iva": Buscar el monto del IVA 21% en el pie de página (Ej: 235,62).
- "importe_total": Monto final total abajo a la derecha (Ej: 1357,62).
- "concepto": Detalle de los artículos centrales. Resume y QUITA toda comilla (Ej: UNION RECTA PLASTICA 5/16, TUERCA FIJACION).

Estructura requerida:
{
  "fecha": "",
  "cuit_proveedor": "",
  "razon_social_proveedor": "",
  "nro_factura": "",
  "importe_neto": "",
  "importe_iva": "",
  "importe_total": "",
  "concepto": ""
}"""
                            res = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[prompt_proveedores, Image.open(io.BytesIO(doc['data']))])
                            raw_text = res.text.strip().replace('```json', '').replace('```JSON', '').replace('```', '')
                            start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                            if start == -1:
                                raise ValueError("La IA no devolvió las llaves de formato de datos")
                            datos_extraidos = json.loads(raw_text[start:end], strict=False)
                            datos_extraidos['_origen'] = doc['nombre']
                            st.session_state.cola_extracciones_prov.append(datos_extraidos)
                            exito = True
                        except Exception as e:
                            error_interno = str(e)
                            intentos -= 1
                            time.sleep(2)
                    if not exito: st.session_state.cola_extracciones_prov.append({'_origen': f"⚠️ Error Técnico en {doc['nombre']} | Falla: {error_interno}"})
                    barra_progreso.progress((i + 1) / len(st.session_state.lote_pendientes_prov))
                st.session_state.lote_pendientes_prov = [] 
                st.rerun() 
            if st.button("🗑️ Vaciar Pila Proveedores"):
                st.session_state.lote_pendientes_prov = []
                st.rerun()

    if st.session_state.resumen_prov:
        st.divider()
        df_prov = pd.DataFrame(st.session_state.resumen_prov)
        st.subheader(f"📋 Planilla de Proveedores ({len(df_prov)} registros)")
        st.dataframe(df_prov, use_container_width=True)
        col_ex1, col_ex2 = st.columns(2)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_prov.to_excel(writer, index=False, sheet_name='Proveedores')
            ws = writer.sheets['Proveedores']
            for i, col in enumerate(df_prov.columns): ws.column_dimensions[get_column_letter(i + 1)].width = 20
        if col_ex1.download_button(label="📥 Descargar Excel de Proveedores", data=buffer.getvalue(), file_name=f"Proveedores_{datetime.now().strftime('%d-%m-%Y')}.xlsx", use_container_width=True):
            st.session_state.resumen_prov = []
            st.session_state.cola_extracciones_prov = []
            st.session_state.lote_pendientes_prov = []
            st.rerun()
        if col_ex2.button("🗑️ Vaciar sin descargar (Proveedores)", use_container_width=True):
            st.session_state.resumen_prov = []
            st.rerun()

# ==========================================
# 5. MÓDULO AUDITORÍA DE REMITOS
# ==========================================
elif opcion == "🔍 Auditoría de Remitos":
    st.title(f"📑 Auditoría de Cargas - {st.session_state.usuario_actual}")
    st.info(f"{st.session_state.usuario_actual}, acá podés auditar las fotos de los playeros y armar los resúmenes para los clientes.")

    try:
        query = supabase.table("ordenes_carga").select("*, clientes(nombre)").eq("estado", "DESPACHADO").not_.is_("url_foto", "null").order("fecha_despacho", desc=True).execute()
        ordenes = query.data
    except Exception as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        ordenes = []

    if not ordenes:
        st.warning("No hay remitos pendientes de auditoría con foto adjunta.")
    else:
        df_audit = pd.DataFrame(ordenes)
        df_audit['Cliente'] = df_audit['clientes'].apply(lambda x: x['nombre'] if x else "DESCONOCIDO")
        clientes_con_remitos = df_audit['Cliente'].unique()

        cliente_sel = st.selectbox("Seleccioná el cliente para auditar y armar resumen:", ["--- Seleccionar ---"] + list(clientes_con_remitos))
        
        if cliente_sel != "--- Seleccionar ---":
            filtro_cliente = df_audit[df_audit['Cliente'] == cliente_sel]
            
            # --- CABECERA Y BOTÓN DE ANÁLISIS EN LOTE ---
            c_head1, c_head2 = st.columns([2, 1])
            with c_head1:
                st.subheader(f"Órdenes de {cliente_sel}")
            with c_head2:
                if st.button("🚀 Leer todas las fotos con IA", use_container_width=True):
                    import requests
                    barra_progreso = st.progress(0)
                    texto_estado = st.empty()
                    total = len(filtro_cliente)
                    
                    for i, (_, fila) in enumerate(filtro_cliente.iterrows()):
                        texto_estado.text(f"Analizando orden #{fila['id']} ({i+1}/{total})...")
                        try:
                            # 1. Descargamos la foto de Supabase
                            respuesta_img = requests.get(fila['url_foto'])
                            img_remito = Image.open(io.BytesIO(respuesta_img.content))

                            # 2. Le pedimos a Gemini que extraiga los datos
                            prompt_auditoria = """Sos un auditor contable automatizado. Extraé de esta imagen:
                            1. "litros": El volumen de litros despachados (solo el número, quitá la 'L' o palabras).
                            2. "comprobante": El número de remito, vale o factura.
                            Devolvé SOLO un JSON puro, sin formato markdown: {"litros": 0, "comprobante": "..."}"""

                            res = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[prompt_auditoria, img_remito])
                            
                            # 3. Limpiamos y leemos la respuesta
                            raw_text = res.text.strip().replace('```json', '').replace('```JSON', '').replace('```', '')
                            start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                            datos_ia = json.loads(raw_text[start:end])

                            # 4. Guardamos lo que leyó la IA en la memoria temporal del sistema
                            st.session_state[f"ia_litros_{fila['id']}"] = float(datos_ia.get('litros', fila['litros_pedidos']))
                            st.session_state[f"ia_factura_{fila['id']}"] = str(datos_ia.get('comprobante', ''))
                        
                        except Exception as e:
                            # Si la IA falla al leer una foto borrosa, simplemente la salta y deja los datos vacíos
                            pass
                        
                        # Actualizamos la barra y pausamos un segundo para no saturar a Gemini
                        barra_progreso.progress((i + 1) / total)
                        time.sleep(1.5) 
                        
                    texto_estado.success("✅ ¡Análisis completo! Ya podés revisar los casilleros de abajo.")
                    time.sleep(2)
                    st.rerun() # Refresca la pantalla para mostrar los números nuevos

            st.divider()

            # --- LISTA DE ÓRDENES PARA CONFIRMAR ---
            for _, fila in filtro_cliente.iterrows():
                fecha_disp = fila['fecha_despacho'][:10] if fila['fecha_despacho'] else "Sin fecha"
                
                # Memoria por defecto: si la IA no corrió todavía, cargamos los litros pedidos originalmente
                if f"ia_litros_{fila['id']}" not in st.session_state:
                    st.session_state[f"ia_litros_{fila['id']}"] = float(fila['litros_pedidos'])
                if f"ia_factura_{fila['id']}" not in st.session_state:
                    st.session_state[f"ia_factura_{fila['id']}"] = ""

                with st.expander(f"📦 Orden #{fila['id']} | {fecha_disp} | Chofer: {fila['chofer']}"):
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.image(fila['url_foto'], caption=f"Foto del Remito - Orden #{fila['id']}", use_container_width=True)
                    with c2:
                        st.markdown(f"**Datos Cargados en Playa:**")
                        st.write(f"🔹 Patente: {fila['patente']}")
                        st.write(f"🔹 Litros Pedidos: {fila['litros_pedidos']} L")
                        if fila['efectivo_pedido'] > 0:
                            st.write(f"💵 Efectivo Entregado: ${fila['efectivo_pedido']}")
                        st.divider()

                        st.markdown("**Confirmación Administrativa:**")
                        with st.form(key=f"form_audit_{fila['id']}"):
                            # Acá los casilleros se autocompletan solos si la IA ya los analizó
                            lts_conf = st.number_input("Litros Reales (según foto)", value=st.session_state[f"ia_litros_{fila['id']}"])
                            nro_compro = st.text_input("Nº Remito / Factura Final", value=st.session_state[f"ia_factura_{fila['id']}"])
                            
                            if st.form_submit_button("✅ Añadir esta carga al lote"):
                                item_resumen = {
                                    "Fecha": fecha_disp,
                                    "Cliente": cliente_sel,
                                    "Patente": fila['patente'],
                                    "Chofer": fila['chofer'],
                                    "Litros Reales": lts_conf,
                                    "Comprobante": nro_compro.upper(),
                                    "ID Orden": fila['id']
                                }
                                st.session_state.resumen_para_cliente.append(item_resumen)
                                st.success(f"¡Orden #{fila['id']} añadida al lote de {cliente_sel}!")

    # --- DESCARGA DE EXCEL ---
    if st.session_state.resumen_para_cliente:
        st.divider()
        st.subheader("📊 Lote Auditado (Listo para Excel)")
        df_resumen = pd.DataFrame(st.session_state.resumen_para_cliente)
        st.dataframe(df_resumen, use_container_width=True)
        buffer_res = io.BytesIO()
        with pd.ExcelWriter(buffer_res, engine='openpyxl') as writer:
            df_resumen.to_excel(writer, index=False, sheet_name='Resumen_Cargas')
            ws = writer.sheets['Resumen_Cargas']
            for i, col in enumerate(df_resumen.columns): ws.column_dimensions[get_column_letter(i + 1)].width = 18
        ca1, ca2 = st.columns(2)
        ca1.download_button("📥 Descargar Excel para Cliente", data=buffer_res.getvalue(), file_name=f"Resumen_{datetime.now().strftime('%d-%m-%Y')}.xlsx", use_container_width=True)
        if ca2.button("🗑️ Vaciar Lote Auditado", use_container_width=True):
            st.session_state.resumen_para_cliente = []
            st.rerun()

# ==========================================
# 6. MANTENIMIENTO
# ==========================================
with st.sidebar.expander("🛠️ Mantenimiento"):
    if st.button("🗑️ Limpiar Memoria (Choferes/Clientes)"):
        for arch in [ARCHIVO_DB, ARCHIVO_CHOFERES]:
            if os.path.exists(arch): os.remove(arch)
        st.rerun()
