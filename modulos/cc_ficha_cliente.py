"""
modulos/cc_ficha_cliente.py

Consulta "Ficha de cliente" del módulo Cuentas Corrientes: el detalle de la
cuenta corriente de UN cliente contra la API de Regente (solo lectura).

No se llama desde lector.py directamente: la invoca el contenedor
modulos/cuenta_corriente.py, que es el que arma el selector de consultas. Se
llega acá buscando un cliente a mano, o desde una fila de cualquiera de las
consultas de listado (ver abrir_ficha() en el contenedor).

OJO CON EL ALCANCE: esta consulta por sí sola no justifica la integración con
Regente, porque el mismo detalle ya se ve en el ERP. El valor está en las
consultas cruzadas entre clientes —el listado de atrasados y compañía—, que
hoy dependen de que Regente exponga sus endpoints sin id_sujeto. Esta ficha es
el detalle al que se baja desde esas listas.

CRITERIO VISUAL (revisión de diseño, septiembre 2026):
- El rojo de la marca se reserva para lo que está VENCIDO o en alerta. Lo que
  está al día va en gris carbón. Si todo es rojo, el rojo deja de avisar nada.
- Un solo número grande en pantalla: el saldo. El resto acompaña en cuerpo
  normal.
- Un único formato de importe en toda la pantalla, el argentino
  ($ 1.234.567,89), que da utils_regente.formatear_pesos. Por eso las tablas
  se formatean con un Styler de pandas y NO con column_config: el formato
  "localized" de Streamlit toma el idioma del navegador y terminaba mostrando
  "132,568.83" (formato de EE.UU.) al lado de "$ 2.434.730,47".

PENDIENTE (segunda tanda, a revisar con Diego): los cambios de CSS global de
lector.py (títulos en gris, números de st.metric en gris, cifras tabulares y
ancho máximo de lectura) y una vista de deuda pensada para el celular, que hoy
obliga a scrollear la grilla de costado.
"""
import pandas as pd
import streamlit as st

from datetime import date

import utils_regente
from core import semaforo
from utils_regente import ErrorRegente


# Colores de la marca. Se repiten acá (y no se importan de lector.py) porque
# este módulo tiene que poder renderizarse solo, sin depender de la app madre.
COLOR_ROJO = "#C8102E"      # solo para vencido / alertas
COLOR_GRIS = "#3A3A3A"      # texto principal y cifras al día
COLOR_GRIS_SUAVE = "#6B7280"  # etiquetas y datos secundarios
COLOR_VERDE_FONDO = "#C8E6C9"  # fondo de las filas de anticipo (plata ya pagada)
COLOR_VERDE_TEXTO = "#1B5E20"

# Cuántos clientes como mucho trae el buscador por razón social. No usamos
# limite=0 en ninguna consulta: el servidor de Regente corta a los 30 segundos.
LIMITE_BUSQUEDA = 50

# Tope de filas de movimientos por consulta, por el mismo motivo.
LIMITE_MOVIMIENTOS = 300

# Orden fijo de las columnas de la tabla de deuda. Siempre se muestran todas,
# aunque para un cliente puntual alguna repita el mismo valor en cada fila.
# Primero lo que se necesita para cobrar (qué comprobante, cuándo vence, cuánto
# falta); el detalle administrativo (Tipo, Cuota, Atraso) va al final, que es
# además lo primero que se pierde de vista al scrollear en el celular.
COLUMNAS_DEUDA = [
    "Estado", "Comprobante", "Vencimiento", "Saldo",
    "Fecha", "Monto", "Punitorio",
    "Tipo", "Cuota", "Atraso (días)",
]

COLUMNAS_IMPORTE_DEUDA = ["Saldo", "Monto", "Punitorio"]
COLUMNAS_IMPORTE_MOVIMIENTOS = ["Debe", "Haber", "Saldo acumulado"]



# ==========================================
# 1. ESTADO DE LA PANTALLA
# ==========================================
def inicializar_estado():
    """El cliente elegido se guarda en sesión para que la pantalla sobreviva
    a los reruns de Streamlit (cambiar una fecha no tiene que borrar la
    búsqueda)."""
    st.session_state.setdefault("cc_id_sujeto", None)
    st.session_state.setdefault("cc_nombre", "")
    st.session_state.setdefault("cc_candidatos", [])


