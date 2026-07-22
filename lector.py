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
import textwrap 
import re 
import random
import gc # IMPORTANTE: Recolector de basura para limpiar la memoria RAM
from datetime import datetime
from supabase import create_client, Client
import requests 

# Importamos la nueva botonera PRO
try:
    from streamlit_option_menu import option_menu
except ImportError:
    st.error("⚠️ Falta instalar el menú moderno. Agregá `streamlit-option-menu` a tu archivo requirements.txt en GitHub.")
    st.stop()

# Herramientas de diseño para el Excel
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ==========================================
# 1. IDENTIDAD, CONEXIÓN Y SEGURIDAD
# ==========================================
COLOR_ROJO = "#C8102E"
COLOR_AMARILLO_ALERTA = "#FFE082" 
COLOR_GRIS_BC = "#3A3A3A" 

# Llamamos a las llaves desde la bóveda secreta de Streamlit
URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL_SB, KEY_SB)

NOMBRES_SUCURSALES = {1: "RECONQUISTA", 2: "AVELLANEDA", 3: "FLORENCIA", 4: "RECREO"}

st.set_page_config(page_title="BC Combustibles - Gestión Pro", page_icon="⛽", layout="wide", initial_sidebar_state="collapsed")

st.markdown(f"""
    <style>
        [data-testid="stSidebarNav"] {{display: none !important;}}
        .stApp {{ background-color: #f4f6f9 !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; font-weight: 700; }}
        
        .stButton>button {{ 
            background-color: {COLOR_ROJO}; color: white; border-radius: 8px; 
            font-weight: 600; height: 2.8em; border: none; width: 100%; transition: all 0.3s;
        }}
        .stButton>button:hover {{ background-color: #900b20; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
        
        [data-testid="stHeader"] {{ background-color: {COLOR_GRIS_BC} !important; }}
        [data-testid="stSidebar"] {{ background-color: {COLOR_GRIS_BC} !important; border-right: none; }}
        
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div {{ color: #ffffff !important; }}
        
        div[data-testid="stMetricValue"] {{ color: {COLOR_ROJO} !important; }}
        
        .tarjeta-pro {{
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; margin-bottom: 20px;
        }}
    </style>
""", unsafe_allow_html=True)

cliente_ia = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

URL_LOGO_OFICIAL = "https://bjhykcdhafoqpfkpngvw.supabase.co/storage/v1/object/public/remitos/Logo%20nuevo.png"

# ==========================================
# 2. SISTEMA DE LOGIN Y AUTENTICACIÓN
# ==========================================
if 'usuario_autenticado' not in st.session_state:
    st.session_state.usuario_autenticado = None

