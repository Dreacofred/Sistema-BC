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
COLOR_GRIS_BC = "#3A3A3A" # El gris oscuro de la web oficial

URL_SB = "https://bjhykcdhafoqpfkpngvw.supabase.co"
KEY_SB = "sb_publishable_OvXN3LjawazkF5GNpsslUQ_SQOhTakr"
supabase: Client = create_client(URL_SB, KEY_SB)

NOMBRES_SUCURSALES = {1: "RECONQUISTA", 2: "AVELLANEDA", 3: "FLORENCIA", 4: "RECREO"}

# Configuramos la página primero
st.set_page_config(page_title="BC Combustibles - Gestión Pro", page_icon="⛽", layout="wide")

# CSS MEJORADO PARA LOOK PROFESIONAL (AHORA CON GRIS BC)
st.markdown(f"""
    <style>
        [data-testid="stSidebarNav"] {{display: none !important;}}
        .stApp {{ background-color: #f4f6f9 !important; }}
        h1, h2, h3 {{ color: {COLOR_ROJO} !important; font-family: 'Montserrat', sans-serif; font-weight: 700; }}
        
        /* Estilo de botones principales */
        .stButton>button {{ 
            background-color: {COLOR_ROJO}; color: white; border-radius: 8px; 
            font-weight: 600; height: 2.8em; border: none; width: 100%; transition: all 0.3s;
        }}
        .stButton>button:hover {{ background-color: #900b20; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
        
        /* HEADER Y SIDEBAR GRIS OSCURO */
        [data-testid="stHeader"] {{ background-color: {COLOR_GRIS_BC} !important; }}
        [data-testid="stSidebar"] {{ background-color: {COLOR_GRIS_BC} !important; border-right: none; }}
        
        /* Forzar texto blanco en la barra lateral */
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] div {{ color: #ffffff !important; }}
        
        div[data-testid="stMetricValue"] {{ color: {COLOR_ROJO} !important; }}
        
        /* Contenedores tipo tarjeta */
        .tarjeta-pro {{
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; margin-bottom: 20px;
        }}
    </style>
""", unsafe_allow_html=True)

cliente_ia = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# Link al logo oficial
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

# DISEÑO DEL MENÚ LATERAL (SIDEBAR) CON FONDO OSCURO
with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    st.image(URL_LOGO_OFICIAL, use_container_width=True)
    
    # Tarjeta de operador en tonos oscuros
    st.markdown(f"""
        <div style="background:#2C2C2C; padding:15px; border-radius:10px; border-left:4px solid {COLOR_ROJO}; margin-bottom:20px;">
            <p style="margin:0; font-size:13px; color:#B0B0B0 !important;">Operador activo:</p>
            <h4 style="margin:0; color:#FFFFFF !important; padding-top: 5px;">{usuario_app}</h4>
            <p style="margin:0; font-size:13px; color:#B0B0B0 !important; margin-top:5px;">📍 {NOMBRES_SUCURSALES.get(user['sucursal_id'], 'BC')}</p>
        </div>
    """, unsafe_allow_html=True)

    # MENÚ MODERNO ADAPTADO PARA FONDO GRIS
    opcion = option_menu(
        menu_title=None, 
        options=["Generador de Resumen", "Facturas de Proveedores", "Verificación BCRA"],
        icons=["file-earmark-spreadsheet", "receipt", "shield-check"], 
        menu_icon="cast", 
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": COLOR_GRIS_BC},
            "icon": {"color": "#FFFFFF", "font-size": "18px"}, 
            "nav-link": {"color": "#FFFFFF", "font-size": "15px", "text-align": "left", "margin":"5px 0", "--hover-color": "#4A4A4A", "border-radius": "8px"},
            "nav-link-selected": {"background-color": COLOR_ROJO, "color": "white"},
        }
    )

    st.markdown("<br><br>", unsafe_allow_html=True)
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.usuario_autenticado = None
        st.rerun()