def elegir_cliente(id_sujeto, nombre):
    st.session_state.cc_id_sujeto = id_sujeto
    st.session_state.cc_nombre = nombre
    st.session_state.cc_candidatos = []


# ==========================================
# 2. PIEZAS VISUALES REUTILIZABLES
# ==========================================
def _dato(etiqueta, valor, color=COLOR_GRIS):
    """Un par etiqueta/valor en cuerpo normal, para los datos que acompañan al
    saldo sin competir con él."""
    return (
        f'<div style="line-height:1.35;">'
        f'<div style="font-size:12px;color:{COLOR_GRIS_SUAVE};">{etiqueta}</div>'
        f'<div style="font-size:15px;color:{color};font-variant-numeric:tabular-nums;">{valor}</div>'
        f'</div>'
    )


def _vencimiento_mas_viejo(deuda):
    """
    El vencimiento pendiente más viejo entre las filas que SUMAN deuda (las
    notas de crédito y los anticipos no cuentan: no son algo que venza).

    Si ya pasó, es la factura más atrasada del cliente. Si todavía no llegó, es
    la primera que le va a vencer. Es el mismo dato con dos lecturas, según la
    fecha de hoy.
    """
    fechas = [
        f["fvenc"] for f in (deuda or {}).get("filas", [])
        if (f.get("signo") or 1) > 0 and (f.get("saldo") or 0) > 0 and f.get("fvenc")
    ]
    return min(fechas) if fechas else None


def _chip_semaforo(color):
    """
    El semáforo del cliente, como una pastilla de color al lado del saldo.

    El color NO se decide acá: sale de core/semaforo.py, que es la misma regla
    que van a usar el listado de atrasados, el bloqueo de órdenes de carga y el
    aviso del portal. Si esta pantalla se inventara su propio criterio, el día
    que cambie un umbral quedarían diciendo cosas distintas.
    """
    if not color:
        return ""
    fondo = semaforo.hex_color(color)
    return (
        f'<div style="margin-top:8px;">'
        f'<span title="{semaforo.descripcion_regla()}" '
        f'style="display:inline-block;padding:3px 12px;border-radius:999px;'
        f'background:{fondo};color:{semaforo.hex_texto(color)};'
        f'font-size:13px;font-weight:600;">'
        f'{semaforo.etiqueta(color)}</span></div>'
    )


def _fila_de_datos(pares):
    """Muestra una lista de (etiqueta, valor) o (etiqueta, valor, color) en
    columnas. Reemplaza a la tira de emojis separados por puntos medios, que
    disfrazaba cuatro datos distintos de una sola oración."""
    pares = [p for p in pares if p[1]]
    if not pares:
        return
    for columna, par in zip(st.columns(len(pares)), pares):
        etiqueta, valor = par[0], par[1]
        color = par[2] if len(par) > 2 else COLOR_GRIS
        columna.markdown(_dato(etiqueta, valor, color), unsafe_allow_html=True)


def _estilar_importes(df, columnas):
    """Aplica el formato argentino de pesos a las columnas de importe y alinea
    los números a la derecha, dejando el dato numérico intacto por debajo para
    que la tabla se pueda seguir ordenando por valor."""
    columnas = [c for c in columnas if c in df.columns]
    estilo = df.style.format({c: utils_regente.formatear_pesos for c in columnas})
    return estilo.set_properties(
        subset=columnas,
        **{"text-align": "right", "font-variant-numeric": "tabular-nums"},
    )


