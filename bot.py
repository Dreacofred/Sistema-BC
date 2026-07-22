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
# 4. PANTALLA PRINCIPAL: AUDITORÍA (Izq: Botones / Der: Tabla)
# ==========================================
if lote_seleccionado != "--- Elegí un cliente ---":
    st.subheader(f"Auditoría en curso: Lote {lote_seleccionado}")
    
    # Filtramos solo los datos del lote seleccionado
    df_lote = df_general[df_general['cliente_asociado'] == lote_seleccionado].copy()

    # Dividimos la pantalla: 1/5 de espacio para los botones, 4/5 para la tabla
    col_izq, col_der = st.columns([1, 4])

    with col_izq:
        st.write("📁 **Archivos del Lote**")
        
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

        # Creamos la lista vertical de botones que abren en pestaña nueva
        if urls_limpias:
            for i, url in enumerate(urls_limpias):
                st.link_button(f"📄 Abrir Archivo {i+1}", url, use_container_width=True)
        else:
            st.warning("No hay archivos adjuntos.")

    with col_der:
        st.write("📊 **Datos Extraídos por IA (Editables)**")
        
        columnas_visibles = [
            'id', 'numero_identificador', 'monto', 'fecha_emision', 
            'fecha_pago', 'codigo_banco', 'codigo_sucursal', 
            'numero_cuenta', 'cuit_emisor', 'razon_social_emisor'
        ]
        
        # Mostramos la tabla gigante editable (todo de un saque)
        datos_editados = st.data_editor(
            df_lote[columnas_visibles],
            hide_index=True,
            use_container_width=True,
            disabled=["id"]
        )
        
        st.divider()
        
        # Botonera de guardado y exportación al final de la tabla
        suma_cheques = datos_editados['monto'].sum()
        st.metric("Suma Total de Cheques", f"${suma_cheques:,.2f}")
        
        if st.button("✅ Aprobar Lote Completo y Generar Excel", type="primary", use_container_width=True):
            with st.spinner("Guardando auditoría..."):
                try:
                    # 1. Actualizamos Supabase fila por fila
                    for index, fila in datos_editados.iterrows():
                        fila_dict = fila.to_dict()
                        id_fila = fila_dict.pop('id', None)
                        
                        # Saltamos filas vacías sin ID
                        if pd.isna(id_fila) or str(id_fila).strip() in ["None", "<NA>", ""]:
                            continue
                            
                        # Limpiamos los "None" traicioneros
                        for key, value in fila_dict.items():
                            if pd.isna(value) or str(value).strip() in ["None", "<NA>", ""]:
                                fila_dict[key] = None
                                
                        # Le clavamos el sello de Auditado
                        fila_dict['estado_auditoria'] = 'Auditado'
                        supabase.table("cobranzas_pendientes").update(fila_dict).eq("id", id_fila).execute()
                    
                    st.success("🎉 ¡Lote auditado y guardado con éxito!")
                    
                    # 2. Generamos el Excel para Regente
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
                    
                    # Limpiamos caché para que desaparezca del menú
                    st.cache_data.clear()
                    
                except Exception as e:
                    st.error(f"Error al procesar: {e}")
