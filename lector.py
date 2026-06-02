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

st.set_page_config(page_title="BC Combustibles - Gestión Pro", page_icon="⛽", layout="wide")

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

with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    st.image(URL_LOGO_OFICIAL, use_container_width=True)
    
    st.markdown(f"""
        <div style="background:#2C2C2C; padding:15px; border-radius:10px; border-left:4px solid {COLOR_ROJO}; margin-bottom:20px;">
            <p style="margin:0; font-size:13px; color:#B0B0B0 !important;">Operador activo:</p>
            <h4 style="margin:0; color:#FFFFFF !important; padding-top: 5px;">{usuario_app}</h4>
            <p style="margin:0; font-size:13px; color:#B0B0B0 !important; margin-top:5px;">📍 {NOMBRES_SUCURSALES.get(user['sucursal_id'], 'BC')}</p>
        </div>
    """, unsafe_allow_html=True)

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
                            
                            # ==========================================
                            # 🧹 LIMPIEZA DE MEMORIA PROVEEDORES
                            # ==========================================
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
        st.markdown(f'<div class="tarjeta-pro" style="border-left: 5px solid {COLOR_ROJO}; padding:15px;">📍 <strong>Acceso Zonal:</strong> Visualizando solo órdenes de la sucursal <strong>{NOMBRES_SUCURSALES.get(user['sucursal_id'])}</strong>.</div>', unsafe_allow_html=True)

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

    # ==========================================
    # MODIFICACIÓN: FILTRO POR SUCURSAL MADRE DEL CLIENTE
    # ==========================================
    try:
        # La magia está en agregar !inner pegado a la palabra clientes
        query = supabase.table("ordenes_carga").select("*, clientes!inner(nombre, formato_especial, sucursal_madre_id)")
        
        # Si no es Super Admin, filtramos por la sucursal madre del CLIENTE
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
                                            
                                        # ==========================================
                                        # 🧹 LIMPIEZA DE MEMORIA OBLIGATORIA (OOM FIX)
                                        # ==========================================
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
                                                st.warning(f"⏳ Google (Pro) saturado. Reintentando orden #{fila['id']} en {tiempo_espera} seg...")
                                                time.sleep(tiempo_espera)
                                                tiempo_espera *= 2 
                                            elif intentos_restantes == 1:
                                                st.warning(f"⚠️ Google (Pro) sigue caído. Cambiando a modelo Flash (Respaldo) para la orden #{fila['id']}...")
                                                time.sleep(2) 
                                            else:
                                                st.error(f"❌ Falló la orden #{fila['id']} incluso con el modelo de respaldo. Intentá más tarde.")
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
                            st.markdown(f"*[Ver foto en tamaño completo]({fila['url_foto']})*")
                        else:
                            st.warning(f"⚠️ SIN FOTO: {fila.get('motivo_sin_foto', 'No se indicó motivo')}")
                        
                        st.markdown("<hr style='margin: 10px 0; border-top: 1px dashed #ccc;'>", unsafe_allow_html=True)
                        st.markdown("**🔄 Reemplazar o Subir remito correcto:**")
                        foto_nueva = st.file_uploader("", type=["jpg", "png", "jpeg"], key=f"up_{fila['id']}", label_visibility="collapsed")
                        
                        if foto_nueva:
                            if st.button("💾 Guardar y Analizar Nueva Foto", key=f"btn_up_{fila['id']}", type="primary"):
                                with st.spinner("Subiendo imagen y analizando con IA..."):
                                    
                                    exito_extraccion_manual = False
                                    intentos_restantes_manual = 3
                                    tiempo_espera_manual = 4
                                    
                                    while intentos_restantes_manual > 0 and not exito_extraccion_manual:
                                        try:
                                            timestamp = int(time.time())
                                            nombre_archivo = f"ADMIN_Orden{fila['id']}_{timestamp}_remito.jpg"
                                            file_bytes = foto_nueva.getvalue()
                                            
                                            supabase.storage.from_("remitos").upload(
                                                path=nombre_archivo,
                                                file=file_bytes,
                                                file_options={"content-type": foto_nueva.type}
                                            )
                                            
                                            url_publica = supabase.storage.from_("remitos").get_public_url(nombre_archivo)
                                            supabase.table("ordenes_carga").update({
                                                "url_foto": url_publica,
                                                "motivo_sin_foto": "Corregido por Auditoría"
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
                                            
                                            # ==========================================
                                            # 🧹 LIMPIEZA DE MEMORIA BOTON MANUAL
                                            # ==========================================
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
                                                    st.warning(f"⏳ Google (Pro) saturado. Reintentando en {tiempo_espera_manual} seg...")
                                                    time.sleep(tiempo_espera_manual)
                                                    tiempo_espera_manual *= 2 
                                                elif intentos_restantes_manual == 1:
                                                    st.warning(f"⚠️ Google (Pro) sigue caído. Cambiando a modelo Flash (Respaldo)...")
                                                    time.sleep(2) 
                                                else:
                                                    st.error(f"❌ Falló incluso con el modelo de respaldo. Intentá más tarde.")
                                            else:
                                                st.error(f"❌ Falla técnica inesperada: {error_msg_manual}")
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
                                    
                                st.info(f"🛒 **Pedido original del cliente:**\n{texto_pedido_cliente}")
                                st.markdown("---")

                                col_f1, col_f2 = st.columns(2)
                                fac_fecha = col_f1.text_input("Fecha", value=st.session_state.get(f"ia_fec_{fila['id']}", ""))
                                fac_rs = col_f2.text_input("Razón Social", value=st.session_state.get(f"ia_rs_{fila['id']}", ""))
                                
                                col_f3, col_f4 = st.columns(2)
                                fac_imp = col_f3.number_input("Importe ($)", value=st.session_state.get(f"ia_imp_{fila['id']}", 0.0))
                                fac_comp = col_f4.text_input("Nº Factura", value=st.session_state.get(f"ia_fac_{fila['id']}", ""))
                                
                                st.markdown("---")
                                
                                prod_ia_val = st.session_state.get(f"ia_prod_{fila['id']}", "")
                                obs_ia_val = st.session_state.get(f"ia_obs_{fila['id']}", "")
                                
                                if obs_ia_val:
                                    st.warning(f"⚠️ **{obs_ia_val}**")

                                fac_prod = st.text_input("Detalle de Combustibles (Leído por IA)", value=prod_ia_val)
                                fac_obs = st.text_input("Observaciones Adicionales (Leído por IA)", value=obs_ia_val)
                                
                                st.markdown("---")
                                efectivo_real_bd = fila.get('efectivo_entregado') if pd.notna(fila.get('efectivo_entregado')) else fila.get('efectivo_pedido', 0)
                                tiene_foto = pd.notna(fila['url_foto']) and str(fila['url_foto']).strip() != ""
                                lts_def = float(fila['litros_pedidos']) if tiene_foto else None
                                
                                nro_ord_gen, nro_ord_lts, nro_ord_efe = "", "", ""
                                
                                if es_especial:
                                    c_o1, c_o2 = st.columns(2)
                                    fac_lts = c_o1.number_input("Total de Litros", value=st.session_state.get(f"ia_lts_{fila['id']}", lts_def))
                                    nro_ord_lts = c_o2.text_input("Nº Orden Litros", value=fila['nro_orden_litros_interna'] if pd.notna(fila['nro_orden_litros_interna']) else "")
                                    c_o3, c_o4 = st.columns(2)
                                    efectivo_final = c_o3.number_input("Efectivo Entregado", value=float(efectivo_real_bd))
                                    nro_ord_efe = c_o4.text_input("Nº Orden Efectivo", value=fila['nro_orden_efectivo_interna'] if pd.notna(fila['nro_orden_efectivo_interna']) else "")
                                else:
                                    c_o1, c_o2 = st.columns(2)
                                    fac_lts = c_o1.number_input("Total de Litros", value=st.session_state.get(f"ia_lts_{fila['id']}", lts_def))
                                    nro_ord_gen = c_o2.text_input("Nº Orden (Normal)", value=fila['nro_orden_cliente'] if pd.notna(fila['nro_orden_cliente']) else "")
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
                            "estado": "AUDITADO",
                            "litros_reales": litros_totales,
                            "numero_factura": item["Nº Factura"],
                            "monto_factura": importe_total,
                            "producto_ia": texto_productos,
                            "observaciones_ia": texto_obs
                        }).eq("id", id_actual).execute()
                        
                        ordenes_procesadas_db.append(id_actual)
                        
            st.session_state.resumen_para_cliente, st.session_state.agregados_excel = [], []
            st.session_state.pop(f"ia_procesada_{cliente_sel}", None) 
            st.success("¡Lote cerrado exitosamente y guardado en la base de datos!")
            time.sleep(1.5)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# ==========================================