# ==========================================
# 3. BUSCADOR DE CLIENTES
# ==========================================
def _buscar_cliente(supabase, modo, texto):
    """Resuelve la búsqueda y deja el resultado en sesión. Separado del dibujo
    del formulario para que se lea de corrido qué hace cada modo."""
    if not texto:
        st.warning("Escribí un código, un CUIT o una razón social para buscar.")
        return

    if modo == "Código":
        if not texto.isdigit():
            st.warning("El código de cliente de Regente es un número. Por ejemplo: 2824")
            return
        # Regente no tiene un endpoint para traer un cliente por id, así que
        # tomamos el código como válido y el nombre sale del estado de cuenta.
        elegir_cliente(int(texto), f"Cliente {texto}")
        return

    if modo == "CUIT":
        encontrados = utils_regente.buscar_cliente_por_cuit(texto, supabase)
        if not encontrados:
            st.info(
                "No se encontró ese CUIT. La API de Regente todavía **no permite "
                "buscar por CUIT** (su buscador mira solo el nombre), así que esta "
                "búsqueda se resuelve contra la tabla de clientes de Supabase y "
                "solo encuentra a los que están dados de alta en nuestro sistema. "
                "Para el resto, buscá por razón social."
            )
            return
    else:  # Razón social
        with st.spinner("Buscando en Regente..."):
            encontrados = utils_regente.buscar_clientes_por_nombre(texto, limite=LIMITE_BUSQUEDA)
        if not encontrados:
            st.info("Ningún cliente de Regente coincide con ese nombre.")
            return

    if len(encontrados) == 1:
        elegir_cliente(encontrados[0]["id_sujeto"], encontrados[0]["sujeto"])
    else:
        st.session_state.cc_candidatos = encontrados


def _buscador(supabase):
    with st.container(border=True):
        st.subheader("Buscar cliente")

        # El formulario es lo que hace que Enter dispare la búsqueda: sin él,
        # tipear y apretar Enter no hacía nada y había que ir al botón.
        with st.form("cc_form_busqueda", border=False):
            col_modo, col_texto, col_boton = st.columns([1.2, 2.5, 1], vertical_alignment="bottom")

            modo = col_modo.radio("Buscar por:", ["Código", "CUIT", "Razón social"], key="cc_modo_busqueda")
            texto = col_texto.text_input(
                "Dato a buscar",
                key="cc_texto_busqueda",
                # La ayuda es fija: adentro de un formulario no se refresca al
                # cambiar el modo, porque Streamlit no reejecuta hasta enviar.
                help=(
                    "Código: el número interno de Regente (ej. 2824). "
                    "CUIT: sin guiones (ej. 30547794482). "
                    "Razón social: alcanza con parte del nombre (ej. AGRONORTE)."
                ),
            )
            buscar = col_boton.form_submit_button("Buscar", use_container_width=True)

        if buscar:
            st.session_state.cc_candidatos = []
            st.session_state.cc_id_sujeto = None
            try:
                _buscar_cliente(supabase, modo, (texto or "").strip())
            except ErrorRegente as e:
                st.error(str(e))

        # Si la búsqueda trajo varios, hay que elegir uno. Va fuera del
        # formulario: adentro solo puede haber botones de envío.
        candidatos = st.session_state.cc_candidatos
        if candidatos:
            st.divider()
            st.caption(
                f"{len(candidatos)} coincidencias"
                + (f" (se muestran las primeras {LIMITE_BUSQUEDA})"
                   if len(candidatos) >= LIMITE_BUSQUEDA else "")
            )

            def _etiqueta(c):
                cuit = f" · CUIT {c['cuit']}" if c["cuit"] else ""
                return f"[{c['id_sujeto']}] {c['sujeto']}{cuit}"

            elegido = st.selectbox(
                "Elegí el cliente:", candidatos, format_func=_etiqueta, key="cc_candidato_sel"
            )
            if st.button("Ver cuenta corriente"):
                elegir_cliente(elegido["id_sujeto"], elegido["sujeto"])
                st.rerun()


