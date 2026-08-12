"""
modulos/clientes.py

Módulo "Gestión de Clientes" de lector.py, separado a su propio archivo
para que lector.py sea más corto y fácil de navegar.

Se llama desde lector.py así: modulo_clientes.mostrar(supabase, NOMBRES_SUCURSALES)
"""
import streamlit as st
import time
import secrets
import string


def _generar_password_temporal(largo=12):
    """Genera una contraseña temporal segura, para precargar el campo y ahorrarle
    el trabajo a quien da de alta el cliente (la puede cambiar si quiere)."""
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(largo))


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

        # La contraseña temporal se genera una sola vez por sesión de carga (no en
        # cada rerun del form), así no cambia sola mientras el usuario está tipeando.
        if "password_temp_alta_cliente" not in st.session_state:
            st.session_state["password_temp_alta_cliente"] = _generar_password_temporal()

        with st.form("form_alta"):
            st.subheader("Carga de Datos Iniciales")
            c1, c2 = st.columns(2)
            nombre_nuevo = c1.text_input("Razón Social / Nombre (Ej: TRANSPORTE S.H)").upper()
            cuit_nuevo = c2.text_input("CUIT (Sin guiones)")

            c3, c4 = st.columns(2)
            suc_madre = c3.selectbox("Sucursal Madre", [1, 2, 3, 4], format_func=lambda x: NOMBRES_SUCURSALES.get(x))
            limite_nuevo = c4.number_input("Límite de Efectivo ($)", min_value=0, value=0)

            st.markdown("**Acceso al Portal:**")
            c_auth1, c_auth2 = st.columns(2)
            email_nuevo = c_auth1.text_input("Email de acceso del cliente", placeholder="cliente@empresa.com")
            password_nueva = c_auth2.text_input(
                "Contraseña inicial",
                value=st.session_state["password_temp_alta_cliente"],
                help="Se generó una contraseña temporal automáticamente. Podés dejarla así o escribir una vos mismo — anotala para pasársela al cliente."
            )

            st.markdown("**Permisos Iniciales:**")
            col_p1, col_p2 = st.columns(2)
            req_foto_n = col_p1.checkbox("Requiere foto de remito obligatoria")
            formato_esp_n = col_p2.checkbox("Usar Formato Especial")

            col_p3, col_p4 = st.columns(2)
            exige_cuit_n = col_p3.checkbox("Exigir CUIT/RS en Factura")
            hab_n = col_p4.checkbox("Habilitado para operar", value=True)

            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("🚀 Dar de Alta Cliente", type="primary", use_container_width=True):
                if not nombre_nuevo or not cuit_nuevo or not email_nuevo or not password_nueva:
                    st.error("⚠️ Por favor, completá el Nombre, CUIT, Email y Contraseña.")
                else:
                    try:
                        # Paso 1: crear el usuario de autenticación en Supabase Auth.
                        # email_confirm=True evita que Supabase le mande un mail de
                        # confirmación al cliente — el acceso queda habilitado directo.
                        respuesta_auth = supabase.auth.admin.create_user({
                            "email": email_nuevo.strip(),
                            "password": password_nueva,
                            "email_confirm": True,
                        })
                        nuevo_auth_id = respuesta_auth.user.id

                        # Paso 2: recién con el UUID ya generado, crear la fila del cliente.
                        supabase.table("clientes").insert({
                            "nombre": nombre_nuevo,
                            "cuit": cuit_nuevo,
                            "sucursal_madre_id": suc_madre,
                            "limite_efectivo": limite_nuevo,
                            "auth_user_id": nuevo_auth_id,
                            "requiere_foto_remito": req_foto_n,
                            "formato_especial": formato_esp_n,
                            "elige_cuit_facturar": exige_cuit_n,
                            "habilitado": hab_n
                        }).execute()

                        st.success(
                            f"✅ ¡Golazo! Cliente registrado y con acceso al portal habilitado.\n\n"
                            f"**Email:** {email_nuevo.strip()}\n\n"
                            f"**Contraseña:** {password_nueva}\n\n"
                            f"Anotá estos datos ahora — pasáselos al cliente por el medio que uses habitualmente."
                        )
                        # Generamos una contraseña nueva para la próxima alta, y
                        # sacamos la usada de sesión para no repetirla por error.
                        del st.session_state["password_temp_alta_cliente"]
                    except Exception as e:
                        mensaje = str(e)
                        if "already been registered" in mensaje or "already registered" in mensaje.lower():
                            st.error(f"⚠️ Ya existe un usuario con ese email en Supabase Auth. Usá otro email, o si es un error, revisá la sección Authentication del dashboard.")
                        else:
                            st.error(f"Error al crear: {mensaje}")
        st.markdown('</div>', unsafe_allow_html=True)
