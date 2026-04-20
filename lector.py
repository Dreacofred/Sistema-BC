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

# SECCIÓN 2: VENTAS A CAMIONES (Con Memoria y Orden Opcional)
elif opcion == "Ventas a Camiones":
    st.title("🚛 Resumen de Carga para Clientes")
    
    col1, col2 = st.columns(2)
    with col1:
        f_factura = st.file_uploader("1. Foto Factura (Obligatorio)", type=["jpg", "png", "jpeg"], key="f1")
    with col2:
        f_orden = st.file_uploader("2. Foto Orden Manual (Opcional)", type=["jpg", "png", "jpeg"], key="f2")

    # Ahora solo exigimos que f_factura esté cargada
    if f_factura:
        if st.button("🔍 Analizar Venta", use_container_width=True):
            with st.spinner("La IA está leyendo los datos..."):
                try:
                    img_factura = Image.open(f_factura)
                    
                    # Preparamos la lista de cosas para mandarle a la IA
                    cosas_para_ia = [img_factura] 

                    # Si Nancy subió la orden, la sumamos a la lista y le damos una instrucción
                    if f_orden:
                        img_orden = Image.open(f_orden)
                        cosas_para_ia.append(img_orden)
                        instruccion = """
                        Sos un experto administrativo contable. Te paso dos imágenes: factura y orden manual.
                        Extraé y cruzá los datos. 
                        Devolveme SOLO un JSON puro con:
                        {"fecha": "...", "chofer": "...", "cliente": "...", "litros": 0.0, "importe_total": 0.0, "nro_factura": "...", "nro_orden": "..."}
                        """
                    # Si NO subió la orden, cambiamos la instrucción
                    else:
                        instruccion = """
                        Sos un experto administrativo contable. Te paso SOLO una factura de surtidor (esta venta no tiene orden manual).
                        Extraé de la factura la fecha, cliente, litros (si figuran, si no poné 0), total y nro de factura.
                        Como no hay orden, en chofer y nro_orden poné "Sin orden".
                        Devolveme SOLO un JSON puro con:
                        {"fecha": "...", "chofer": "Sin orden", "cliente": "...", "litros": 0.0, "importe_total": 0.0, "nro_factura": "...", "nro_orden": "Sin orden"}
                        """

                    # Agregamos la instrucción al principio de la lista
                    cosas_para_ia.insert(0, instruccion)

                    # Le mandamos el paquete a Gemini
                    res = cliente.models.generate_content(
                        model='gemini-2.0-flash', 
                        contents=cosas_para_ia
                    )
                    
                    # Limpiamos y guardamos el JSON
                    limpio = res.text.replace("```json", "").replace("```", "").strip()
                    datos = json.loads(limpio)
                    
                    st.session_state.resumen_ventas.append(datos)
                    st.success("¡Venta agregada al resumen!")
                
                except Exception as e:
                    st.error(f"Error al leer los datos. Detalle: {e}")

    # --- MOSTRAR LA TABLA ACUMULADA ---
    if st.session_state.resumen_ventas:
        st.divider()
        st.subheader("📋 Resumen Acumulado del Día")
        df = pd.DataFrame(st.session_state.resumen_ventas)
        st.dataframe(df, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar Excel (CSV)", data=csv, file_name="resumen_carga.csv", mime="text/csv")
        with col_b:
            if st.button("🗑️ Borrar todo y empezar de nuevo"):
                st.session_state.resumen_ventas = []
                st.rerun()
