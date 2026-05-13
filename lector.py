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
import requests 

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

def convertir_a_numero(valor):
    """Convierte cadenas numéricas a enteros para evitar el triángulo verde en Excel"""
    v = str(valor).strip()
    if v.isdigit():
        return int(v)
    return v

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
if 'agregados_excel' not in st.session_state: st.session_state.agregados_excel = []

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
                            prompt_ventas = """Analizá este comprobante (Factura o Vale). 
REGLA DE ORO: 'BC COMBUSTIBLES' es el emisor arriba de todo. IGNORALO.
Tus objetivos son:
1. Extraer 'razon_social' del cliente que recibe la carga (está debajo del logo, cerca del CUIT del cliente).
2. Extraer 'litros_factura' e 'importe' total.
3. Extraer 'chofer' si hay un vale manuscrito al lado.
Extraé JSON puro sin markdown."""
                            res = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[prompt_ventas, Image.open(io.BytesIO(doc['data']))])
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
                            prompt_prov = """Eres un auditor contable. Tu objetivo es leer una FACTURA DE COMPRA.
BC COMBUSTIBLES es el RECEPTOR (está abajo). NO lo pongas como proveedor.
El 'razon_social_proveedor' es el emisor arriba a la izquierda.
Busca CUIT, Fecha, Nº de Factura y Totales. Extraé JSON puro."""
                            res = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[prompt_prov, Image.open(io.BytesIO(doc['data']))])
                            raw_text = res.text.strip().replace('```json', '').replace('```', '')
                            start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                            datos_extraidos = json.loads(raw_text[start:end])
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
    st.info(f"Revisión de movimientos para generar resúmenes externos.")

    try:
        query = supabase.table("ordenes_carga").select("*, clientes(nombre, formato_especial)").eq("estado", "DESPACHADO").order("fecha_despacho", desc=True).execute()
        ordenes = query.data
    except Exception as e:
        st.error(f"Error de base de datos: {e}")
        ordenes = []

    if not ordenes:
        st.warning("No hay remitos pendientes de auditoría.")
    else:
        df_audit = pd.DataFrame(ordenes)
        df_audit['Cliente'] = df_audit['clientes'].apply(lambda x: x['nombre'] if x else "DESCONOCIDO")
        df_audit['formato_especial'] = df_audit['clientes'].apply(lambda x: x.get('formato_especial', False) if x else False)
        
        df_audit = df_audit[(df_audit['url_foto'].notnull()) | (df_audit['motivo_sin_foto'].notnull())]

        clientes_con_movimientos = df_audit['Cliente'].unique()
        cliente_sel = st.selectbox("Seleccioná el cliente para armar su resumen:", ["--- Seleccionar ---"] + list(clientes_con_movimientos))
        
        if cliente_sel != "--- Seleccionar ---":
            filtro_cliente = df_audit[df_audit['Cliente'] == cliente_sel]
            
            c_head1, c_head2 = st.columns([2, 1])
            with c_head1:
                st.subheader(f"Movimientos de {cliente_sel}")
            with c_head2:
                clave_estado_ia = f"ia_procesada_{cliente_sel}"
                ya_procesado = st.session_state.get(clave_estado_ia, False)
                
                if ya_procesado:
                    st.button("✅ Fotos procesadas por IA", disabled=True, use_container_width=True)
                else:
                    if st.button("🚀 Procesar fotos con IA", use_container_width=True):
                        barra_p = st.progress(0)
                        ordenes_con_foto = filtro_cliente[filtro_cliente['url_foto'].notnull()]
                        total = len(ordenes_con_foto)
                        if total > 0:
                            for i, (_, fila) in enumerate(ordenes_con_foto.iterrows()):
                                try:
                                    res_img = requests.get(fila['url_foto'])
                                    img_rem = Image.open(io.BytesIO(res_img.content))
                                    prompt_auditoria = """Eres un experto en auditoría fiscal argentina. 
Analizá este documento. REGLA DE ORO: 'BC COMBUSTIBLES S.A.' es el EMISOR. NO lo pongas como razon_social. 
Buscá al CLIENTE (Receptor) debajo del encabezado principal. Extraé el nombre legal completo.
Extraé: fecha, razon_social, litros, importe, comprobante.
Devolvé estrictamente JSON puro."""
                                    res_ia = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[prompt_auditoria, img_rem])
                                    raw_t = res_ia.text.strip().replace('```json', '').replace('```', '')
                                    d_ia = json.loads(raw_t[raw_t.find('{'):raw_t.rfind('}')+1])
                                    
                                    st.session_state[f"ia_fec_{fila['id']}"] = str(d_ia.get('fecha', ''))
                                    st.session_state[f"ia_rs_{fila['id']}"] = str(d_ia.get('razon_social', ''))
                                    st.session_state[f"ia_lts_{fila['id']}"] = float(d_ia.get('litros', 0.0))
                                    st.session_state[f"ia_imp_{fila['id']}"] = float(d_ia.get('importe', 0.0))
                                    st.session_state[f"ia_fac_{fila['id']}"] = str(d_ia.get('comprobante', ''))
                                except: pass
                                barra_p.progress((i + 1) / total)
                            st.session_state[clave_estado_ia] = True
                            st.success("✅ Análisis completo.")
                            time.sleep(1)
                            st.rerun()

            st.divider()

            for _, fila in filtro_cliente.iterrows():
                fecha_disp = fila['fecha_despacho'][:10] if pd.notna(fila['fecha_despacho']) else "---"
                chofer_txt = fila['chofer'] if pd.notna(fila['chofer']) else "Sin chofer"
                es_especial = fila['formato_especial']
                estado_icono = "✅ [LISTO]" if fila['id'] in st.session_state.agregados_excel else "📦 [PENDIENTE]"
                
                with st.expander(f"{estado_icono} Orden #{fila['id']} | Cliente: {cliente_sel} | Chofer: {chofer_txt} | Patente: {fila['patente']}"):
                    c1, c2 = st.columns([1.8, 1]) 
                    with c1:
                        if pd.notna(fila['url_foto']) and str(fila['url_foto']).strip() != "":
                            st.markdown(f"**[🔍 Clic aquí para abrir la foto en tamaño completo (Zoom real)]({fila['url_foto']})**")
                            st.image(fila['url_foto'], caption="Remito / Factura original", use_container_width=True)
                        else:
                            motivo = fila['motivo_sin_foto'] if pd.notna(fila['motivo_sin_foto']) else 'Sin motivo'
                            st.warning(f"⚠️ SIN FOTO: {motivo}")
                            
                    with c2:
                        if fila['id'] in st.session_state.agregados_excel:
                            st.success("✅ Esta orden ya fue validada.")
                        else:
                            with st.form(key=f"form_aud_{fila['id']}"):
                                st.write("📋 **Datos Extraídos (Factura/Remito)**")
                                col_f1, col_f2 = st.columns(2)
                                fac_fecha = col_f1.text_input("Fecha", value=st.session_state.get(f"ia_fec_{fila['id']}", ""))
                                fac_rs = col_f2.text_input("Razón Social", value=st.session_state.get(f"ia_rs_{fila['id']}", ""))
                                
                                col_f3, col_f4 = st.columns(2)
                                fac_imp = col_f3.number_input("Importe ($)", value=st.session_state.get(f"ia_imp_{fila['id']}", 0.0))
                                fac_comp = col_f4.text_input("Nº Factura", value=st.session_state.get(f"ia_fac_{fila['id']}", ""))
                                
                                st.write("📝 **Cantidades y Órdenes**")
                                efectivo_real_bd = fila.get('efectivo_entregado') if pd.notna(fila.get('efectivo_entregado')) else fila.get('efectivo_pedido', 0)
                                tiene_foto = pd.notna(fila['url_foto']) and str(fila['url_foto']).strip() != ""
                                litros_por_defecto = float(fila['litros_pedidos']) if tiene_foto else None
                                
                                nro_ord_gen, nro_ord_lts, nro_ord_efe = "", "", ""
                                
                                if es_especial:
                                    col_o1, col_o2 = st.columns(2)
                                    fac_lts = col_o1.number_input("Litros", value=st.session_state.get(f"ia_lts_{fila['id']}", litros_por_defecto))
                                    nro_ord_lts = col_o2.text_input("Nº Orden Litros", value=fila['nro_orden_litros_interna'] if pd.notna(fila['nro_orden_litros_interna']) else "")
                                    col_o3, col_o4 = st.columns(2)
                                    efectivo_final = col_o3.number_input("Efectivo Entregado ($)", value=float(efectivo_real_bd))
                                    nro_ord_efe = col_o4.text_input("Nº Orden Efectivo", value=fila['nro_orden_efectivo_interna'] if pd.notna(fila['nro_orden_efectivo_interna']) else "")
                                else:
                                    col_o1, col_o2 = st.columns(2)
                                    fac_lts = col_o1.number_input("Litros", value=st.session_state.get(f"ia_lts_{fila['id']}", litros_por_defecto))
                                    nro_ord_gen = col_o2.text_input("Nº Orden (Normal)", value=fila['nro_orden_cliente'] if pd.notna(fila['nro_orden_cliente']) else "")
                                    efectivo_final = st.number_input("Efectivo Entregado ($)", value=float(efectivo_real_bd))
                                
                                if st.form_submit_button("✅ Añadir al Excel Final"):
                                    st.session_state.agregados_excel.append(fila['id'])
                                    
                                    # FUSIÓN DE COLUMNAS APLICADA AQUÍ: 1 SOLA COLUMNA PARA EL NÚMERO DE ORDEN
                                    st.session_state.resumen_para_cliente.append({
                                        "Fecha": fac_fecha.strip(),
                                        "Chofer": chofer_txt.strip(),
                                        "Razón Social": fac_rs.strip(),
                                        "Litros": fac_lts,
                                        "Nº Orden": convertir_a_numero(nro_ord_lts) if es_especial else convertir_a_numero(nro_ord_gen),
                                        "Importe": fac_imp,
                                        "Nº Factura": fac_comp.strip(),
                                        "Entidad Pagadora": cliente_sel,
                                        "Efectivo": efectivo_final,
                                        "Nº Orden Efectivo": convertir_a_numero(nro_ord_efe) if es_especial else "-"
                                    })
                                    st.toast("Carga añadida.")
                                    st.rerun() 

    if st.session_state.resumen_para_cliente:
        st.divider()
        df_res = pd.DataFrame(st.session_state.resumen_para_cliente)
        
        # --- SUMATORIA DE TOTALES PARA EL EXCEL ---
        df_res['Litros'] = pd.to_numeric(df_res['Litros'], errors='coerce').fillna(0)
        df_res['Importe'] = pd.to_numeric(df_res['Importe'], errors='coerce').fillna(0)
        df_res['Efectivo'] = pd.to_numeric(df_res['Efectivo'], errors='coerce').fillna(0)
        
        total_row = {col: "" for col in df_res.columns}
        total_row["Razón Social"] = "TOTALES:"
        total_row["Litros"] = df_res['Litros'].sum()
        total_row["Importe"] = df_res['Importe'].sum()
        total_row["Efectivo"] = df_res['Efectivo'].sum()
        
        df_export = pd.concat([df_res, pd.DataFrame([total_row])], ignore_index=True)

        st.subheader("📊 Vista Previa del Excel")
        st.dataframe(df_export, use_container_width=True)
        
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as wr:
            df_export.to_excel(wr, index=False, sheet_name='Resumen_BC')
            ws = wr.sheets['Resumen_BC']
            
            fill_header = PatternFill(start_color="C8102E", end_color="C8102E", fill_type="solid")
            font_header = Font(color="FFFFFF", bold=True)
            font_total = Font(bold=True)
            fill_total = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            borde = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

            for col_num, col_name in enumerate(df_export.columns, 1):
                cell = ws.cell(row=1, column=col_num)
                cell.fill = fill_header
                cell.font = font_header
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = borde
                ws.column_dimensions[get_column_letter(col_num)].width = 18

            max_row = ws.max_row
            for row in ws.iter_rows(min_row=2, max_row=max_row, min_col=1, max_col=ws.max_column):
                is_total_row = (row[0].row == max_row)
                for cell in row:
                    cell.border = borde
                    cell.alignment = Alignment(vertical="center")
                    
                    if is_total_row:
                        cell.font = font_total
                        cell.fill = fill_total
                        
                    header = ws.cell(row=1, column=cell.column).value
                    if header in ["Importe", "Efectivo"]: cell.number_format = '"$"#,##0.00'
                    elif header == "Litros": cell.number_format = '#,##0.00'

        c_ex1, c_ex2 = st.columns(2)
        c_ex1.download_button("📥 Descargar Excel", data=buf.getvalue(), file_name=f"Resumen_{cliente_sel}.xlsx", use_container_width=True)
        
        if c_ex2.button("🗑️ Vaciar Lote (Sin Auditar)", use_container_width=True):
            st.session_state.resumen_para_cliente = []
            st.session_state.agregados_excel = []
            st.session_state.pop(f"ia_procesada_{cliente_sel}", None) 
            st.rerun()
            
        st.markdown("### 🔒 Cierre Definitivo")
        confirmar_cierre = st.checkbox("Confirmo que ya descargué el Excel.")
        if st.button("✅ Marcar Auditadas y Cerrar Lote", disabled=not confirmar_cierre, use_container_width=True):
            if st.session_state.agregados_excel:
                for ord_id in st.session_state.agregados_excel: supabase.table("ordenes_carga").update({"estado": "AUDITADO"}).eq("id", ord_id).execute()
            st.session_state.resumen_para_cliente = []
            st.session_state.agregados_excel = []
            st.session_state.pop(f"ia_procesada_{cliente_sel}", None) 
            st.success("¡Lote cerrado!")
            time.sleep(1.5)
            st.rerun()

# ==========================================
# 6. MANTENIMIENTO
# ==========================================
with st.sidebar.expander("🛠️ Mantenimiento"):
    if st.button("🗑️ Limpiar Memoria"):
        for arch in [ARCHIVO_DB, ARCHIVO_CHOFERES]:
            if os.path.exists(arch): os.remove(arch)
        st.rerun()
