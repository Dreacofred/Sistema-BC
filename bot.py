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
# 2. TRAER LOTES PENDIENTES DE SUPABASE
# ==========================================
@st.cache_data(ttl=10) # Se actualiza cada 10 segundos
def obtener_pendientes():
    respuesta = supabase.table("cobranzas_pendientes").select("*").eq("estado_auditoria", "Pendiente").execute()
    return respuesta.data

datos_pendientes = obtener_pendientes()

if not datos_pendientes:
    st.success("🎉 ¡Bandeja limpia! No hay lotes pendientes de auditoría en este momento.")
    st.stop()

# Agrupar los cheques por Cliente para armar la "Bandeja de Entrada"
df_pendientes = pd.DataFrame(datos_pendientes)
lotes_disponibles = df_pendientes['cliente_asociado'].unique().tolist()

# ==========================================
# 3. BARRA LATERAL: LA BANDEJA DE ENTRADA
# ==========================================
with st.sidebar:
    st.header("📥 Bandeja de Pendientes")
    st.info("Seleccioná un lote para auditar:")
    
    # Selector de lote
    lote_seleccionado = st.radio(
        "Lotes esperando revisión:",
        lotes_disponibles,
        format_func=lambda x: f"🔴 Lote: {x}"
    )
    
    if st.button("🔄 Actualizar Bandeja"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 4. PANTALLA PRINCIPAL: AUDITORÍA (Dividida)
# ==========================================
if lote_seleccionado:
    st.subheader(f"Auditoría en curso: Lote {lote_seleccionado}")
    
    # Filtramos solo los datos del lote seleccionado
    df_lote = df_pendientes[df_pendientes['cliente_asociado'] == lote_seleccionado].copy()
    
    # Dividimos la pantalla: Izquierda (Fotos) | Derecha (Grilla IA)
    col_fotos, col_grilla = st.columns([1, 1.5])
    
    with col_fotos:
        st.write("📸 **Imágenes del Lote**")
        
        # 1. Extraemos lo que hay en la base de datos
        urls_crudas = df_lote['archivo_url'].dropna().unique().tolist()
        
        urls_limpias = []
        # 2. El "Colador": limpiamos y separamos por si hay varias URLs juntas
        for url_str in urls_crudas:
            if isinstance(url_str, str):
                # Separamos por coma y limpiamos espacios
                for u in url_str.split(','):
                    u_limpia = u.strip()
                    # Solo guardamos si realmente es un link web
                    if u_limpia.startswith('http'):
                        urls_limpias.append(u_limpia)
                        
        # 3. Quitamos posibles fotos duplicadas
        urls_limpias = list(set(urls_limpias))

        if urls_limpias:
            with st.container(height=600): # Caja con scroll para las fotos
                for url in urls_limpias:
                    try:
                        st.image(url, use_column_width=True)
                        st.divider()
                    except Exception as e:
                        st.error(f"Error al cargar una de las imágenes.")
        else:
            st.warning("Este lote no tiene imágenes válidas adjuntas (o el bot aún no las subió).")        
    with col_grilla:
        st.write("📊 **Datos Extraídos por IA (Editables)**")
        
        # Preparamos las columnas que la administración realmente necesita ver/editar
        columnas_visibles = [
            'id', 'numero_identificador', 'monto', 'fecha_emision', 
            'fecha_pago', 'codigo_banco', 'codigo_sucursal', 
            'numero_cuenta', 'cuit_emisor', 'razon_social_emisor'
        ]
        
        # Mostramos la grilla editable
        df_mostrar = df_lote[columnas_visibles].copy()
        datos_editados = st.data_editor(
            df_mostrar,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            disabled=["id"] # Bloqueamos el ID para que no lo rompan sin querer
        )
        
        st.write("---")
        st.write("### 🚦 Semáforo y Exportación")
        suma_cheques = datos_editados['monto'].sum()
        st.metric("Suma Total de Cheques Auditados", f"${suma_cheques:,.2f}")
        
        if st.button("✅ Aprobar Lote y Generar Excel", type="primary"):
            with st.spinner("Guardando auditoría y generando archivo..."):
                try:
                    # 1. Actualizamos Supabase fila por fila con las correcciones
                    for index, fila in datos_editados.iterrows():
                        fila_dict = fila.to_dict()
                        
                        # Extraemos el ID y lo sacamos de la lista de datos a actualizar
                        id_fila = fila_dict.pop('id', None)
                        
                        # Si el ID es inválido (ej: se agregó una fila vacía por accidente), la saltamos
                        if pd.isna(id_fila) or str(id_fila).strip() in ["None", "<NA>", ""]:
                            continue
                            
                        # Limpieza extrema: Reemplazamos textos basura de Streamlit por vacíos reales (NULL en SQL)
                        for key, value in fila_dict.items():
                            if pd.isna(value) or str(value).strip() in ["None", "<NA>", ""]:
                                fila_dict[key] = None
                                
                        # Le clavamos el sello de Auditado
                        fila_dict['estado_auditoria'] = 'Auditado'
                        
                        # Actualizamos en la base de datos usando el ID limpio
                        supabase.table("cobranzas_pendientes").update(fila_dict).eq("id", id_fila).execute()
                    
                    st.success("🎉 ¡Base de datos actualizada con éxito! El lote ya no está pendiente.")
                    
                    # 2. Generamos el Excel mapeado para Regente
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
                    )
                    
                    st.info("👆 Clic en el botón para descargar. (Refrescá la página para seguir con el próximo lote).")
                    
                except Exception as e:
                    st.error(f"Error al guardar la auditoría: {e}")
