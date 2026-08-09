# ESTE BOT ES EL QUE MANEJA LA AUDITORIA DE LOS COMPROBANTES QUE ESTAN PENDIENTES DE AUDITAR
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import time

# ==========================================
# 1. CREDENCIALES
# ==========================================
URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL_SB, KEY_SB)

st.title("🏢 Auditoría de Comprobantes - BC Combustibles")
st.markdown("---")

# ==========================================
# 2. TRAER LOTES PENDIENTES
# ==========================================
@st.cache_data(ttl=10)
def obtener_datos():
    respuesta = supabase.table("cobranzas_pendientes").select("*").execute()
    return respuesta.data

datos_db = obtener_datos()
df_completo = pd.DataFrame(datos_db)

if df_completo.empty or not (df_completo['estado_auditoria'] == 'Pendiente').any():
    st.success("🎉 ¡Bandeja limpia! No hay comprobantes pendientes de auditoría en este momento.")
    st.stop()

# Solo trabajamos con los pendientes
df_pendientes = df_completo[df_completo['estado_auditoria'] == 'Pendiente'].copy()
lotes_disponibles = df_pendientes['cliente_asociado'].unique().tolist()

# ==========================================
# 3. VARIABLES DE MEMORIA
# ==========================================
if 'cheques_listos' not in st.session_state:
    st.session_state.cheques_listos = []
if 'datos_corregidos' not in st.session_state:
    st.session_state.datos_corregidos = {}

# ==========================================
# 4. SELECTOR DE LOTE
# ==========================================
st.subheader("📥 Bandeja de Pendientes")
cliente_sel = st.selectbox("Seleccioná un cliente para auditar su lote:", ["--- Elegí un cliente ---"] + lotes_disponibles)

if st.button("🔄 Actualizar Bandeja"):
    st.cache_data.clear()
    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 5. PANTALLA DE AUDITORÍA (ESTILO ACORDEÓN)
