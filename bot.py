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
@st.cache_data(ttl=10) # Se actualiza cada 10 segundos
def obtener_datos():
    # Traemos todos los datos de la base
    respuesta = supabase.table("cobranzas_pendientes").select("*").execute()
    return respuesta.data

datos_db = obtener_datos()
df_completo = pd.DataFrame(datos_db)

# Verificamos si hay ALGO pendiente en toda la base
if df_completo.empty or not (df_completo['estado_auditoria'] == 'Pendiente').any():
    st.success("🎉 ¡Bandeja limpia! No hay lotes pendientes de auditoría en este momento.")
    st.stop()

# --- EL FILTRO MÁGICO ---
# 1. Buscamos los IDs de los Lotes (envíos) que tienen al menos un cheque pendiente
ids_lotes_activos = df_completo[df_completo['estado_auditoria'] == 'Pendiente']['lote_id'].unique()

# 2. Recortamos la tabla general para que SOLO muestre los cheques de esos envíos puntuales
df_general = df_completo[df_completo['lote_id'].isin(ids_lotes_activos)].copy()

# Armamos la lista del desplegable
lotes_disponibles = df_general['cliente_asociado'].unique().tolist()

# ==========================================
# 3. BANDEJA DE ENTRADA (EN PANTALLA PRINCIPAL)
# ==========================================
st.subheader("📥 Bandeja de Pendientes")

# Armamos la lista con una opción vacía al principio
opciones_desplegable = ["--- Elegí un cliente ---"] + lotes_disponibles

# Menú desplegable en el centro de la pantalla
lote_seleccionado = st.selectbox(
    "Seleccioná un lote para auditar:",
    opciones_desplegable
)

if st.button("🔄 Actualizar Bandeja"):
    st.cache_data.clear()
    st.rerun()

st.markdown("---")

