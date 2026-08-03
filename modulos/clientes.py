"""
modulos/clientes.py

Módulo "Gestión de Clientes" de lector.py, separado a su propio archivo
para que lector.py sea más corto y fácil de navegar.

Se llama desde lector.py así: modulos_clientes.mostrar(supabase, NOMBRES_SUCURSALES)
"""
import streamlit as st
import time


def mostrar(supabase, NOMBRES_SUCURSALES):
    st.title("👥 Gestión de Clientes")
    st.markdown('<p style="color:#666; font-size:16px;">Administración centralizada de cuentas corrientes, límites y permisos.</p>', unsafe_allow_html=True)

    tab_editar, tab_alta = st.tabs(["📝 Editar Clientes", "➕ Dar de Alta Nuevo Cliente"])

    with tab_editar:
        st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
        res_clientes = supabase.table("clientes").select("*").order("nombre").execute()
        clientes_db = res_clientes.data

        if clientes_db:
            nombres_clientes = [c['nombre'] for c in clientes_db]
            cliente_sel = st.selectbox("Seleccionar cliente a administrar:", ["--- Seleccionar ---"] + nombres_clientes)

            if cliente_sel != "--- Seleccionar ---":
                st.markdown("<hr>", unsafe_allow_html=True)
                c_data = next(c for c in clientes_db if c['nombre'] == cliente_sel)

                if c_data.get('habilitado', True):
                    st.success("🟢 ESTADO: HABILITADO")
                else:
                    st.error("⛔ ESTADO: INHABILITADO")

                with st.form(f"form_edit_{c_data['id']}"):
                    st.subheader(f"Datos de {c_data['nombre']}")
                    c1, c2 = st.columns(2)
                    limite = c1.number_input("Límite de Efectivo ($)", value=float(c_data.get('limite_efectivo', 0)))

                    st.markdown("**Permisos y Configuraciones:**")
                    c3, c4 = st.columns(2)
                    req_foto = c3.checkbox("Foto de remito obligatoria", value=c_data.get('requiere_foto_remito', False))
                    formato_esp = c4.checkbox("Formato Especial (Órdenes Lts/Efe)", value=c_data.get('formato_especial', False))

                    c5, c6 = st.columns(2)
                    exige_cuit = c5.checkbox("Exigir CUIT/RS Factura", value=c_data.get('elige_cuit_facturar', False))
                    habilitado = c6.checkbox("Cliente Habilitado", value=c_data.get('habilitado', True))

                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True):
                        try:
                            supabase.table("clientes").update({
                                "limite_efectivo": limite,
                                "requiere_foto_remito": req_foto,
                                "formato_especial": formato_esp,
                                "elige_cuit_facturar": exige_cuit,
                                "habilitado": habilitado
                            }).eq("id", c_data['id']).execute()
                            st.success("✅ ¡Cliente actualizado con éxito!")
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar: {e}")
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_alta:
        st.markdown('<div class="tarjeta-pro">', unsafe_allow_html=True)
        with st.form("form_alta"):
            st.subheader("Carga de Datos Iniciales")
            c1, c2 = st.columns(2)
            nombre_nuevo = c1.text_input("Razón Social / Nombre (Ej: TRANSPORTE S.H)").upper()
            cuit_nuevo = c2.text_input("CUIT (Sin guiones)")

            c3, c4 = st.columns(2)
            suc_madre = c3.selectbox("Sucursal Madre", [1, 2, 3, 4], format_func=lambda x: NOMBRES_SUCURSALES.get(x))
            limite_nuevo = c4.number_input("Límite de Efectivo ($)", min_value=0, value=0)

            auth_id = st.text_input("UUID de Autenticación (Supabase Auth)", help="Pegá acá el ID del usuario creado en la sección Authentication de Supabase")

            st.markdown("**Permisos Iniciales:**")
            col_p1, col_p2 = st.columns(2)
            req_foto_n = col_p1.checkbox("Requiere foto de remito obligatoria")
            formato_esp_n = col_p2.checkbox("Usar Formato Especial")

            col_p3, col_p4 = st.columns(2)
            exige_cuit_n = col_p3.checkbox("Exigir CUIT/RS en Factura")
            hab_n = col_p4.checkbox("Habilitado para operar", value=True)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("🚀 Dar de Alta Cliente", type="primary", use_container_width=True):
                if not nombre_nuevo or not cuit_nuevo or not auth_id:
                    st.error("⚠️ Por favor, completá el Nombre, CUIT y el UUID de Autenticación.")
                else:
                    try:
                        supabase.table("clientes").insert({
                            "nombre": nombre_nuevo,
                            "cuit": cuit_nuevo,
                            "sucursal_madre_id": suc_madre,
                            "limite_efectivo": limite_nuevo,
                            "auth_user_id": auth_id,
                            "requiere_foto_remito": req_foto_n,
                            "formato_especial": formato_esp_n,
                            "elige_cuit_facturar": exige_cuit_n,
                            "habilitado": hab_n
                        }).execute()
                        st.success("✅ ¡Golazo! Cliente registrado exitosamente en la base de datos.")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al crear: {e}")
        st.markdown('</div>', unsafe_allow_html=True)