# ==========================================
# 4. RESUMEN DE ESTADO DE CUENTA
# ==========================================
def _mostrar_resumen(estado, deuda):
    """El encabezado de la cuenta: un solo número grande (el saldo) y los
    datos que lo explican al lado, en cuerpo normal.

    'estado' puede ser None cuando el cliente no tiene saldo: en ese caso la
    API devuelve la lista vacía, no un error."""
    if estado is None:
        st.success("El cliente no tiene saldo pendiente en Regente.")
        return

    # El atraso sale del DETALLE de la deuda, no del campo "dias" del estado de
    # cuenta: Regente lo manda en 0 aunque haya facturas vencidas (caso 693,
    # 25/09/2026). Ver core/semaforo.py.
    dias = semaforo.dias_atraso_de_deuda(deuda) or semaforo.dias_atraso_de_estado(estado)
    atrasado = dias > 0
    color_sem = semaforo.color_de_deuda(deuda) or semaforo.color_de_estado_cuenta(estado)
    # El saldo se pinta solo cuando el semáforo ya no está en verde: un cliente
    # al día no tiene por qué leerse como una alarma.
    color_saldo = semaforo.hex_color(color_sem) if color_sem in (semaforo.AMARILLO, semaforo.ROJO) else COLOR_GRIS

    # Un saldo negativo no es una deuda en menos: es plata A FAVOR del cliente.
    # Se dice con todas las letras en vez de dejar un número en menos que hay
    # que interpretar.
    saldo_a_favor = estado["saldo_final"] < 0
    etiqueta_saldo = "Saldo a favor del cliente" if saldo_a_favor else "Saldo actual"
    # Se mantiene el signo menos: es el que dice que la plata está a favor del
    # cliente. El verde acompaña para que se lea de un vistazo que no es deuda.
    importe_saldo = utils_regente.formatear_pesos(estado["saldo_final"])
    if saldo_a_favor:
        color_saldo = semaforo.hex_color(semaforo.VERDE)

    col_saldo, col_datos = st.columns([1.3, 2], vertical_alignment="center")
    with col_saldo:
        st.markdown(
            f'<div style="font-size:13px;color:{COLOR_GRIS_SUAVE};">{etiqueta_saldo}</div>'
            # nowrap + clamp: sin esto, un saldo de 7 cifras se parte en varias
            # líneas ("$ / 2.434.730,4 / 7") cuando la ventana es angosta.
            f'<div style="font-size:clamp(26px,3vw,40px);font-weight:700;'
            f'color:{color_saldo};line-height:1.15;white-space:nowrap;'
            f'font-variant-numeric:tabular-nums;">'
            f'{importe_saldo}</div>'
            + _chip_semaforo(color_sem),
            unsafe_allow_html=True,
        )

    with col_datos:
        datos = [
            (
                "Días de atraso",
                str(dias),
                semaforo.hex_color(color_sem) if atrasado else COLOR_GRIS,
            ),
            ("Punitorios", utils_regente.formatear_pesos(estado["punitorios"])),
        ]
        # Solo tiene sentido mostrar el saldo con punitorios cuando hay
        # punitorios: si son 0, repite el número grande de al lado.
        if estado["punitorios"]:
            datos.append((
                "Saldo con punitorios",
                utils_regente.formatear_pesos(estado["saldo_con_punitorios"]),
                COLOR_ROJO,
            ))
        # La misma fecha sirve para las dos cosas: es el vencimiento pendiente
        # más viejo. Si ya pasó, es lo más atrasado que tiene; si todavía no
        # llegó, es lo primero que le vence. Cambia el nombre, no el dato.
        fecha_venc = _vencimiento_mas_viejo(deuda) or estado["peor_fecha"]
        if fecha_venc:
            ya_vencio = fecha_venc < date.today()
            datos.append((
                "Vencimiento impago más viejo" if ya_vencio else "Próximo vencimiento",
                f"{fecha_venc:%d/%m/%Y}",
                semaforo.hex_color(color_sem) if (ya_vencio and atrasado) else COLOR_GRIS,
            ))
        if estado["fecha_ultimo_recibo"]:
            # Es el campo "fup" de Regente: la fecha del último recibo del
            # cliente, o sea la última vez que pagó. Se muestra como "Último
            # pago" porque es lo que la gente entiende sin explicación.
            datos.append(("Último pago", f"{estado['fecha_ultimo_recibo']:%d/%m/%Y}"))
        _fila_de_datos(datos)

    st.write("")
    _fila_de_datos([
        ("Domicilio", f"{estado['direccion']} {estado['localidad']}".strip()),
        ("Teléfono", estado["telefono"]),
    ])

    if estado["observaciones"]:
        st.info(f"Observaciones en Regente: {estado['observaciones']}")


