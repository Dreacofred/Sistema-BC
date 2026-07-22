import streamlit as st
import pandas as pd
from supabase import create_client, Client
import time

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA Y CREDENCIALES
# ==========================================
st.set_page_config(page_title="Auditoría SICE", layout="wide")

URL_SB = st.secrets["SUPABASE_URL"]
KEY_SB = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL_SB, KEY_SB)

st.title("🏢 Centro de Auditoría - BC Combustibles")
st.markdown("Revisá los lotes enviados desde la pista, validá la lectura de la IA y exportá a Regente.")
st.markdown("---")

# ==========================================
# 2. TRAER LOTES DE SUPABASE
# ==========================================
@st.cache_data(ttl=10)
def obtener_datos():
    respuesta = supabase.table("cobranzas_pendientes").select("*").execute()
    return respuesta.data

datos_db = obtener_datos()
df_completo = pd.DataFrame(datos_db)

# Verificamos si hay ALGO pendiente en toda la base
if df_completo.empty or not (df_completo['estado_auditoria'] == 'Pendiente').any():
    st.success("🎉 ¡Bandeja limpia! No hay lotes pendientes de auditoría en este momento.")
    st.stop()

# --- EL FILTRO MÁGICO ---
ids_lotes_activos = df_completo[df_completo['estado_auditoria'] == 'Pendiente']['lote_id'].unique()
df_general = df_completo[df_completo['lote_id'].isin(ids_lotes_activos)].copy()
lotes_disponibles = df_general['cliente_asociado'].unique().tolist()

# ==========================================
# 3. BANDEJA DE ENTRADA
# ==========================================
st.subheader("📥 Bandeja de Pendientes")
opciones_desplegable = ["--- Elegí un cliente ---"] + lotes_disponibles
lote_seleccionado = st.selectbox("Seleccioná un lote para auditar:", opciones_desplegable)

if st.button("🔄 Actualizar Bandeja"):
    st.cache_data.clear()
    st.rerun()

st.markdown("---")