# Inicializar estados
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
        st.markdown(f'<div class="tarjeta-pro" style="border-left: 5px solid {COLOR_ROJO}; padding:15px;">📍 <strong>Acceso Zonal:</strong> Visualizando solo órdenes de la sucursal <strong>{NOMBRES_SUCURSALES.get(user['sucursal_id'])}</strong>.</div>', unsafe_allow_html=True)

    try:
        query = supabase.table("ordenes_carga").select("*, clientes(nombre, formato_especial)")
        if user['puesto'] != 'SUPER_ADMIN':
            query = query.eq("sucursal_carga_id", user['sucursal_id'])
            
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

        # KPIs Rápidos
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
                                try:
                                    res_img = requests.get(fila['url_foto'])
                                    img_rem = Image.open(io.BytesIO(res_img.content))
                                    prompt_auditoria = """Experto auditor. Emisor es 'BC COMBUSTIBLES'. Buscá al CLIENTE Receptor. Extraé fecha, razon_social, litros, importe, comprobante en JSON puro."""
                                    res_ia = cliente_ia.models.generate_content(model='gemini-2.5-pro', contents=[prompt_auditoria, img_rem])
                                    
                                    raw_t = res_ia.text.strip().replace('```json', '').replace('```', '')
                                    
                                    # Intentamos extraer el JSON de forma segura
                                    start = raw_t.find('{')
                                    end = raw_t.rfind('}') + 1
                                    if start != -1 and end != 0:
                                        d_ia = json.loads(raw_t[start:end])
                                        
                                        # Función para procesar números con comas y puntos (estilo Argentino)
                                        def limpiar_num(v):
                                            try:
                                                txt = str(v).replace('$', '').replace(' ', '').strip()
                                                if ',' in txt and '.' in txt:
                                                    txt = txt.replace('.', '').replace(',', '.')
                                                elif ',' in txt:
                                                    txt = txt.replace(',', '.')
                                                return float(txt) if txt else 0.0
                                            except:
                                                return 0.0
                                                
                                        st.session_state[f"ia_fec_{fila['id']}"] = str(d_ia.get('fecha', ''))
                                        st.session_state[f"ia_rs_{fila['id']}"] = str(d_ia.get('razon_social', ''))
                                        st.session_state[f"ia_lts_{fila['id']}"] = limpiar_num(d_ia.get('litros', 0.0))
                                        st.session_state[f"ia_imp_{fila['id']}"] = limpiar_num(d_ia.get('importe', 0.0))
                                        st.session_state[f"ia_fac_{fila['id']}"] = str(d_ia.get('comprobante', ''))
                                    else:
                                        st.warning(f"La IA no devolvió un formato válido para la orden #{fila['id']}")
                                        
                                except Exception as e:
                                    # AHORA SÍ VEMOS EL ERROR EN PANTALLA EN LUGAR DE IGNORARLO
                                    st.error(f"Falla técnica en orden #{fila['id']}: {e}")
                                    
                                barra_p.progress((i + 1) / total)
                                
                        st.session_state[clave_estado_ia] = True
                        st.success("✅ Extracción completa.")
                        time.sleep(2) # Le damos 2 segundos para que puedas leer si hubo algún error rojo
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
                            st.markdown(f"*[Ver foto en tamaño completo]({fila['url_foto']})*")
                        else:
                            st.warning(f"⚠️ SIN FOTO: {fila['motivo_sin_foto']}")
                            
                    with c2:
                        if fila['id'] in st.session_state.agregados_excel:
                            st.success("✅ Añadido al reporte.")
                        else:
                            with st.form(key=f"form_aud_{fila['id']}"):
                                col_f1, col_f2 = st.columns(2)
                                fac_fecha = col_f1.text_input("Fecha", value=st.session_state.get(f"ia_fec_{fila['id']}", ""))
                                fac_rs = col_f2.text_input("Razón Social", value=st.session_state.get(f"ia_rs_{fila['id']}", ""))
                                
                                col_f3, col_f4 = st.columns(2)
                                fac_imp = col_f3.number_input("Importe ($)", value=st.session_state.get(f"ia_imp_{fila['id']}", 0.0))
                                fac_comp = col_f4.text_input("Nº Factura", value=st.session_state.get(f"ia_fac_{fila['id']}", ""))
                                
                                st.markdown("---")
                                efectivo_real_bd = fila.get('efectivo_entregado') if pd.notna(fila.get('efectivo_entregado')) else fila.get('efectivo_pedido', 0)
                                tiene_foto = pd.notna(fila['url_foto']) and str(fila['url_foto']).strip() != ""
                                lts_def = float(fila['litros_pedidos']) if tiene_foto else None
                                
                                nro_ord_gen, nro_ord_lts, nro_ord_efe = "", "", ""
                                
                                if es_especial:
                                    c_o1, c_o2 = st.columns(2)
                                    fac_lts = c_o1.number_input("Litros", value=st.session_state.get(f"ia_lts_{fila['id']}", lts_def))
                                    nro_ord_lts = c_o2.text_input("Nº Orden Litros", value=fila['nro_orden_litros_interna'] if pd.notna(fila['nro_orden_litros_interna']) else "")
                                    c_o3, c_o4 = st.columns(2)
                                    efectivo_final = c_o3.number_input("Efectivo Entregado", value=float(efectivo_real_bd))
                                    nro_ord_efe = c_o4.text_input("Nº Orden Efectivo", value=fila['nro_orden_efectivo_interna'] if pd.notna(fila['nro_orden_efectivo_interna']) else "")
                                else:
                                    c_o1, c_o2 = st.columns(2)
                                    fac_lts = c_o1.number_input("Litros", value=st.session_state.get(f"ia_lts_{fila['id']}", lts_def))
                                    nro_ord_gen = c_o2.text_input("Nº Orden (Normal)", value=fila['nro_orden_cliente'] if pd.notna(fila['nro_orden_cliente']) else "")
                                    efectivo_final = st.number_input("Efectivo Entregado", value=float(efectivo_real_bd))
                                if st.form_submit_button("✅ Guardar Fila"):
                                    st.session_state.agregados_excel.append(fila['id'])
                                    st.session_state.resumen_para_cliente.append({
                                        "id_orden": int(fila['id']), # ACÁ ESTÁ LA MAGIA: Guardamos el ID para usarlo al final
                                        "Fecha": fac_fecha.strip(), "Chofer": chofer_txt.strip(), "Razón Social": fac_rs.strip(),
                                        "Litros": fac_lts, "Nº Orden": convertir_a_numero(nro_ord_lts) if es_especial else convertir_a_numero(nro_ord_gen),
                                        "Importe": fac_imp, "Nº Factura": fac_comp.strip(), "Entidad Pagadora": cliente_sel,
                                        "Efectivo": efectivo_final, "Nº Orden Efectivo": convertir_a_numero(nro_ord_efe) if es_especial else "-"
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
                # Recorremos la memoria para sacar los datos reales y enviarlos a la BD
                for item in st.session_state.resumen_para_cliente:
                    if "id_orden" in item:
                        supabase.table("ordenes_carga").update({
                            "estado": "AUDITADO",
                            "litros_reales": item["Litros"],
                            "numero_factura": item["Nº Factura"],
                            "monto_factura": item["Importe"]
                        }).eq("id", item["id_orden"]).execute()
                        
            st.session_state.resumen_para_cliente, st.session_state.agregados_excel = [], []
            st.session_state.pop(f"ia_procesada_{cliente_sel}", None) 
            st.success("¡Lote cerrado exitosamente y guardado en la base de datos!")
            time.sleep(1.5)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# 5. MÓDULO: VERIFICACIÓN BCRA (VÍA PUENTE ROBUSTO)
# ==========================================
elif opcion == "Verificación BCRA":
    st.title("🛡️ Verificación Blindada de CUIT")
    st.markdown('<p style="color:#666; font-size:16px;">Consultá el estado crediticio en la base interna y en el BCRA.</p>', unsafe_allow_html=True)
    
    def consultar_bcra(cuit):
        # Limpiamos el CUIT por seguridad
        cuit = str(cuit).strip()
        url_oficial = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/{cuit}"
        
        # Usamos el endpoint normal de AllOrigins para obtener un objeto JSON envuelto (Sugerencia del Gem)
        url_puente = f"https://api.allorigins.win/get?url={requests.utils.quote(url_oficial)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BC-Combustibles/1.0"
        }
        
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # ¡CLAVE! Subimos el tiempo límite de 15 a 30 segundos
            response = requests.get(url_puente, headers=headers, verify=False, timeout=30)
            
            if response.status_code == 200:
                # AllOrigins devuelve el JSON del BCRA dentro de una propiedad 'contents'
                wrapper_data = response.json()
                inner_content = wrapper_data.get('contents')
                
                if not inner_content:
                    return None

                # El contenido interno viene como String, hay que parsearlo a JSON
                import json
                data = json.loads(inner_content)
                
                # Chequeamos el status del BCRA (puede estar dentro del JSON)
                if data.get('status') == 200 and 'results' in data:
                    res = data['results']
                    periodos = res.get('periodos', [])
                    
                    if periodos and 'entidades' in periodos[0] and periodos[0]['entidades']:
                        entidad_info = periodos[0]['entidades'][0]
                        return {
                            "situacion": entidad_info.get("situacion", 1),
                            "entidad": entidad_info.get("entidad", "Entidad Financiera"),
                            "denominacion": res.get('denominacion', 'Cliente')
                        }
                    else:
                        # Si no hay periodos con deudas, se considera Limpio
                        return "SIN_DEUDAS"
                elif data.get('status') == 404:
                    # El BCRA tira 404 si el CUIT no tiene deudas registradas
                    return "SIN_DEUDAS"
                
                return None
                
            elif response.status_code == 404:
                return "SIN_DEUDAS"
            else:
                st.error(f"Error en Puente: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            # Si tarda más de 30 segundos, mostramos un cartel amable en vez de un error rojo
            st.warning("⏱️ El puente gratuito está saturado y tardó demasiado. Volvé a intentar en unos segundos.")
            return None
        except Exception as e:
            st.error(f"Error interno: {str(e)}")
            return None

    def guardar_cuit_afectado(cuit, situacion, nombre):
        try:
            supabase.table("cuits_afectados").insert({
                "cuit": cuit, 
                "situacion_bcra": situacion,
                "observaciones": f"Titular: {nombre} - BCRA Oficial (Vía Puente)"
            }).execute()
        except Exception as e:
            st.error(f"Error guardando en BD local: {e}")

    st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
    cuit_input = st.text_input("Ingresá el CUIT a verificar (solo números)", max_chars=11, placeholder="Ej: 30123456789")

    if st.button("Validar Riesgo"):
        if len(cuit_input) != 11 or not cuit_input.isdigit():
            st.error("❌ Por favor, ingresá un CUIT válido de 11 dígitos.")
        else:
            try:
                # 1. Base interna (Supabase)
                registro_interno = supabase.table("cuits_afectados").select("*").eq("cuit", cuit_input).execute()
                
                if registro_interno.data:
                    st.error(f"⚠️ ¡ATENCIÓN! Este CUIT ya está en nuestra lista de AFECTADOS.")
                    st.warning(f"Situación registrada anteriormente: Nivel {registro_interno.data[0]['situacion_bcra']}")
                    st.info("No hace falta consultar al BCRA, ya tenemos antecedentes negativos internos.")
                else:
                    # 2. Consulta al BCRA Oficial vía Puente
                    with st.spinner('Consultando base oficial del Banco Central vía API Puente...'):
                        datos_bcra = consultar_bcra(cuit_input)
                        
                        if datos_bcra == "SIN_DEUDAS":
                            st.success("✅ Cliente Limpio. No registra deudas en el sistema financiero (Situación 1). Operación segura.")
                        elif isinstance(datos_bcra, dict):
                            situacion = datos_bcra['situacion']
                            entidad = datos_bcra['entidad']
                            nombre = datos_bcra['denominacion']
                            
                            st.markdown(f"**Titular:** {nombre}")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("Situación Actual", f"Nivel {situacion}")
                            
                            if situacion == 1:
                                st.success(f"✅ Cliente Limpio (Situación 1 en {entidad}). Operación segura.")
                            else:
                                st.error(f"🚨 RIESGO DETECTADO: Situación {situacion} en {entidad}.")
                                st.warning("El CUIT fue ingresado automáticamente a nuestra lista negra.")
                                guardar_cuit_afectado(cuit_input, situacion, nombre)
                        elif datos_bcra is None:
                            st.warning("El servicio puente no pudo alcanzar al BCRA. Intentá nuevamente en unos minutos.")
            except Exception as e:
                st.error(f"Error de sistema: {e}")
    st.markdown('</div>', unsafe_allow_html=True)