# ==========================================
# 5. DETALLE DE DEUDA PENDIENTE
# ==========================================
def _mostrar_deuda(deuda):
    st.subheader("Deuda pendiente")

    if not deuda["filas"]:
        st.info("No hay comprobantes ni cuotas pendientes.")
        return

    hoy = date.today()
    filas = []
    for f in deuda["filas"]:
        # Una nota de crédito o un anticipo (signo -1) es plata A FAVOR del
        # cliente: aunque su fecha ya pasó, no es una deuda vencida y no puede
        # contar como tal ni en el color ni en el contador de vencidos.
        a_favor = f["signo"] < 0
        anticipo = utils_regente.es_anticipo(f["nro"])
        vencida = (
            not a_favor
            and f["fvenc"] is not None
            and f["fvenc"] < hoy
            and f["saldo"] > 0
        )
        if anticipo:
            estado_fila = "Anticipo"
        elif a_favor:
            estado_fila = "A favor"
        elif vencida:
            estado_fila = "Vencida"
        else:
            estado_fila = "Al día"
        filas.append({
            "Estado": estado_fila,
            "Comprobante": f["nro"],
            "Vencimiento": f["fvenc"],
            # Con signo: las notas de crédito tienen que restar en la tabla,
            # igual que restan en el total que calcula Regente.
            "Saldo": f["saldo_con_signo"],
            "Fecha": f["fecha_comp"],
            "Monto": f["monto"],
            "Punitorio": f["punitorio"],
            # El signo solo dice si suma o resta: anticipos y notas de crédito
            # comparten el -1, así que el anticipo se reconoce por el número.
            "Tipo": (
                "Anticipo" if anticipo
                else ("Nota de crédito" if a_favor else "Factura / Débito")
            ),
            "Cuota": (
                f"{f['nro_cuota']}/{f['cant_cuotas']}"
                if f["nro_cuota"] and f["cant_cuotas"] else "-"
            ),
            "Atraso (días)": f["atraso"],
        })

    df = pd.DataFrame(filas)[COLUMNAS_DEUDA]

    def _pintar_estado(valor):
        """Pinta solo la celda de Estado según lo que sea la fila."""
        if valor == "Vencida":
            color = COLOR_ROJO
        elif valor == "Anticipo":
            color = COLOR_VERDE_TEXTO
        elif valor == "A favor":
            color = COLOR_GRIS_SUAVE
        else:
            color = COLOR_GRIS
        return f"color: {color}; font-weight: 600;"

    def _pintar_fila(fila):
        """Los anticipos van con la fila entera en verde: no son deuda, son
        plata que el cliente YA pagó y todavía no se aplicó a una factura. Sin
        eso se leen como un renglón más de lo que debe."""
        if fila["Estado"] == "Anticipo":
            return [f"background-color: {COLOR_VERDE_FONDO};"] * len(fila)
        return [""] * len(fila)

    estilo = (
        _estilar_importes(df, COLUMNAS_IMPORTE_DEUDA)
        .apply(_pintar_fila, axis=1)
        .map(_pintar_estado, subset=["Estado"])
    )

    st.dataframe(
        estilo,
        use_container_width=True,
        hide_index=True,
        column_config={
            # "Estado" angosto para que en el celular entren también
            # Vencimiento y Saldo sin tener que scrollear la grilla de costado.
            "Estado": st.column_config.TextColumn("Estado", width="small"),
            "Vencimiento": st.column_config.DateColumn("Vencimiento", format="DD/MM/YYYY"),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
        },
    )

    vencidas = sum(1 for f in filas if f["Estado"] == "Vencida")
    _fila_de_datos([
        ("Total adeudado", utils_regente.formatear_pesos(deuda["total"])),
        ("Comprobantes pendientes", f"{len(filas)}"),
        (
            "Vencidos",
            f"{vencidas}",
            COLOR_ROJO if vencidas else COLOR_GRIS,
        ),
        ("Punitorios acumulados", utils_regente.formatear_pesos(deuda["total_punitorios"])),
    ])
    st.caption(
        "El total lo calcula Regente sumando el saldo de cada fila por su signo "
        "(las notas de crédito restan) y no incluye punitorios."
    )