# ==========================================
# 4. PANTALLA PRINCIPAL: CARRUSEL Y TABLA
# ==========================================
if lote_seleccionado != "--- Elegí un cliente ---":
    st.subheader(f"Auditoría en curso: Lote {lote_seleccionado}")
    
    df_lote = df_general[df_general['cliente_asociado'] == lote_seleccionado].copy()

    # Extraemos y limpiamos las URLs de la base de datos
    urls_crudas = df_lote['archivo_url'].dropna().unique().tolist()
    urls_limpias = []
    for url_str in urls_crudas:
        if isinstance(url_str, str):
            for u in url_str.split(','):
                u_limpia = u.strip()
                if u_limpia.startswith('http'):
                    urls_limpias.append(u_limpia)
    urls_limpias = list(dict.fromkeys(urls_limpias))

    # --- MEMORIA DEL CARRUSEL ---
    # Si cambiamos de cliente o entramos por primera vez, reseteamos la foto a la número 0
    if 'lote_actual' not in st.session_state or st.session_state.lote_actual != lote_seleccionado:
        st.session_state.lote_actual = lote_seleccionado
        st.session_state.foto_index = 0

    # Dividimos la pantalla mitad y mitad para tener un buen tamaño de lectura
    col_izq, col_der = st.columns([1, 1])

    with col_izq:
        st.write("📸 **Visor de Archivos**")
        
        if urls_limpias:
            # --- BOTONERA DE NAVEGACIÓN ---
            col_btn_izq, col_contador, col_btn_der = st.columns([1, 2, 1])
            
            with col_btn_izq:
                # Botón Anterior (solo funciona si no estamos en la primera foto)
                if st.button("⬅️ Anterior", use_container_width=True):
                    if st.session_state.foto_index > 0:
                        st.session_state.foto_index -= 1
                        st.rerun()
                        
            with col_contador:
                # Texto central que indica por dónde vamos
                st.markdown(f"<h5 style='text-align: center;'>Archivo {st.session_state.foto_index + 1} de {len(urls_limpias)}</h5>", unsafe_allow_html=True)
                
            with col_btn_der:
                # Botón Siguiente (solo funciona si no estamos en la última foto)
                if st.button("Siguiente ➡️", use_container_width=True):
                    if st.session_state.foto_index < len(urls_limpias) - 1:
                        st.session_state.foto_index += 1
                        st.rerun()

            # --- MOSTRAR LA IMAGEN O PDF ACTIVO ---
            url_activa = urls_limpias[st.session_state.foto_index]
            
            try:
                if ".pdf" in url_activa.lower():
                    visor_url = f"https://docs.google.com/gview?url={url_activa}&embedded=true"
                    mostrar_pdf = f'<iframe src="{visor_url}" width="100%" height="600" frameborder="0"></iframe>'
                    st.markdown(mostrar_pdf, unsafe_allow_html=True)
                    st.link_button("📄 Abrir PDF en pestaña gigante", url_activa)
                else:
                    st.image(url_activa, use_container_width=True)
                    st.link_button("🖼️ Ver imagen en tamaño completo", url_activa)
            except Exception:
                st.error("Error al cargar el archivo.")
        else:
            st.warning("No hay archivos adjuntos.")

    with col_der:
        st.write("📊 **Datos Extraídos por IA (Editables)**")
        
        columnas_visibles = [
            'id', 'numero_identificador', 'monto', 'fecha_emision', 
            'fecha_pago', 'codigo_banco', 'codigo_sucursal', 
            'numero_cuenta', 'cuit_emisor', 'razon_social_emisor'
        ]
        
        # Mostramos la tabla editable
        datos_editados = st.data_editor(
            df_lote[columnas_visibles],
            hide_index=True,
            use_container_width=True,
            disabled=["id"],
            height=650 # Le damos la misma altura que el visor de fotos
        )
        
        st.divider()
        
        suma_cheques = datos_editados['monto'].sum()
        st.metric("Suma Total de Cheques", f"${suma_cheques:,.2f}")
        
        if st.button("✅ Aprobar Lote Completo y Generar Excel", type="primary", use_container_width=True):
            with st.spinner("Guardando auditoría..."):
                try:
                    for index, fila in datos_editados.iterrows():
                        fila_dict = fila.to_dict()
                        id_fila = fila_dict.pop('id', None)
                        
                        if pd.isna(id_fila) or str(id_fila).strip() in ["None", "<NA>", ""]:
                            continue
                            
                        for key, value in fila_dict.items():
                            if pd.isna(value) or str(value).strip() in ["None", "<NA>", ""]:
                                fila_dict[key] = None
                                
                        fila_dict['estado_auditoria'] = 'Auditado'
                        supabase.table("cobranzas_pendientes").update(fila_dict).eq("id", id_fila).execute()
                    
                    st.success("🎉 ¡Lote auditado y guardado con éxito!")
                    
                    df_regente = pd.DataFrame({
                        "Titular": datos_editados.get("razon_social_emisor", ""),
                        "Emision": datos_editados.get("fecha_emision", ""),
                        "Venc.": datos_editados.get("fecha_pago", ""),
                        "Nro": datos_editados.get("numero_identificador", ""),
                        "Bco.": datos_editados.get("codigo_banco", ""),
                        "NCta.": datos_editados.get("numero_cuenta", ""),
                        "Plaza": datos_editados.get("codigo_sucursal", ""),
                        "Monto": datos_editados.get("monto", 0.0)
                    })
                    
                    csv_data = df_regente.to_csv(index=False).encode('utf-8')
                    
                    st.download_button(
                        label="⬇️ Descargar Archivo para Regente",
                        data=csv_data,
                        file_name=f"importacion_regente_{lote_seleccionado.replace(' ', '_')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    st.cache_data.clear()
                    
                except Exception as e:
                    st.error(f"Error al procesar: {e}")