# ==========================================
# 4. PANTALLA PRINCIPAL: AUDITORÍA (Maestro/Detalle)
# ==========================================
if lote_seleccionado != "--- Elegí un cliente ---":
    st.subheader(f"Auditoría en curso: Lote {lote_seleccionado}")
    
    # Filtramos solo los datos del lote seleccionado
    df_lote = df_general[df_general['cliente_asociado'] == lote_seleccionado].copy()

    # ¡Acá definimos las columnas para que la tabla las entienda!
    columnas_visibles = [
        'id', 'numero_identificador', 'monto', 'fecha_emision', 
        'fecha_pago', 'codigo_banco', 'codigo_sucursal', 
        'numero_cuenta', 'cuit_emisor', 'razon_social_emisor'
    ]

    # --- 1. TABLA GENERAL (A TODO EL ANCHO) ---
    st.write("📊 **Resumen del Lote (Vista General)**")
    
    # Función para pintar la fila de verde si ya está auditada
    def pintar_verde(fila):
        if fila.get('estado_auditoria') == 'Auditado':
            return ['background-color: #c3e6cb; color: #155724'] * len(fila)
        return [''] * len(fila)

    # Mostramos la tabla bloqueada (solo lectura) pero pintada
    st.dataframe(
        df_lote[columnas_visibles].style.apply(pintar_verde, axis=1),
        use_container_width=True,
        hide_index=True
    )
    
    st.divider()

    # --- 2. ZONA DE AUDITORÍA INDIVIDUAL ---
    st.subheader("🔍 Estación de Revisión")
    
    # Armamos la lista para el desplegable con un tilde si ya está listo
    opciones_cheques = ["--- Elegí un comprobante ---"]
    for _, fila in df_lote.iterrows():
        icono = "✅" if fila.get('estado_auditoria') == 'Auditado' else "⏳"
        opciones_cheques.append(f"{icono} Cheque N° {fila.get('numero_identificador', 'S/N')} | Monto: ${fila.get('monto', 0)} | ID: {fila['id']}")

    cheque_sel = st.selectbox("Seleccioná un comprobante para auditar y ver su imagen:", opciones_cheques)

    if cheque_sel != "--- Elegí un comprobante ---":
        # Extraemos el ID del final del texto (después de 'ID: ')
        id_seleccionado = cheque_sel.split("ID: ")[1]
        df_fila = df_lote[df_lote['id'] == id_seleccionado].copy()

        # --- A. EDITOR DE LA FILA ---
        st.write("📝 **Datos extraídos (Corregí acá si la IA se equivocó)**")
        fila_editada = st.data_editor(df_fila[columnas_visibles], hide_index=True, use_container_width=True, disabled=["id"])
        
        # --- B. BOTÓN DE CONFIRMACIÓN ---
        if st.button("✅ Confirmar y Marcar como OK", use_container_width=True):
            datos_nuevos = fila_editada.iloc[0].to_dict()
            datos_nuevos['estado_auditoria'] = 'Auditado' # Le cambiamos el estado
            
            # Limpieza de valores nulos o vacíos antes de guardar
            for key, value in datos_nuevos.items():
                if pd.isna(value) or str(value).strip() in ["None", "<NA>", ""]:
                    datos_nuevos[key] = None

            # Actualizamos en Supabase
            supabase.table("cobranzas_pendientes").update(datos_nuevos).eq("id", id_seleccionado).execute()
            
            # Avisamos, limpiamos la memoria caché y recargamos la página para que se pinte de verde
            st.success("¡Comprobante auditado correctamente!")
            st.cache_data.clear() 
            time.sleep(1)
            st.rerun()

        st.write("---")
        
        # --- C. VISOR DE ARCHIVOS DEL LOTE ---
        st.write("📸 **Documentos Adjuntos**")
        urls_crudas = df_fila['archivo_url'].dropna().unique().tolist()
        
        urls_limpias = []
        for url_str in urls_crudas:
            if isinstance(url_str, str):
                for u in url_str.split(','):
                    u_limpia = u.strip()
                    if u_limpia.startswith('http'):
                        urls_limpias.append(u_limpia)
                        
        urls_limpias = list(dict.fromkeys(urls_limpias))

        if urls_limpias:
            opciones = [f"Archivo {i+1}" for i in range(len(urls_limpias))]
            seleccion = st.radio("Navegar por las imágenes del lote:", opciones, horizontal=True, label_visibility="collapsed")
            indice = opciones.index(seleccion)
            url_activa = urls_limpias[indice]
            
            try:
                if ".pdf" in url_activa.lower():
                    visor_url = f"https://docs.google.com/gview?url={url_activa}&embedded=true"
                    mostrar_pdf = f'<iframe src="{visor_url}" width="100%" height="600" frameborder="0"></iframe>'
                    st.markdown(mostrar_pdf, unsafe_allow_html=True)
                    st.link_button("📄 Abrir PDF en otra pestaña", url_activa)
                else:
                    st.image(url_activa, use_container_width=True)
            except Exception as e:
                st.error(f"Error al cargar el archivo.")
        else:
            st.warning("Este lote no tiene imágenes adjuntas.")
            
    st.divider()
    
    # --- 3. EXPORTACIÓN DEL LOTE COMPLETO ---
    st.write("### 🚀 Exportación a Regente")
    suma_cheques = df_lote['monto'].sum()
    st.metric("Suma Total de Cheques del Lote", f"${suma_cheques:,.2f}")
    
    # Verificamos si falta alguno por auditar
    pendientes = df_lote[df_lote['estado_auditoria'] != 'Auditado']
    
    if not pendientes.empty:
        st.warning(f"⚠️ Faltan auditar {len(pendientes)} comprobantes para poder generar el Excel de este lote.")
    else:
        if st.button("💾 Generar Excel para Regente", type="primary", use_container_width=True):
            try:
                # Generamos el Excel mapeado para Regente con todos los cheques del lote
                df_regente = pd.DataFrame({
                    "Titular": df_lote["razon_social_emisor"],
                    "Emision": df_lote["fecha_emision"],
                    "Venc.": df_lote["fecha_pago"],
                    "Nro": df_lote["numero_identificador"],
                    "Bco.": df_lote["codigo_banco"],
                    "NCta.": df_lote["numero_cuenta"],
                    "Plaza": df_lote["codigo_sucursal"],
                    "Monto": df_lote["monto"]
                })
                
                csv_data = df_regente.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="⬇️ Descargar Archivo",
                    data=csv_data,
                    file_name=f"importacion_regente_{lote_seleccionado.replace(' ', '_')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                st.info("👆 Clic en el botón para descargar. Luego actualizá la bandeja para seguir con el próximo lote.")
                
            except Exception as e:
                st.error(f"Error al generar el archivo: {e}")