# ==========================================
# 6. MOVIMIENTOS (PAGOS Y COMPROBANTES)
# ==========================================
def _mostrar_movimientos(id_sujeto):
    with st.expander("Movimientos y pagos del período"):
        desde_defecto, hasta_defecto = utils_regente.rango_de_fechas_por_defecto(meses_atras=6)

        col1, col2, col3 = st.columns([1, 1, 1])
        desde = col1.date_input("Desde", value=desde_defecto, format="DD/MM/YYYY", key="cc_desde")
        hasta = col2.date_input("Hasta", value=hasta_defecto, format="DD/MM/YYYY", key="cc_hasta")
        limite = col3.number_input(
            "Máx. de filas", min_value=50, max_value=LIMITE_MOVIMIENTOS, value=100, step=50,
            help=(
                "Regente corta las consultas a los 30 segundos. Si te faltan "
                "movimientos, conviene achicar el rango de fechas antes que "
                "subir este número."
            ),
            key="cc_limite",
        )

        if desde > hasta:
            st.warning("La fecha 'Desde' no puede ser posterior a la fecha 'Hasta'.")
            return

        if not st.button("Consultar movimientos"):
            return

        try:
            with st.spinner("Consultando movimientos en Regente..."):
                movimientos = utils_regente.obtener_cta_cte(
                    id_sujeto, desde, hasta, limite=int(limite)
                )
        except ErrorRegente as e:
            st.error(str(e))
            return

        if not movimientos:
            st.info("No hay movimientos en ese período.")
            return

        filas = []
        for m in movimientos:
            filas.append({
                "Fecha": m["fecha"],
                "Comprobante": "Saldo inicial" if m["es_saldo_inicial"] else (m["nro"] or "↳ pago"),
                "Recibo": m["nro_recibo"] or "-",
                "Medio de pago": m["tipo_pago"] or "-",
                "Debe": m["debe"],
                "Haber": m["haber"],
                "Saldo acumulado": m["saldo"],
            })

        st.dataframe(
            _estilar_importes(pd.DataFrame(filas), COLUMNAS_IMPORTE_MOVIMIENTOS),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            },
        )
        st.caption(
            "La primera fila es el saldo inicial: resume todo lo anterior a la "
            "fecha 'Desde'. Las filas sin número de comprobante son los pagos "
            "que cancelan el comprobante de arriba."
        )

        if len(movimientos) >= limite:
            st.warning(
                f"Se alcanzó el límite de {int(limite)} filas: puede haber más "
                "movimientos sin mostrar. Achicá el rango de fechas."
            )


# ==========================================
# 7. VISTA COMPLETA DE LA CUENTA
# ==========================================
def _mostrar_cuenta(id_sujeto, nombre):
    try:
        with st.spinner("Consultando Regente..."):
            estado = utils_regente.obtener_estado_cuenta(id_sujeto)
            deuda = utils_regente.obtener_deuda(id_sujeto)
    except ErrorRegente as e:
        st.error(str(e))
        return

    # Si el estado de cuenta trajo el nombre real, es mejor que el que veníamos
    # arrastrando del buscador (sobre todo cuando se buscó por código).
    titulo = (estado or {}).get("sujeto") or nombre

    with st.container(border=True):
        st.markdown(
            f'<div style="font-size:24px;font-weight:700;color:{COLOR_GRIS};">{titulo}</div>'
            f'<div style="font-size:13px;color:{COLOR_GRIS_SUAVE};margin-bottom:14px;">'
            f'Código en Regente: {id_sujeto}</div>',
            unsafe_allow_html=True,
        )

        _mostrar_resumen(estado, deuda)
        st.divider()
        _mostrar_deuda(deuda)

    _mostrar_movimientos(id_sujeto)


# ==========================================
# 8. ENTRADA DE LA CONSULTA
# ==========================================
def mostrar(supabase):
    """La llama el contenedor (modulos/cuenta_corriente.py). El título y el
    selector de consultas los pone él; acá solo va el contenido."""
    inicializar_estado()
    _buscador(supabase)

    if st.session_state.cc_id_sujeto:
        _mostrar_cuenta(st.session_state.cc_id_sujeto, st.session_state.cc_nombre)
    else:
        # Una pantalla vacía es una invitación a hacer algo, no un hueco.
        st.caption(
            "Buscá un cliente por código, CUIT o razón social para ver su saldo, "
            "su deuda pendiente y sus últimos pagos."
        )