# 5. MÓDULO: VERIFICACIÓN BCRA (100% CLOUD VÍA SCRAPERAPI)
# ==========================================
elif opcion == "Verificación BCRA":
    st.title("🛡️ Verificación Blindada de CUIT")
    st.markdown('<p style="color:#666; font-size:16px;">Consultá el estado crediticio y el historial de cheques rechazados en el BCRA.</p>', unsafe_allow_html=True)
    
    def consultar_bcra_completo(cuit):
        cuit = str(cuit).strip()
        
        # 🔑 TU LLAVE DE ACCESO DE SCRAPERAPI (Reemplazar aquí)
        API_KEY = "cf3ae8aaf0457292c6e2f8983b207139"
        
        # URLs Oficiales del BCRA
        url_deudas = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/{cuit}"
        url_cheques = f"https://api.bcra.gob.ar/centraldedeudores/v1.0/Deudas/ChequesRechazados/{cuit}"
        
        datos_cliente = {
            "situacion": 1,
            "entidad": "Sin Registros",
            "denominacion": "Cliente Desconocido",
            "cheques_rechazados": 0
        }
        
        try:
            import requests
            import time
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # --- 1. SITUACIÓN CREDITICIA ---
            # Configuramos la petición para que pase por el túnel de ScraperAPI
            payload_deudas = {'api_key': API_KEY, 'url': url_deudas, 'render': 'false'}
            res_deuda = requests.get('https://api.scraperapi.com/', params=payload_deudas, timeout=45)
            
            if res_deuda.status_code == 200:
                try:
                    data = res_deuda.json()
                    if data.get('status') == 200 and 'results' in data:
                        res = data['results']
                        datos_cliente['denominacion'] = res.get('denominacion', 'Cliente')
                        
                        periodos = res.get('periodos', [])
                        if periodos and 'entidades' in periodos[0] and periodos[0]['entidades']:
                            entity_info = periodos[0]['entidades'][0]
                            datos_cliente['situacion'] = entity_info.get("situacion", 1)
                            datos_cliente['entidad'] = entity_info.get("entidad", "Entidad Financiera")
                except Exception:
                    pass
            
            time.sleep(1) # Pequeño respiro para la API
            
            # --- 2. CHEQUES RECHAZADOS ---
            payload_cheques = {'api_key': API_KEY, 'url': url_cheques, 'render': 'false'}
            res_cheque = requests.get('https://api.scraperapi.com/', params=payload_cheques, timeout=45)
            
            if res_cheque.status_code == 200:
                try:
                    data_ch = res_cheque.json()
                    status_interno = data_ch.get('status')
                    
                    if status_interno == 200:
                        results_ch = data_ch.get('results', {})
                        total_cheques = 0
                        
                        # Parseo profundo dinámico para contar los cheques reales
                        if isinstance(results_ch, dict):
                            for k, v in results_ch.items():
                                if isinstance(v, list):
                                    for item in v:
                                        if isinstance(item, dict):
                                            sub_listas = [sub_v for sub_k, sub_v in item.items() if isinstance(sub_v, list)]
                                            if sub_listas:
                                                for sub in sub_listas:
                                                    total_cheques += len(sub)
                                            else:
                                                total_cheques += 1
                                        else:
                                            total_cheques += 1
                        elif isinstance(results_ch, list):
                            total_cheques = len(results_ch)
                            
                        datos_cliente['cheques_rechazados'] = total_cheques
                        
                    elif status_interno == 404: # El BCRA confirma 0 cheques
                        datos_cliente['cheques_rechazados'] = 0
                    elif status_interno == 429: # Saturación
                        datos_cliente['cheques_rechazados'] = -429
                    else:
                        datos_cliente['cheques_rechazados'] = -1
                except Exception:
                    datos_cliente['cheques_rechazados'] = -1
            else:
                datos_cliente['cheques_rechazados'] = -1
                
            return datos_cliente
            
        except requests.exceptions.Timeout:
            st.warning("⏱️ Tiempo de espera agotado. El proxy tardó demasiado en responder.")
            return None
        except Exception as e:
            st.error(f"Error de conexión interna: {str(e)}")
            return None

    def guardar_cuit_afectado(cuit, situacion, nombre, observaciones_extra):
        try:
            supabase.table("cuits_afectados").insert({
                "cuit": cuit, 
                "situacion_bcra": situacion,
                "observaciones": f"Titular: {nombre} | {observaciones_extra}"
            }).execute()
        except Exception as e:
            st.error(f"Error guardando en BD local: {e}")

    st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
    cuit_input = st.text_input("Ingresá el CUIT a verificar (solo números)", max_chars=11, placeholder="Ej: 30123456789")

    if st.button("Validar Riesgo Global"):
        if len(cuit_input) != 11 or not cuit_input.isdigit():
            st.error("❌ Por favor, ingresá un CUIT válido de 11 dígitos.")
        else:
            try:
                registro_interno = supabase.table("cuits_afectados").select("*").eq("cuit", cuit_input).execute()
                
                if registro_interno.data:
                    st.error(f"⚠️ ¡ATENCIÓN! Este CUIT ya está en nuestra lista de AFECTADOS.")
                    st.warning(f"Situación registrada anteriormente: Nivel {registro_interno.data[0]['situacion_bcra']}")
                    st.info("No hace falta consultar al BCRA, ya tenemos antecedentes negativos internos.")
                else:
                    with st.spinner('Consultando historial de Deudas y Cheques en el BCRA (Puede demorar unos segundos)...'):
                        datos_bcra = consultar_bcra_completo(cuit_input)
                        
                        if datos_bcra is None:
                            st.warning("El servicio no pudo alcanzar al BCRA. Intentá nuevamente.")
                        else:
                            situacion = datos_bcra['situacion']
                            entidad = datos_bcra['entidad']
                            nombre = datos_bcra['denominacion']
                            cheques_rechazados = datos_bcra['cheques_rechazados']
                            
                            st.markdown(f"**Titular:** {nombre}")
                            
                            col1, col2 = st.columns(2)
                            with col1: 
                                st.metric("Situación Crediticia", f"Nivel {situacion}")
                            with col2: 
                                if cheques_rechazados == -429:
                                    st.warning("⚠️ Límite API (429)")
                                elif cheques_rechazados == -1:
                                    st.warning("⚠️ Error Lectura (Bloqueo WAF)")
                                elif cheques_rechazados > 0:
                                    st.error(f"⚠️ {cheques_rechazados} Cheques Rechazados")
                                else:
                                    st.success("✅ 0 Cheques Rechazados")
                            
                            if cheques_rechazados in [-429, -1]:
                                st.warning("⚠️ No se pudo comprobar el historial de cheques. El proxy de rotación falló, reintentá.")
                            elif situacion == 1 and cheques_rechazados == 0:
                                st.success("✅ Cliente Totalmente Limpio (Situación 1 y sin cheques rebotados). Operación segura.")
                            else:
                                st.error("🚨 RIESGO DETECTADO EN EL BCRA.")
                                motivos = []
                                if situacion > 1:
                                    motivos.append(f"Situación {situacion} en {entidad}")
                                if cheques_rechazados > 0:
                                    motivos.append(f"Tiene {cheques_rechazados} cheques rechazados")
                                
                                msj_final = " | ".join(motivos)
                                st.warning(f"Motivo del bloqueo: {msj_final}")
                                st.warning("El CUIT fue ingresado automáticamente a nuestra lista negra.")
                                guardar_cuit_afectado(cuit_input, situacion, nombre, f"Bloqueo por: {msj_final}")
                                
            except Exception as e:
                st.error(f"Error de sistema: {e}")
    st.markdown('</div>', unsafe_allow_html=True)
