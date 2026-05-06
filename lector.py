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

            entidad_ia = limpiar_texto(datos_actuales.get('entidad_pagadora', '')).upper()
            entidad_final = entidad_ia
            if entidad_ia and ENTIDADES_OFICIALES:
                coincidencias_e = difflib.get_close_matches(entidad_ia, ENTIDADES_OFICIALES, n=1, cutoff=0.4)
                if coincidencias_e: entidad_final = coincidencias_e[0]

            if es_nuevo_cli: st.info("✨ ¡Atención! Código de cliente nuevo detectado.")
            if chofer_final and chofer_final not in BASE_CHOFERES:
                st.markdown(f"""<div class="bloque-alerta">⚠️ ATENCIÓN {st.session_state.usuario_actual.upper()}:<br>El chofer en pantalla no figura en la memoria. Revisá que esté bien escrito.</div>""", unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns([1.5, 2, 1, 3])
            fecha, chofer, codigo_final, cliente_rs = c1.text_input("Fecha", v_fecha), c2.text_input("Chofer", chofer_final), c3.text_input("Cód. Cli.", codigo_ia), c4.text_input("Cliente de Factura", nombre_sugerido)
            
            c5, c6, c7 = st.columns(3)
            litros, importe, factura_nro = c5.number_input("Litros", value=to_f(datos_actuales.get('litros_factura', 0.0)), format="%.4f"), c6.number_input("Importe", value=to_f(datos_actuales.get('importe', 0.0))), c7.text_input("Factura Nº", limpiar_texto(datos_actuales.get('nro_factura', '')))
            entidad = st.text_input("Entidad pagadora", entidad_final)
            
            with st.expander("Órdenes y Efectivo", expanded=True):
                ca1, ca2, ca3 = st.columns(3)
                o_litros, val_efectivo, o_efectivo = ca1.text_input("Orden Litros", v_o_litros), ca2.number_input("Efectivo", value=v_efectivo), ca3.text_input("Orden Efectivo", v_o_efectivo)

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
        st.subheader("📸 Paso 1: Recolectar Documentos")
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
        
        # 🟢 AUTO-RESET: Al hacer clic, se limpia todo automáticamente 🟢
        if col_ex1.download_button(label="📥 Descargar Excel y Reiniciar", data=buffer.getvalue(), file_name=f"Resumen_{datetime.now().strftime('%d-%m-%Y')}.xlsx", use_container_width=True):
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

with st.sidebar.expander("🛠️ Mantenimiento"):
    if st.button("🗑️ Limpiar Memoria (Choferes/Clientes)"):
        for arch in [ARCHIVO_DB, ARCHIVO_CHOFERES]:
            if os.path.exists(arch): os.remove(arch)
        st.rerun()
