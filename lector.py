import streamlit as st
from google import genai
from pypdf import PdfReader
from PIL import Image

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Sistema BC Combustibles", layout="wide")

# --- BARRA LATERAL PARA NAVEGACIÓN ---
st.sidebar.title("Menú Principal")
opcion = st.sidebar.radio(
    "Seleccioná una tarea:",
    ["Facturas de Proveedores", "Ventas a Camiones (Órdenes)"]
)

# Inicializamos el cliente de IA
cliente = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# ==========================================
# SECCIÓN 1: FACTURAS DE PROVEEDORES (Lo que ya tenías)
# ==========================================
if opcion == "Facturas de Proveedores":
    st.title("📄 Carga de Facturas de Proveedores")
    st.write("Subí el PDF o la foto de la factura para extraer los datos para Regente.")
    
    archivo_subido = st.file_uploader("Arrastrá archivo aquí", type=["pdf", "png", "jpg", "jpeg"], key="prov")

    if archivo_subido and st.button("🚀 Extraer Datos Proveedor"):
        with st.spinner("Analizando..."):
            if archivo_subido.name.lower().endswith('.pdf'):
                lector = PdfReader(archivo_subido)
                material = lector.pages[0].extract_text()
            else:
                material = Image.open(archivo_subido)

            orden = "Analizá esta factura de proveedor de Argentina. Devolveme un JSON con proveedor_nombre, proveedor_cuit, numero_comprobante, fecha_emision, importe_total y articulos."
            
            respuesta = cliente.models.generate_content(model='gemini-2.0-flash', contents=[orden, material])
            st.success("¡Datos extraídos!")
            st.code(respuesta.text, language="json")

# ==========================================
# SECCIÓN 2: VENTAS A CAMIONES (Lo nuevo para Nancy)
# ==========================================
elif opcion == "Ventas a Camiones (Órdenes)":
    st.title("🚛 Registro de Ventas a Camiones")
    st.write("Subí la **Foto de la Factura** y la **Foto de la Orden Manual** para unificar los datos.")

    col1, col2 = st.columns(2)
    with col1:
        foto_factura = st.file_uploader("1. Foto de la Factura", type=["png", "jpg", "jpeg"], key="f_fact")
    with col2:
        foto_orden = st.file_uploader("2. Foto de la Orden Manual", type=["png", "jpg", "jpeg"], key="f_ord")

    if foto_factura and foto_orden:
        if st.button("🔗 Unificar y Procesar Venta", use_container_width=True):
            with st.spinner("Leyendo ambas imágenes y cruzando datos..."):
                try:
                    img_factura = Image.open(foto_factura)
                    img_orden = Image.open(foto_orden)

                    instruccion_unificada = """
                    Sos un administrativo contable de una estación de servicio. 
                    Te paso dos imágenes: una es la factura del surtidor y la otra es una orden escrita a mano por el playero.
                    
                    TU TAREA:
                    1. Extraer de la FACTURA: Número de factura, Fecha, Razón Social del cliente y el Total.
                    2. Extraer de la ORDEN MANUAL: Nombre del Chofer, Número de Orden, Litros cargados y cualquier observación.
                    3. Cruzar los datos: Verificá que los litros de la orden coincidan con los de la factura.
                    4. Calculá el precio por litro (Total Factura / Litros).

                    Devolveme un JSON con esta estructura:
                    {
                      "fecha": "...",
                      "chofer": "...",
                      "cliente_razon_social": "...",
                      "litros": 0.0,
                      "importe_total": 0.0,
                      "precio_por_litro": 0.0,
                      "nro_factura": "...",
                      "nro_orden": "...",
                      "alerta": "Solo si hay una diferencia entre la orden y la factura"
                    }
                    """

                    # Le mandamos las DOS imágenes a la IA juntas
                    respuesta = cliente.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=[instruccion_unificada, img_factura, img_orden]
                    )

                    st.success("¡Datos unificados con éxito!")
                    st.code(respuesta.text, language="json")
                
                except Exception as e:
                    st.error(f"Error al procesar: {e}")