# ==========================================
if cliente_sel != "--- Elegí un cliente ---":
    df_lote = df_pendientes[df_pendientes['cliente_asociado'] == cliente_sel].copy()

    st.markdown(f"### 📋 Revisión de Comprobantes: {cliente_sel}")

    for index, fila in df_lote.iterrows():
        cid = fila['id']
        ya_listo = cid in st.session_state.cheques_listos

        # Icono dinámico según si ya lo guardamos en memoria
        icono = "✅ LISTO" if ya_listo else "🟠 PENDIENTE"

        # Mostramos los datos actualizados si ya se corrigieron, sino los de la base
        monto_display = st.session_state.datos_corregidos.get(cid, {}).get('monto', fila.get('monto', 0))
        nro_display = st.session_state.datos_corregidos.get(cid, {}).get('numero_identificador', fila.get('numero_identificador', 'S/N'))
        tipo_display = fila.get('tipo_comprobante') or 'Comprobante'
        if not nro_display or str(nro_display).strip() == "":
            nro_display = "S/N"

        # ACORDEÓN EXPANDIBLE
        with st.expander(f"{icono} | {tipo_display} Nº {nro_display} | Monto: ${float(monto_display or 0):,.2f}"):

            # ACÁ ESTÁ LA MAGIA: 1 de ancho para el form, 1.8 para la imagen (casi el doble de tamaño)
            col_datos, col_img = st.columns([1, 1.8])

            # --- MITAD DERECHA: IMAGEN GIGANTE ---
            with col_img:
                url_activa = str(fila['archivo_url']).split(',')[0].strip() if pd.notna(fila['archivo_url']) else ""

                if url_activa.startswith('http'):
                    if ".pdf" in url_activa.lower():
                        visor_url = f"https://docs.google.com/gview?url={url_activa}&embedded=true"
                        st.markdown(f'<iframe src="{visor_url}" width="100%" height="600" frameborder="0"></iframe>', unsafe_allow_html=True)
                        st.link_button("📄 Abrir PDF en pestaña grande", url_activa)
                    else:
                        st.image(url_activa, use_container_width=True)
                        st.link_button("🖼️ Ver imagen original", url_activa)
                else:
                    st.warning("Este comprobante no tiene imagen adjunta.")

            # --- MITAD IZQUIERDA: FORMULARIO ESTILO LISTA ---
            with col_datos:
                if ya_listo:
                    st.success("✔️ Fila revisada y guardada temporalmente.")
                    if st.button("✏️ Editar nuevamente", key=f"btn_edit_{cid}"):
                        st.session_state.cheques_listos.remove(cid)
                        st.rerun()
                else:
                    with st.form(f"form_cheque_{cid}"):
                        st.markdown("📝 **Completá o corregí:**")

                        # Función que crea la estructura: Texto a la Izq, Caja a la Der
                        def crear_campo(etiqueta, valor, tipo="texto"):
                            c_lbl, c_inp = st.columns([1, 1.5])
                            c_lbl.markdown(f"<div style='margin-top: 8px; font-size: 14px;'>{etiqueta}</div>", unsafe_allow_html=True)
                            if tipo == "numero":
                                return c_inp.number_input(etiqueta, value=float(valor or 0.0), label_visibility="collapsed")
                            else:
                                return c_inp.text_input(etiqueta, value=str(valor), label_visibility="collapsed")

                        f_nro = crear_campo("Nº Comprobante", fila.get('numero_identificador', ''))
                        f_monto = crear_campo("Monto ($)", fila.get('monto', 0.0), tipo="numero")
                        f_emi = crear_campo("Emisión", fila.get('fecha_emision', ''))
                        f_pago = crear_campo("Vencimiento", fila.get('fecha_pago', ''))
                        f_banco = crear_campo("Cód. Banco", fila.get('codigo_banco', ''))
                        f_sucursal = crear_campo("Cód. Sucursal", fila.get('codigo_sucursal', ''))
                        f_cuenta = crear_campo("Nº Cuenta", fila.get('numero_cuenta', ''))
                        f_cuit = crear_campo("CUIT Emisor", fila.get('cuit_emisor', ''))
                        f_rs = crear_campo("Razón Social", fila.get('razon_social_emisor', ''))

                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.form_submit_button("✅ Guardar Fila", type="primary", use_container_width=True):
                            # Guardamos los cambios en la memoria temporal
                            st.session_state.datos_corregidos[cid] = {
                                'numero_identificador': f_nro.strip(),
                                'monto': f_monto,
                                'fecha_emision': f_emi.strip(),
                                'fecha_pago': f_pago.strip(),
                                'codigo_banco': f_banco.strip(),
                                'codigo_sucursal': f_sucursal.strip(),
                                'numero_cuenta': f_cuenta.strip(),
                                'cuit_emisor': f_cuit.strip(),
                                'razon_social_emisor': f_rs.strip(),
                                'estado_auditoria': 'Auditado'
                            }
                            st.session_state.cheques_listos.append(cid)
                            st.rerun()

    # ==========================================
    # 6. CIERRE Y EXPORTACIÓN DEL LOTE
    # ==========================================
    st.markdown("<br><hr>", unsafe_allow_html=True)
    faltantes = len(df_lote) - len(st.session_state.cheques_listos)

    if faltantes > 0:
        st.info(f"⚠️ Faltan revisar {faltantes} comprobante(s) para poder exportar y cerrar el lote.")
    else:
        st.success("🎉 ¡Excelente! Todos los comprobantes de este lote fueron revisados.")
        st.markdown("### 🚀 Exportación a Regente")

        # Armamos la tabla final para exportar
        filas_export = []
        suma_total = 0
        for cid in df_lote['id']:
            d = st.session_state.datos_corregidos[cid]
            suma_total += d['monto']
            filas_export.append({
                "Titular": d['razon_social_emisor'],
                "Emision": d['fecha_emision'],
                "Venc.": d['fecha_pago'],
                "Nro": d['numero_identificador'],
                "Bco.": d['codigo_banco'],
                "NCta.": d['numero_cuenta'],
                "Plaza": d['codigo_sucursal'],
                "Monto": d['monto']
            })

        df_regente = pd.DataFrame(filas_export)
        st.metric("Suma Total Auditada", f"${suma_total:,.2f}")

        col_ex1, col_ex2 = st.columns(2)

        # Botón de descarga
        csv_data = df_regente.to_csv(index=False).encode('utf-8')
        col_ex1.download_button(
            label="⬇️ 1. Descargar Archivo para Regente",
            data=csv_data,
            file_name=f"importacion_regente_{cliente_sel.replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True
        )

        # Cierre en base de datos
        st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
        confirmar = col_ex2.checkbox("Confirmo que ya descargué el archivo CSV")
        if col_ex2.button("✅ 2. CERRAR LOTE EN BASE DE DATOS", disabled=not confirmar, type="primary", use_container_width=True):
            with st.spinner("Guardando en la nube..."):
                try:
                    # Impactamos cada cheque corregido en Supabase
                    for cid in st.session_state.cheques_listos:
                        datos_finales = st.session_state.datos_corregidos[cid].copy()
                        # Limpieza de vacíos para SQL
                        for key, value in datos_finales.items():
                            if pd.isna(value) or str(value).strip() in ["None", "<NA>", ""]:
                                datos_finales[key] = None

                        supabase.table("cobranzas_pendientes").update(datos_finales).eq("id", cid).execute()

                    st.success("¡Lote cerrado y limpiado de la bandeja con éxito!")

                    # Limpiamos la memoria para el próximo lote
                    st.session_state.cheques_listos = []
                    st.session_state.datos_corregidos = {}
                    time.sleep(1.5)
                    st.cache_data.clear()
                    st.rerun()

                except Exception as e:
                    st.error(f"Error al guardar: {e}")
        st.markdown("</div>", unsafe_allow_html=True)