def mostrar_login():
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown(f"""
            <div class="tarjeta-pro" style="text-align:center;">
                <img src="{URL_LOGO_OFICIAL}" width="140" style="border-radius:10px; margin-bottom: 20px;">
                <h2 style='text-align:center; margin-bottom: 30px;'>Acceso Seguro</h2>
            </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            legajo = st.text_input("Número de Legajo", placeholder="Ej: 105")
            pin = st.text_input("PIN de Acceso", type="password", placeholder="Tu clave")
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("INGRESAR AL SISTEMA"):
                try:
                    res = supabase.table("empleados").select("*").eq("legajo", legajo).eq("pin", pin).execute()
                    if res.data:
                        st.session_state.usuario_autenticado = res.data[0]
                        st.rerun()
                    else:
                        st.error("❌ Credenciales incorrectas.")
                except Exception as e:
                    st.error(f"Error de conexión: {e}")

if st.session_state.usuario_autenticado is None:
    mostrar_login()
    st.stop()

# --- USUARIO LOGUEADO ---
user = st.session_state.usuario_autenticado
usuario_app = user['nombre']

# 1. ELIMINAR EL "FANTASMA" DE LA BARRA LATERAL POR COMPLETO
st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# 2. CABECERA SUPERIOR ALINEADA AL CENTRO
# Usamos vertical_alignment="center" para que el botón Salir quede perfectamente a la misma altura que tu perfil
col_logo, col_esp, col_perfil, col_salir = st.columns([1, 4, 2.5, 1], vertical_alignment="center")

with col_logo:
    st.image(URL_LOGO_OFICIAL, width=120)

with col_perfil:
    # Textos forzados a blanco (#FFFFFF) para que resalten sobre el gris
    st.markdown(f"""
        <div style="background:#3A3A3A; padding:8px 15px; border-radius:8px; border-left:4px solid {COLOR_ROJO};">
            <p style="margin:0; font-size:13px; color:#FFFFFF !important;">Operador: <b>{usuario_app}</b></p>
            <p style="margin:0; font-size:13px; color:#FFFFFF !important;">📍 {NOMBRES_SUCURSALES.get(user['sucursal_id'], 'BC')}</p>
        </div>
    """, unsafe_allow_html=True)

with col_salir:
    # Botón más chico, centrado y con texto en negrita
    if st.button("**🚪 Salir**"):
        st.session_state.usuario_autenticado = None
        st.rerun()

# 3. MENÚ HORIZONTAL AJUSTADO
opcion = option_menu(
    menu_title=None, 
    options=["Generador de Resumen", "Facturas de Proveedores", "Verificación BCRA", "Gestión de Clientes", "Laboratorio IA"], 
    icons=["file-earmark-spreadsheet", "receipt", "shield-check", "people", "robot"], 
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": COLOR_GRIS_BC, "border-radius": "8px", "margin-top": "10px"},
        "icon": {"color": "#FFFFFF", "font-size": "13px"}, 
        # Achicamos la fuente a 12px
        "nav-link": {"color": "#FFFFFF", "font-size": "12px", "text-align": "center", "margin":"0px", "--hover-color": "#4A4A4A"},
        # IMPORTANTISIMO: Anulamos la negrita al seleccionar (font-weight: normal) para que no salte de renglón
        "nav-link-selected": {"background-color": COLOR_ROJO, "color": "white", "font-weight": "normal"}, 
    }
)
st.markdown("<br>", unsafe_allow_html=True)

if 'lote_pendientes_prov' not in st.session_state: st.session_state.lote_pendientes_prov = []
if 'cola_extracciones_prov' not in st.session_state: st.session_state.cola_extracciones_prov = []
if 'resumen_prov' not in st.session_state: st.session_state.resumen_prov = []
if 'resumen_para_cliente' not in st.session_state: st.session_state.resumen_para_cliente = []
if 'agregados_excel' not in st.session_state: st.session_state.agregados_excel = []

def convertir_a_numero(valor):
    v = str(valor).strip()
    if v.isdigit(): return int(v)
    return v

# ==========================================
# 3. MÓDULO: FACTURAS DE PROVEEDORES
# ==========================================
if opcion == "Facturas de Proveedores":
    st.title(f"🏢 Gestión de Proveedores")
    st.markdown('<p style="color:#666; font-size:16px;">Módulo de carga y digitalización de comprobantes de compras.</p>', unsafe_allow_html=True)
    
    if len(st.session_state.cola_extracciones_prov) > 0:
        total_restantes = len(st.session_state.cola_extracciones_prov)
        st.warning(f"Tienes {total_restantes} factura(s) esperando tu revisión.")
        
        datos_actuales = st.session_state.cola_extracciones_prov[0]
        st.markdown(f'<div class="tarjeta-pro"><h4>📝 Revisando: {datos_actuales.get("_origen", "Documento desconocido")}</h4></div>', unsafe_allow_html=True)

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
                registro_prov = {"Fecha": fecha.strip(), "Proveedor": razon_social.strip().upper(), "CUIT": cuit.strip(), "Factura": nro_factura.strip(), "Neto": neto, "IVA": iva, "Total": total, "Concepto": concepto.strip()}
                st.session_state.resumen_prov.append(registro_prov)
                st.session_state.cola_extracciones_prov.pop(0) 
                st.rerun()
            if col_b2.form_submit_button("🗑️ DESCARTAR"):
                st.session_state.cola_extracciones_prov.pop(0)
                st.rerun()

    else:
        tab1, tab2 = st.tabs(["📁 Subir Facturas", "📸 Cámara"])
        with tab1:
            st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
            fotos_disco = st.file_uploader("Seleccionar facturas o remitos", type=["pdf","jpg","png","jpeg"], accept_multiple_files=True, key="up_prov")
            if fotos_disco and st.button("➕ Sumar facturas a la Pila"):
                for f in fotos_disco: st.session_state.lote_pendientes_prov.append({'nombre': f.name, 'data': f.getvalue(), 'tipo': f.type})
                st.success(f"✅ Se sumaron {len(fotos_disco)} facturas.")
            st.markdown('</div>', unsafe_allow_html=True)

        with tab2:
            st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
            foto_camara = st.camera_input("Enfocar factura", key="cam_prov")
            if foto_camara and st.button("➕ Sumar captura a la Pila"):
                st.session_state.lote_pendientes_prov.append({'nombre': f"Factura_{len(st.session_state.lote_pendientes_prov)+1}.jpg", 'data': foto_camara.getvalue(), 'tipo': foto_camara.type})
                st.success("✅ ¡Factura Agregada!")
            st.markdown('</div>', unsafe_allow_html=True)
        
        if st.session_state.lote_pendientes_prov:
            st.subheader(f"📦 Pila de Facturas ({len(st.session_state.lote_pendientes_prov)} documentos)")
            if st.button("🚀 INICIAR LECTURA DE PROVEEDORES"):
                barra_progreso, status_text = st.progress(0), st.empty()
                for i, doc in enumerate(st.session_state.lote_pendientes_prov):
                    status_text.text(f"Analizando {doc['nombre']}...")
                    exito, intentos, error_interno = False, 3, ""
                    while intentos > 0 and not exito:
                        try:
                            prompt_prov = """Eres auditor contable. Objetivo: leer FACTURA DE COMPRA. BC COMBUSTIBLES es RECEPTOR. Buscá CUIT, Fecha, Nº de Factura y Totales. Extraé JSON puro."""
                            modelo_actual = 'gemini-2.5-pro' if intentos > 1 else 'gemini-2.5-flash'
                            
                            img_rem = Image.open(io.BytesIO(doc['data']))
                            res = cliente_ia.models.generate_content(model=modelo_actual, contents=[prompt_prov, img_rem])
                            raw_text = res.text.strip().replace('```json', '').replace('```', '')
                            start, end = raw_text.find('{'), raw_text.rfind('}') + 1
                            datos_extraidos = json.loads(raw_text[start:end])
                            datos_extraidos['_origen'] = doc['nombre']
                            st.session_state.cola_extracciones_prov.append(datos_extraidos)
                            
                            try: img_rem.close()
                            except: pass
                            gc.collect()
                            
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
            st.session_state.resumen_prov, st.session_state.cola_extracciones_prov, st.session_state.lote_pendientes_prov = [], [], []
            st.rerun()
        if col_ex2.button("🗑️ Vaciar sin descargar (Proveedores)", use_container_width=True):
            st.session_state.resumen_prov = []
            st.rerun()

# ==========================================
# 4. MÓDULO: GENERADOR DE RESUMEN A CLIENTES
# ==========================================
elif opcion == "Generador de Resumen":
    st.title(f"📑 Generador de Resúmenes")
    
    if user['puesto'] == 'SUPER_ADMIN':
        st.markdown(f'<div class="tarjeta-pro" style="border-left: 5px solid #28a745; padding:15px;">🔓 <strong>Acceso SUPER ADMIN:</strong> Visualizando órdenes de TODAS las sucursales.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="tarjeta-pro" style="border-left: 5px solid {COLOR_ROJO}; padding:15px;">📍 <strong>Acceso Zonal:</strong> Visualizando solo órdenes de la sucursal <strong>{NOMBRES_SUCURSALES.get(user["sucursal_id"])}</strong>.</div>', unsafe_allow_html=True)

    PROMPT_AUDITORIA = textwrap.dedent("""
    Sos un auditor experto. El Emisor es 'BC COMBUSTIBLES'. Buscá al CLIENTE Receptor y los datos de la carga. 
    Devolvé ÚNICAMENTE un JSON puro, sin texto adicional ni formato markdown (sin ```json), con estas claves exactas:
    - "fecha": Fecha del comprobante.
    - "razon_social": Cliente receptor.
    - "importe": Monto total en números.
    - "comprobante": Número de comprobante.
    - "litros": Sumá la cantidad TOTAL de litros de combustible. NO sumes aceites o aditivos, solo combustibles.
    - "detalle_productos": Hacé un resumen de los combustibles y sus litros exactos. Ejemplo: 'Euro Diesel G3: 201 L | Gas Oil 500 G2: 81.5 L'. Si es un solo producto, poné solo ese.
    - "observaciones_ia": Evaluá TODOS los ítems facturados y aplicá ESTA REGLA ESTRICTA:
      1. Si SOLO cargó 'Gas Oil 500 G2' (Gasoil normal), devolvé "". (Vacío).
      2. Si detectás 2 o más combustibles diferentes, devolvé "Atención. La factura tiene varios productos."
      3. Si cargó SOLO Euro, devolvé "Atención. El producto cargado es Euro, verifique."
      4. Si SOLO cargó Nafta, devolvé "Atención. La factura contiene Nafta."
      5. Si encontrás artículos extra (aceites, filtros, etc.), devolvé "Atención. La factura contiene artículos extra: [detallar los extra]."
    """).strip()

    try:
        query = supabase.table("ordenes_carga").select("*, clientes!inner(nombre, formato_especial, sucursal_madre_id)")
        if user['puesto'] != 'SUPER_ADMIN':
            query = query.eq("clientes.sucursal_madre_id", user['sucursal_id'])
            
        res_auditoria = query.eq("estado", "DESPACHADO").order("fecha_despacho", desc=True).execute()
        ordenes = res_auditoria.data
    except Exception as e:
        st.error(f"Error de base de datos: {e}")
        ordenes = []

    if not ordenes:
        st.info("👍 Todo al día. No hay remitos pendientes para tu sucursal.")
    else:
        df_audit = pd.DataFrame(ordenes)
        df_audit['Cliente'] = df_audit['clientes'].apply(lambda x: x['nombre'] if x else "DESCONOCIDO")
        df_audit['formato_especial'] = df_audit['clientes'].apply(lambda x: x.get('formato_especial', False) if x else False)
        df_audit = df_audit[(df_audit['url_foto'].notnull()) | (df_audit['motivo_sin_foto'].notnull())]

        col_k1, col_k2, col_k3 = st.columns(3)
        col_k1.metric("Clientes con pendientes", len(df_audit['Cliente'].unique()))
        col_k2.metric("Remitos a procesar", len(df_audit))
        col_k3.metric("Litros Peticionados", f"{df_audit['litros_pedidos'].sum():,.0f} L")
        st.markdown("<hr>", unsafe_allow_html=True)

        clientes_con_movimientos = df_audit['Cliente'].unique()
        
        st.markdown("### Seleccionar Cuenta Corriente")
        cliente_sel = st.selectbox("", ["--- Seleccionar ---"] + list(clientes_con_movimientos), label_visibility="collapsed")
        
        if cliente_sel != "--- Seleccionar ---":
            filtro_cliente = df_audit[df_audit['Cliente'] == cliente_sel]
            
            c_head1, c_head2 = st.columns([2, 1])
            with c_head1:
                st.subheader(f"Operaciones de {cliente_sel}")
            with c_head2:
                clave_estado_ia = f"ia_procesada_{cliente_sel}"
                if st.session_state.get(clave_estado_ia, False):
                    st.button("✅ IA Procesada", disabled=True, use_container_width=True)
                else:
                    if st.button("🚀 Leer Datos con IA", use_container_width=True):
                        barra_p = st.progress(0)
                        ordenes_con_foto = filtro_cliente[filtro_cliente['url_foto'].notnull()]
                        total = len(ordenes_con_foto)
                        
                        if total > 0:
                            for i, (_, fila) in enumerate(ordenes_con_foto.iterrows()):
                                exito_extraccion = False
                                intentos_restantes = 3
                                tiempo_espera = 4  
                                
                                while intentos_restantes > 0 and not exito_extraccion:
                                    try:
                                        res_img = requests.get(fila['url_foto'])
                                        img_rem = Image.open(io.BytesIO(res_img.content))
                                        
                                        modelo_actual = 'gemini-2.5-pro' if intentos_restantes > 1 else 'gemini-2.5-flash'
                                        
                                        res_ia = cliente_ia.models.generate_content(model=modelo_actual, contents=[PROMPT_AUDITORIA, img_rem])
                                        raw_t = res_ia.text.strip().replace('```json', '').replace('```', '')
                                        
                                        start = raw_t.find('{')
                                        end = raw_t.rfind('}') + 1
                                        
                                        if start != -1 and end != 0:
                                            d_ia = json.loads(raw_t[start:end])
                                            
                                            def limpiar_num(v):
                                                try:
                                                    txt = str(v).replace('$', '').replace(' ', '').strip()
                                                    if ',' in txt and '.' in txt: txt = txt.replace('.', '').replace(',', '.')
                                                    elif ',' in txt: txt = txt.replace(',', '.')
                                                    return float(txt) if txt else 0.0
                                                except:
                                                    return 0.0
                                            
                                            st.session_state[f"ia_fec_{fila['id']}"] = str(d_ia.get('fecha', ''))
                                            st.session_state[f"ia_rs_{fila['id']}"] = str(d_ia.get('razon_social', ''))
                                            st.session_state[f"ia_lts_{fila['id']}"] = limpiar_num(d_ia.get('litros', 0.0))
                                            st.session_state[f"ia_imp_{fila['id']}"] = limpiar_num(d_ia.get('importe', 0.0))
                                            st.session_state[f"ia_fac_{fila['id']}"] = str(d_ia.get('comprobante', ''))
                                            st.session_state[f"ia_prod_{fila['id']}"] = str(d_ia.get('detalle_productos', ''))
                                            st.session_state[f"ia_obs_{fila['id']}"] = str(d_ia.get('observaciones_ia', ''))
                                        else:
                                            st.warning(f"La IA no devolvió un formato JSON válido para la orden #{fila['id']}")
                                            
                                        try: img_rem.close()
                                        except: pass
                                        del res_img     
                                        gc.collect()    
                                        
                                        exito_extraccion = True 
                                        
                                    except Exception as e:
                                        error_msg = str(e)
                                        if "503" in error_msg or "429" in error_msg or "UNAVAILABLE" in error_msg:
                                            intentos_restantes -= 1
                                            
                                            if intentos_restantes > 1:
                                                st.warning(f"⏳ Google saturado. Reintentando orden #{fila['id']} en {tiempo_espera} seg...")
                                                time.sleep(tiempo_espera)
                                                tiempo_espera *= 2 
                                            elif intentos_restantes == 1:
                                                st.warning(f"⚠️ Cambiando a modelo de respaldo para la orden #{fila['id']}...")
                                                time.sleep(2) 
                                            else:
                                                st.error(f"❌ Falló la orden #{fila['id']}. Intentá más tarde.")
                                        else:
                                            st.error(f"❌ Falla técnica inesperada en orden #{fila['id']}: {error_msg}")
                                            break 
                                
                                barra_p.progress((i + 1) / total)
                                time.sleep(3)
                                
                        st.session_state[clave_estado_ia] = True
                        st.success("✅ Extracción completa.")
                        time.sleep(2)
                        st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)

            for _, fila in filtro_cliente.iterrows():
                chofer_txt = fila['chofer'] if pd.notna(fila['chofer']) else "Sin chofer"
                es_especial = fila['formato_especial']
                estado_icono = "🟢 LISTO" if fila['id'] in st.session_state.agregados_excel else "🟠 PENDIENTE"
                
                patente_txt = fila['patente'] if pd.notna(fila['patente']) and str(fila['patente']).strip() != "" else "Sin Patente"
                with st.expander(f"{estado_icono} | Camión: {patente_txt} | Chofer: {chofer_txt}"):
                    c1, c2 = st.columns([1.5, 1]) 
                    with c1:
                        if pd.notna(fila['url_foto']) and str(fila['url_foto']).strip() != "":
                            st.image(fila['url_foto'], use_container_width=True)
                        else:
                            st.warning(f"⚠️ SIN FOTO: {fila.get('motivo_sin_foto', 'No se indicó motivo')}")
                        
                        st.markdown("<hr style='margin: 10px 0; border-top: 1px dashed #ccc;'>", unsafe_allow_html=True)
                        foto_nueva = st.file_uploader("**🔄 Reemplazar remito:**", type=["jpg", "png", "jpeg"], key=f"up_{fila['id']}", label_visibility="collapsed")
                        
                        if foto_nueva:
                            if st.button("💾 Guardar y Analizar Nueva Foto", key=f"btn_up_{fila['id']}", type="primary"):
                                with st.spinner("Subiendo imagen y analizando..."):
                                    exito_extraccion_manual = False
                                    intentos_restantes_manual = 3
                                    tiempo_espera_manual = 4
                                    
                                    while intentos_restantes_manual > 0 and not exito_extraccion_manual:
                                        try:
                                            timestamp = int(time.time())
                                            nombre_archivo = f"ADMIN_Orden{fila['id']}_{timestamp}_remito.jpg"
                                            file_bytes = foto_nueva.getvalue()
                                            
                                            supabase.storage.from_("remitos").upload(
                                                path=nombre_archivo, file=file_bytes, file_options={"content-type": foto_nueva.type}
                                            )
                                            
                                            url_publica = supabase.storage.from_("remitos").get_public_url(nombre_archivo)
                                            supabase.table("ordenes_carga").update({
                                                "url_foto": url_publica, "motivo_sin_foto": "Corregido por Auditoría"
                                            }).eq("id", fila['id']).execute()
                                            
                                            modelo_actual_manual = 'gemini-2.5-pro' if intentos_restantes_manual > 1 else 'gemini-2.5-flash'
                                            
                                            img_rem = Image.open(io.BytesIO(file_bytes))
                                            res_ia = cliente_ia.models.generate_content(model=modelo_actual_manual, contents=[PROMPT_AUDITORIA, img_rem])
                                            
                                            raw_t = res_ia.text.strip().replace('```json', '').replace('```', '')
                                            start = raw_t.find('{')
                                            end = raw_t.rfind('}') + 1
                                            if start != -1 and end != 0:
                                                d_ia = json.loads(raw_t[start:end])
                                                def limpiar_num(v):
                                                    try:
                                                        txt = str(v).replace('$', '').replace(' ', '').strip()
                                                        if ',' in txt and '.' in txt: txt = txt.replace('.', '').replace(',', '.')
                                                        elif ',' in txt: txt = txt.replace(',', '.')
                                                        return float(txt) if txt else 0.0
                                                    except: return 0.0
                                                
                                                st.session_state[f"ia_fec_{fila['id']}"] = str(d_ia.get('fecha', ''))
                                                st.session_state[f"ia_rs_{fila['id']}"] = str(d_ia.get('razon_social', ''))
                                                st.session_state[f"ia_lts_{fila['id']}"] = limpiar_num(d_ia.get('litros', 0.0))
                                                st.session_state[f"ia_imp_{fila['id']}"] = limpiar_num(d_ia.get('importe', 0.0))
                                                st.session_state[f"ia_fac_{fila['id']}"] = str(d_ia.get('comprobante', ''))
                                                st.session_state[f"ia_prod_{fila['id']}"] = str(d_ia.get('detalle_productos', ''))
                                                st.session_state[f"ia_obs_{fila['id']}"] = str(d_ia.get('observaciones_ia', ''))
                                            
                                            try: img_rem.close()
                                            except: pass
                                            gc.collect()
                                            
                                            exito_extraccion_manual = True
                                            st.success("✅ ¡Foto actualizada y leída por IA! Recargando...")
                                            time.sleep(1.5)
                                            st.rerun()
                                            
                                        except Exception as e:
                                            error_msg_manual = str(e)
                                            if "503" in error_msg_manual or "429" in error_msg_manual or "UNAVAILABLE" in error_msg_manual:
                                                intentos_restantes_manual -= 1
                                                if intentos_restantes_manual > 1:
                                                    time.sleep(tiempo_espera_manual)
                                                    tiempo_espera_manual *= 2 
                                                elif intentos_restantes_manual == 1:
                                                    time.sleep(2) 
                                                else:
                                                    st.error(f"❌ Falló incluso con el modelo de respaldo.")
                                            else:
                                                st.error(f"❌ Falla técnica inesperada.")
                                                break
                            
                    with c2:
                        if fila['id'] in st.session_state.agregados_excel:
                            st.success("✅ Añadido al reporte.")
                        else:
                            with st.form(key=f"form_aud_{fila['id']}"):
                                
                                detalles_bd = fila.get('detalle_combustibles')
                                if isinstance(detalles_bd, str):
                                    try: detalles_bd = json.loads(detalles_bd)
                                    except: detalles_bd = None
                                        
                                texto_pedido_cliente = ""
                                if detalles_bd and isinstance(detalles_bd, dict):
                                    texto_pedido_cliente = " | ".join([f"{k}: {v} L" if str(v).replace('.','',1).isdigit() else f"{k}: {v}" for k, v in detalles_bd.items()])
                                elif fila.get('litros_pedidos'):
                                    texto_pedido_cliente = f"Gas Oil 500 G2: {fila.get('litros_pedidos')} L"
                                else:
                                    texto_pedido_cliente = "Tanque Lleno / No especificado"
                                    
                                extras_bd = fila.get('articulos_extra')
                                if extras_bd and str(extras_bd).strip() and str(extras_bd).lower() != "nan":
                                    texto_pedido_cliente += f" 📦 Extras: {extras_bd}"
                                    
                                st.info(f"🛒 **Pedido original:**\n{texto_pedido_cliente}")

                                col_f1, col_f2 = st.columns(2)
                                fac_fecha = col_f1.text_input("Fecha", value=st.session_state.get(f"ia_fec_{fila['id']}", ""))
                                fac_rs = col_f2.text_input("Razón Social", value=st.session_state.get(f"ia_rs_{fila['id']}", ""))
                                
                                col_f3, col_f4 = st.columns(2)
                                fac_imp = col_f3.number_input("Importe ($)", value=st.session_state.get(f"ia_imp_{fila['id']}", 0.0))
                                fac_comp = col_f4.text_input("Nº Factura", value=st.session_state.get(f"ia_fac_{fila['id']}", ""))
                                
                                prod_ia_val = st.session_state.get(f"ia_prod_{fila['id']}", "")
                                obs_ia_val = st.session_state.get(f"ia_obs_{fila['id']}", "")
                                
                                if obs_ia_val:
                                    st.warning(f"⚠️ **{obs_ia_val}**")

                                fac_prod = st.text_input("Combustibles (IA)", value=prod_ia_val)
                                fac_obs = st.text_input("Observaciones (IA)", value=obs_ia_val)
                                
                                st.markdown("---")
                                efectivo_real_bd = fila.get('efectivo_entregado') if pd.notna(fila.get('efectivo_entregado')) else fila.get('efectivo_pedido', 0)
                                tiene_foto = pd.notna(fila['url_foto']) and str(fila['url_foto']).strip() != ""
                                lts_def = float(fila['litros_pedidos']) if tiene_foto else None
                                
                                nro_ord_gen, nro_ord_lts, nro_ord_efe = "", "", ""
                                
                                if es_especial:
                                    c_o1, c_o2 = st.columns(2)
                                    fac_lts = c_o1.number_input("Total Litros", value=st.session_state.get(f"ia_lts_{fila['id']}", lts_def))
                                    nro_ord_lts = c_o2.text_input("Nº Orden Litros", value=fila['nro_orden_litros_interna'] if pd.notna(fila['nro_orden_litros_interna']) else "")
                                    c_o3, c_o4 = st.columns(2)
                                    efectivo_final = c_o3.number_input("Efectivo Entregado", value=float(efectivo_real_bd))
                                    nro_ord_efe = c_o4.text_input("Nº Orden Efectivo", value=fila['nro_orden_efectivo_interna'] if pd.notna(fila['nro_orden_efectivo_interna']) else "")
                                else:
                                    c_o1, c_o2 = st.columns(2)
                                    fac_lts = c_o1.number_input("Total Litros", value=st.session_state.get(f"ia_lts_{fila['id']}", lts_def))
                                    nro_ord_gen = c_o2.text_input("Nº Orden Normal", value=fila['nro_orden_cliente'] if pd.notna(fila['nro_orden_cliente']) else "")
                                    efectivo_final = st.number_input("Efectivo Entregado", value=float(efectivo_real_bd))
                                    
                                if st.form_submit_button("✅ Guardar Fila"):
                                    st.session_state.agregados_excel.append(fila['id'])
                                    productos_a_guardar = []
                                    
                                    if "|" in fac_prod or ":" in fac_prod:
                                        partes = fac_prod.split("|")
                                        for p in partes:
                                            if ":" in p:
                                                nombre, lts_str = p.split(":", 1)
                                                lts_str = lts_str.replace(',', '.') 
                                                numeros = re.findall(r"[-+]?\d*\.\d+|\d+", lts_str)
                                                lts_indiv = float(numeros[0]) if numeros else 0.0
                                                productos_a_guardar.append({"nombre": nombre.strip(), "litros": lts_indiv})
                                            else:
                                                productos_a_guardar.append({"nombre": p.strip(), "litros": 0.0})
                                    else:
                                        productos_a_guardar.append({"nombre": fac_prod.strip(), "litros": fac_lts})
                                    
                                    producto_mayor = max(productos_a_guardar, key=lambda x: x['litros']) if productos_a_guardar else None

                                    for prod in productos_a_guardar:
                                        es_el_mayor = (prod == producto_mayor)
                                        
                                        efectivo_asignar = efectivo_final if es_el_mayor else 0.0
                                        importe_asignar = fac_imp if es_el_mayor else 0.0
                                        obs_asignar = fac_obs.strip() if es_el_mayor else ""
                                        
                                        st.session_state.resumen_para_cliente.append({
                                            "id_orden": int(fila['id']), 
                                            "Fecha": fac_fecha.strip(), "Chofer": chofer_txt.strip(), "Razón Social": fac_rs.strip(),
                                            "Litros": prod['litros'], 
                                            "Producto": prod['nombre'],
                                            "Observaciones": obs_asignar,
                                            "Nº Orden": convertir_a_numero(nro_ord_lts) if es_especial else convertir_a_numero(nro_ord_gen),
                                            "Importe": importe_asignar, "Nº Factura": fac_comp.strip(), "Entidad Pagadora": cliente_sel,
                                            "Efectivo": efectivo_asignar, "Nº Orden Efectivo": convertir_a_numero(nro_ord_efe) if es_especial else "-"
                                        })
                                    st.rerun()

    if st.session_state.resumen_para_cliente:
        st.markdown("<hr>", unsafe_allow_html=True)
        df_res = pd.DataFrame(st.session_state.resumen_para_cliente)
        
        df_res['Litros'] = pd.to_numeric(df_res['Litros'], errors='coerce').fillna(0)
        df_res['Importe'] = pd.to_numeric(df_res['Importe'], errors='coerce').fillna(0)
        df_res['Efectivo'] = pd.to_numeric(df_res['Efectivo'], errors='coerce').fillna(0)
        
        total_row = {col: "" for col in df_res.columns}
        total_row["Razón Social"] = "TOTALES:"
        total_row["Litros"] = df_res['Litros'].sum()
        total_row["Importe"] = df_res['Importe'].sum()
        total_row["Efectivo"] = df_res['Efectivo'].sum()
        
        df_export = pd.concat([df_res, pd.DataFrame([total_row])], ignore_index=True)

        st.subheader("📊 Resumen Final")
        cols_mostrar = [c for c in df_export.columns if c != "id_orden"]
        st.dataframe(df_export[cols_mostrar], use_container_width=True)
        
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as wr:
            df_export[cols_mostrar].to_excel(wr, index=False, sheet_name='Resumen_BC')
            ws = wr.sheets['Resumen_BC']
            
            fill_header = PatternFill(start_color="C8102E", end_color="C8102E", fill_type="solid")
            font_header = Font(color="FFFFFF", bold=True)
            font_total = Font(bold=True)
            fill_total = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
            borde = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

            for col_num, col_name in enumerate(cols_mostrar, 1):
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

        st.markdown("<br>", unsafe_allow_html=True)
        c_ex1, c_ex2 = st.columns(2)
        c_ex1.download_button("📥 Descargar Excel Final", data=buf.getvalue(), file_name=f"Resumen_{cliente_sel}.xlsx", use_container_width=True)
        
        if c_ex2.button("🗑️ Limpiar (Sin Auditar)"):
            st.session_state.resumen_para_cliente, st.session_state.agregados_excel = [], []
            st.session_state.pop(f"ia_procesada_{cliente_sel}", None) 
            st.rerun()
            
        st.markdown("<div class='tarjeta-pro' style='margin-top: 30px; text-align:center;'>", unsafe_allow_html=True)
        confirmar_cierre = st.checkbox("Confirmo que ya descargué el Excel y deseo cerrar estas órdenes.")
        if st.button("✅ MARCAR COMO AUDITADAS", disabled=not confirmar_cierre, use_container_width=True):
            if st.session_state.agregados_excel:
                ordenes_procesadas_db = []
                for item in st.session_state.resumen_para_cliente:
                    id_actual = item.get("id_orden")
                    
                    if id_actual and id_actual not in ordenes_procesadas_db:
                        filas_este_remito = [x for x in st.session_state.resumen_para_cliente if x.get("id_orden") == id_actual]
                        litros_totales = sum(float(x["Litros"]) for x in filas_este_remito)
                        importe_total = sum(float(x["Importe"]) for x in filas_este_remito)
                        texto_productos = " | ".join([f"{x['Producto']}: {x['Litros']}L" for x in filas_este_remito])
                        todas_obs = [x["Observaciones"] for x in filas_este_remito if x["Observaciones"].strip() != ""]
                        texto_obs = " | ".join(todas_obs)
                        
                        supabase.table("ordenes_carga").update({
                            "estado": "AUDITADO", "litros_reales": litros_totales,
                            "numero_factura": item["Nº Factura"], "monto_factura": importe_total,
                            "producto_ia": texto_productos, "observaciones_ia": texto_obs
                        }).eq("id", id_actual).execute()
                        ordenes_procesadas_db.append(id_actual)
                        
            st.session_state.resumen_para_cliente, st.session_state.agregados_excel = [], []
            st.session_state.pop(f"ia_procesada_{cliente_sel}", None) 
            st.success("¡Lote cerrado exitosamente y guardado en la base de datos!")
            time.sleep(1.5)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# 5. MÓDULO: VERIFICACIÓN BCRA Y CHEQUES (IA AVANZADA)
# ==========================================
elif opcion == "Verificación BCRA":
    import utils_bcra  # 🚀 IMPORTAMOS TU NUEVO MOTOR
    import requests
    import time
    import json
    import urllib3
    import re
    import random
    import io
    import pandas as pd
    from datetime import datetime
    from PIL import Image
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # --- INTERFAZ CON 3 PESTAÑAS ---
    tab_manual, tab_ia, tab_masivo = st.tabs(["✍️ Consulta Manual", "📸 Escáner de Cheques (IA Pro)", "📋 Carga Masiva (Excel)"])

    # ==========================================
    # PESTAÑA 1: CONSULTA MANUAL
    # ==========================================
    with tab_manual:
        st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
        cuit_input = st.text_input("Ingresá el CUIT (solo números)", max_chars=11, key="cuit_manual")
        
        if st.button("Validar Riesgo Manual"):
            cuit_limpio = re.sub(r'\D', '', cuit_input)
            
            if len(cuit_limpio) != 11:
                st.error("❌ CUIT inválido. Debe contener exactamente 11 números.")
            else:
                registro_interno = supabase.table("cuits_afectados").select("*").eq("cuit", cuit_limpio).execute()
                if registro_interno.data:
                    st.error(f"⚠️ Este CUIT ya está en nuestra lista de AFECTADOS (Nivel {registro_interno.data[0]['situacion_bcra']}).")
                else:
                    with st.spinner('Consultando historial en el BCRA...'):
                        # 🚀 LLAMADA AL MOTOR EXTERNO
                        datos = utils_bcra.consultar_bcra_completo(cuit_limpio)
                        if datos and not datos.get("error_api"):
                            st.markdown(f"**Titular:** {datos['denominacion']}")
                            col1, col2 = st.columns(2)
                            col1.metric("Situación Crediticia", f"Nivel {datos['situacion']}")
                            if datos['cheques_rechazados'] > 0:
                                col2.error(f"⚠️ {datos['cheques_rechazados']} Cheques Rechazados")
                                st.warning("🚨 RIESGO DETECTADO EN EL BCRA.")
                                if st.button("Confirmar y Enviar a Lista Negra", key="btn_save_manual"):
                                    # 🚀 LLAMADA AL MOTOR EXTERNO (PASANDO SUPABASE)
                                    utils_bcra.guardar_en_lista_negra(supabase, cuit_limpio, datos['situacion'], datos['denominacion'], f"Rechazos: {datos['cheques_rechazados']}")
                            elif datos['cheques_rechazados'] == 0:
                                col2.success("✅ 0 Cheques Rechazados")
                                st.success("Operación totalmente segura.")
                            else:
                                col2.warning("El BCRA bloqueó la lectura del historial. Intente nuevamente.")
                        elif datos and datos.get("error_api"):
                            st.error(f"Falla de conexión con el túnel (ScraperAPI): {datos['error_api']}")
        st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # PESTAÑA 2: ESCÁNER DE LOTES MÚLTIPLES (IA PRO + COLA)
    # ==========================================
    with tab_ia:
        if 'lote_procesado' not in st.session_state:
            st.session_state['lote_procesado'] = []

        fotos_lote = st.file_uploader("📸 Subí hasta 3 fotos de cheques", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)
        
        if fotos_lote:
            if st.button("🚀 Procesar Lotes (IA Avanzada)", type="primary"):
                st.session_state['lote_procesado'] = [] 
                
                with st.spinner("Procesando fotos y consultando BCRA..."):
                    barra_p = st.progress(0)
                    total_fotos = len(fotos_lote)
                    
                    for idx, foto in enumerate(fotos_lote):
                        img = Image.open(foto)
                        img.thumbnail((2500, 3000), Image.Resampling.LANCZOS)
                        
                        # 🚀 LLAMADA AL MOTOR EXTERNO (PASANDO CLIENTE_IA)
                        lista_cheques = utils_bcra.procesar_lote_cheques_ia(cliente_ia, img)
                        
                        for cheque in lista_cheques:
                            cuit_limpio = re.sub(r'\D', '', str(cheque.get("cuit", "")))
                            datos_bcra = None
                            
                            if len(cuit_limpio) == 11:
                                time.sleep(random.uniform(1.5, 3.5)) 
                                # 🚀 LLAMADA AL MOTOR EXTERNO
                                datos_bcra = utils_bcra.consultar_bcra_completo(cuit_limpio)
                            
                            st.session_state['lote_procesado'].append({
                                "img": img, 
                                "id": cheque.get("id"),
                                "numero_cheque": cheque.get("numero_cheque"),
                                "emisor": cheque.get("emisor"),
                                "cuit": cheque.get("cuit"),
                                "cuit_limpio": cuit_limpio,
                                "datos_bcra": datos_bcra
                            })
                        
                        barra_p.progress((idx + 1) / total_fotos)
                    
                    st.success("✅ Lote procesado completamente.")

        # --- RENDERIZADO DE RESULTADOS ---
        if st.session_state.get('lote_procesado'):
            st.markdown("### 📋 Resultados de Auditoría")
            
            for i, cheque in enumerate(st.session_state['lote_procesado']):
                st.markdown("---")
                col1, col2 = st.columns([1, 2])
                with col1:
                    with st.expander("Ver Foto"):
                        st.image(cheque["img"], use_container_width=True)
                with col2:
                    st.markdown(f"**🏦 Cheque Nº {cheque.get('numero_cheque')}** | **Emisor:** {cheque.get('emisor')}")
                    st.markdown(f"**CUIT:** `{cheque.get('cuit')}`")
                    
                    bcra = cheque.get("datos_bcra")
                    if bcra and not bcra.get("error_api"):
                        if bcra['situacion'] == 1 and bcra['cheques_rechazados'] == 0:
                            st.success(f"✅ BCRA: {bcra['denominacion']} | Sit: 1 | 0 Rechazos")
                        else:
                            st.error(f"🚨 BCRA: {bcra['denominacion']} | Sit: {bcra['situacion']} | Rechazos: {bcra['cheques_rechazados']}")
                            if st.button(f"Guardar en Lista Negra", key=f"btn_lote_{i}"):
                                # 🚀 LLAMADA AL MOTOR EXTERNO (PASANDO SUPABASE)
                                utils_bcra.guardar_en_lista_negra(supabase, cheque['cuit_limpio'], bcra['situacion'], bcra['denominacion'], f"Rechazos: {bcra['cheques_rechazados']}")
                    else:
                        st.warning("⚠️ Consulta fallida o CUIT inválido.")
                        if bcra and bcra.get("error_api"):
                            st.error(f"Error Técnico: {bcra['error_api']}")
                        
            if st.button("🧹 Limpiar Resultados"):
                st.session_state['lote_procesado'] = []
                st.rerun()

    # ==========================================
    # PESTAÑA 3: CARGA MASIVA (CAJA DE DISPARO RÁPIDO)
    # ==========================================
    with tab_masivo:
        if 'resultados_masivos' not in st.session_state:
            st.session_state['resultados_masivos'] = None

        st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
        st.info("💡 Pegá una lista de CUITs (ej. copiados desde un Excel). El sistema los filtrará y procesará automáticamente.")
        texto_cuits = st.text_area("Lista de CUITs", height=150, placeholder="30123456789\n20123456789\n...")
        
        if st.button("🚀 Iniciar Consulta Masiva"):
            lineas = texto_cuits.replace('-', '').replace(' ', '\n').split('\n')
            lista_cuits = []
            
            for l in lineas:
                c = re.sub(r'\D', '', l)
                if len(c) == 11 and c not in lista_cuits:
                    lista_cuits.append(c)
            
            if not lista_cuits:
                st.error("❌ No se detectaron CUITs válidos de 11 dígitos en el texto.")
            else:
                if len(lista_cuits) > 20:
                    st.warning(f"⚠️ Detectamos {len(lista_cuits)} CUITs. Para evitar bloqueos, procesaremos solo los primeros 20.")
                    lista_cuits = lista_cuits[:20]
                    
                st.write(f"⏳ Procesando {len(lista_cuits)} CUITs... Podés dejar esta pestaña abierta.")
                barra_p = st.progress(0)
                resultados_temporales = []
                
                for i, cuit in enumerate(lista_cuits):
                    # 🚀 LLAMADA AL MOTOR EXTERNO
                    datos = utils_bcra.consultar_bcra_completo(cuit)
                    
                    if datos and not datos.get("error_api"):
                        sit = datos.get("situacion", "")
                        rechazos = datos.get("cheques_rechazados", "")
                        nombre = datos.get("denominacion", "")
                        
                        estado = "🟢 APROBADO" if sit == 1 and rechazos == 0 else "🔴 RECHAZADO"
                        if rechazos in [-1, -429]: estado = "⚠️ ERROR API"
                            
                        resultados_temporales.append({
                            "CUIT": cuit, "Razón Social": nombre, 
                            "Situación": sit, "Cheques Rech.": rechazos, "Estado": estado
                        })
                    else:
                        motivo_real = datos.get("error_api", "Error fatal desconocido") if datos else "Timeout masivo"
                        resultados_temporales.append({
                            "CUIT": cuit, "Razón Social": f"🚨 {motivo_real}", 
                            "Situación": "-", "Cheques Rech.": "-", "Estado": "⚠️ ERROR"
                        })
                        
                    barra_p.progress((i + 1) / len(lista_cuits))
                    time.sleep(1.5) 
                
                st.success("✅ ¡Consulta Masiva Finalizada!")
                st.session_state['resultados_masivos'] = resultados_temporales
                st.rerun()

        if st.session_state.get('resultados_masivos'):
            df_masivo = pd.DataFrame(st.session_state['resultados_masivos'])
            st.dataframe(df_masivo, use_container_width=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            col_btn1, col_btn2 = st.columns(2)
            
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as wr:
                df_masivo.to_excel(wr, index=False, sheet_name='Reporte BCRA')
            
            col_btn1.download_button(
                "📥 Descargar Reporte en Excel", 
                data=buf.getvalue(), 
                file_name=f"Reporte_Riesgo_{datetime.now().strftime('%d%m%Y')}.xlsx", 
                use_container_width=True
            )
            
            if col_btn2.button("🧹 Limpiar Pantalla", use_container_width=True):
                st.session_state['resultados_masivos'] = None
                st.rerun()
                
        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# 6. MÓDULO: GESTIÓN DE CLIENTES (ADMINISTRACIÓN)
# ==========================================
elif opcion == "Gestión de Clientes":
    st.title("👥 Gestión de Clientes")
    st.markdown('<p style="color:#666; font-size:16px;">Administración centralizada de cuentas corrientes, límites y permisos.</p>', unsafe_allow_html=True)

    # Dividimos en dos pestañas para que quede súper prolijo
    tab_editar, tab_alta = st.tabs(["📝 Editar Clientes", "➕ Dar de Alta Nuevo Cliente"])

    with tab_editar:
        st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
        # Traemos todos los clientes ordenados alfabéticamente
        res_clientes = supabase.table("clientes").select("*").order("nombre").execute()
        clientes_db = res_clientes.data

        if clientes_db:
            nombres_clientes = [c['nombre'] for c in clientes_db]
            cliente_sel = st.selectbox("Seleccionar cliente a administrar:", ["--- Seleccionar ---"] + nombres_clientes)

            if cliente_sel != "--- Seleccionar ---":
                st.markdown("<hr>", unsafe_allow_html=True)
                # Buscamos los datos del cliente seleccionado
                c_data = next(c for c in clientes_db if c['nombre'] == cliente_sel)

                # Etiqueta visual rápida
                if c_data.get('habilitado', True):
                    st.success("🟢 ESTADO: HABILITADO")
                else:
                    st.error("⛔ ESTADO: INHABILITADO")

                with st.form(f"form_edit_{c_data['id']}"):
                    st.subheader(f"Datos de {c_data['nombre']}")
                    c1, c2 = st.columns(2)
                    limite = c1.number_input("Límite de Efectivo ($)", value=float(c_data.get('limite_efectivo', 0)))
                    
                    st.markdown("**Permisos y Configuraciones:**")
                    c3, c4 = st.columns(2)
                    req_foto = c3.checkbox("Foto de remito obligatoria", value=c_data.get('requiere_foto_remito', False))
                    formato_esp = c4.checkbox("Formato Especial (Órdenes Lts/Efe)", value=c_data.get('formato_especial', False))

                    c5, c6 = st.columns(2)
                    exige_cuit = c5.checkbox("Exigir CUIT/RS Factura", value=c_data.get('elige_cuit_facturar', False))
                    habilitado = c6.checkbox("Cliente Habilitado", value=c_data.get('habilitado', True))

                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True):
                        try:
                            supabase.table("clientes").update({
                                "limite_efectivo": limite,
                                "requiere_foto_remito": req_foto,
                                "formato_especial": formato_esp,
                                "elige_cuit_facturar": exige_cuit,
                                "habilitado": habilitado
                            }).eq("id", c_data['id']).execute()
                            st.success("✅ ¡Cliente actualizado con éxito!")
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar: {e}")
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_alta:
        st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
        with st.form("form_alta"):
            st.subheader("Carga de Datos Iniciales")
            c1, c2 = st.columns(2)
            nombre_nuevo = c1.text_input("Razón Social / Nombre (Ej: TRANSPORTE S.H)").upper()
            cuit_nuevo = c2.text_input("CUIT (Sin guiones)")

            c3, c4 = st.columns(2)
            suc_madre = c3.selectbox("Sucursal Madre", [1, 2, 3, 4], format_func=lambda x: NOMBRES_SUCURSALES.get(x))
            limite_nuevo = c4.number_input("Límite de Efectivo ($)", min_value=0, value=0)

            auth_id = st.text_input("UUID de Autenticación (Supabase Auth)", help="Pegá acá el ID del usuario creado en la sección Authentication de Supabase")

            st.markdown("**Permisos Iniciales:**")
            col_p1, col_p2 = st.columns(2)
            req_foto_n = col_p1.checkbox("Requiere foto de remito obligatoria")
            formato_esp_n = col_p2.checkbox("Usar Formato Especial")

            col_p3, col_p4 = st.columns(2)
            exige_cuit_n = col_p3.checkbox("Exigir CUIT/RS en Factura")
            hab_n = col_p4.checkbox("Habilitado para operar", value=True)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("🚀 Dar de Alta Cliente", type="primary", use_container_width=True):
                if not nombre_nuevo or not cuit_nuevo or not auth_id:
                    st.error("⚠️ Por favor, completá el Nombre, CUIT y el UUID de Autenticación.")
                else:
                    try:
                        supabase.table("clientes").insert({
                            "nombre": nombre_nuevo,
                            "cuit": cuit_nuevo,
                            "sucursal_madre_id": suc_madre,
                            "limite_efectivo": limite_nuevo,
                            "auth_user_id": auth_id,
                            "requiere_foto_remito": req_foto_n,
                            "formato_especial": formato_esp_n,
                            "elige_cuit_facturar": exige_cuit_n,
                            "habilitado": hab_n
                        }).execute()
                        st.success("✅ ¡Golazo! Cliente registrado exitosamente en la base de datos.")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al crear: {e}")
        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# 7. MÓDULO: LABORATORIO IA (COBRANZAS)
# ==========================================
elif opcion == "Laboratorio IA":
    # Leemos y ejecutamos el archivo directamente
    with open("bot.py", encoding="utf-8") as f:
        exec(f.read())
        st.markdown('</div>', unsafe_allow_html=True)
