"""
core/supabase_client.py

Conexión ÚNICA a Supabase. Más adelante, todas las apps (lector.py,
app_clientes.py, bot.py) van a importar desde acá en vez de repetir
las mismas 3 líneas de conexión cada una.

Por ahora este archivo no lo usa nadie todavía (por eso es 100% seguro
crearlo) — es una pieza que dejamos lista para conectar en una próxima
sesión.
"""
import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_supabase_client() -> Client:
    """
    Devuelve un cliente de Supabase ya conectado.
    Usa cache_resource para no reconectar en cada rerun de Streamlit.
    """
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)
