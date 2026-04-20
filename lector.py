import streamlit as st
import requests

st.title("🔍 Diagnóstico de Modelos Google")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    
    # Le preguntamos directamente a la base de datos de Google
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    respuesta = requests.get(url)
    
    if respuesta.status_code == 200:
        st.success("✅ Conexión perfecta con la API Key.")
        st.write("Estos son los nombres EXACTOS que Google te permite usar:")
        
        datos = respuesta.json()
        for modelo in datos.get('models', []):
            st.code(modelo['name'])
            
    else:
        st.error(f"❌ Error del servidor: {respuesta.status_code}")
        st.write(respuesta.text)

except Exception as e:
    st.error(f"Error interno: {e}")
