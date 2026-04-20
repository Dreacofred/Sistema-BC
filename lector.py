import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image
import pandas as pd # Agregamos esto para manejar tablas
import json

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Sistema BC Combustibles", layout="wide")

# --- MEMORIA DEL SISTEMA (Session State) ---
if 'resumen_ventas' not in st.session_state:
    st.session_state.resumen_ventas = []

# --- BARRA LATERAL ---
st.sidebar.title("Menú Principal")
opcion = st.sidebar.radio("Tarea:", ["Facturas de Proveedores", "Ventas a Camiones"])

cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# SECCIÓN 1: PROVEEDORES (Igual que antes)
if opcion == "Facturas de Proveedores":
    st.title("📄 Facturas de Proveedores")
    archivo = st.file_uploader("Subir factura", type=["pdf", "png", "jpg"], key="prov")
    if archivo and st.button("Procesar"):
        # ... (aquí va tu lógica de proveedores que ya funciona) ...
        st.write("Procesando...")

# SECCIÓN 2: VENTAS A CAMIONES (Con Memoria)
elif opcion == "Ventas a Camiones":
    st.title("🚛 Resumen de Carga para Clientes")
    
    col1, col2 = st.columns(2)
    with col1:
        f_factura = st.file_uploader("Foto Factura", type=["jpg", "png"], key="f1")
    with col2:
        f_orden = st.file_uploader("Foto Orden Manual", type=["jpg", "png"], key="f2")

    if f_factura and f_orden:
        if st.button("🔍 Analizar Par de Fotos"):
            with st.spinner("La IA está cruzando datos..."):
                img1 = Image.open(f_factura)
                img2 = Image.open(f_orden)
                
                instruccion = "Sos un experto administrativo. Leé la factura y el papel manuscrito. Extraé: fecha, chofer, cliente, litros, total factura, nro factura y nro orden. Devolveme SOLO un JSON puro."
                
                res = cliente.models.generate_content(model='gemini-2.0-flash', contents=[instruccion, img1, img2])
                
                try:
                    # Limpiamos la respuesta por si la IA pone texto extra
                    limpio = res.text.replace("```json", "").replace("```", "").strip()
                    datos = json.loads(limpio)
                    
                    # Guardamos en la memoria
                    st.session_state.resumen_ventas.append(datos)
                    st.success("¡Venta agregada al resumen!")
                except:
                    st.error("Error al leer los datos. Asegurate que las fotos sean claras.")

    # --- MOSTRAR LA TABLA ACUMULADA ---
    if st.session_state.resumen_ventas:
        st.divider()
        st.subheader("📋 Resumen Acumulado del Día")
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.dataframe(df, use_container_width=True)

        # Botones de acción
        col_a, col_b = st.columns(2)
        with col_a:
            # Convertimos a CSV para que Nancy lo abra en Excel
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar Excel (CSV)", data=csv, file_name="resumen_carga.csv", mime="text/csv")
        
        with col_b:
            if st.button("🗑️ Borrar todo y empezar de nuevo"):
                st.session_state.resumen_ventas = []
                st.rerun()
