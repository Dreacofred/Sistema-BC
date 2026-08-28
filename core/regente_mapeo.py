"""
core/regente_mapeo.py

Etapa 2 del plan de integración con Regente: arma, en memoria, los datos que
eventualmente se van a mandar a Regente para un lote ya auditado.

IMPORTANTE — alcance de este archivo:
Este módulo NO llama a ninguna API. No hace ningún GET ni POST. Solo toma
las filas de `cobranzas_pendientes` (ya corregidas y auditadas en bot.py) y
las traduce/agrupa al formato que va a necesitar Regente, dejando huecos
marcados con None en los datos que todavía dependen de una consulta en vivo
(el id_titular del emisor, y el id_recibo real que devuelva Regente al
crear el Recibo). Esos huecos se completan en la Etapa 3, que sí va a tocar
la API real — y solo con el OK explícito de Diego.

Reglas de agrupación (confirmadas con Diego el 26/08/2026):
- Todos los Cheques Físicos de un lote van juntos, bajo UN solo Recibo.
- Todos los Cheques Electrónicos de un lote van juntos, bajo OTRO Recibo
  aparte (nunca mezclados con los físicos).
- Cada Transferencia genera su PROPIO Recibo individual (una transferencia,
  un recibo — no se agrupan entre sí ni con los cheques).
- Un lote puede tener varios emisores distintos entre sus cheques — cada
  cheque busca/crea su propio emisor por separado, pero comparten el mismo
  Recibo si son del mismo tipo (físico o electrónico).
- La categoría "Otro" (decisión de Diego, 26/08/2026): no tiene id_tipo_pago
  en Regente, así que NO se arma automáticamente — queda marcada para
  cargarse a mano.
- fec_recibo = la fecha del día en que se arma el envío (no la fecha del
  cheque, no la fecha de cierre del lote).
"""
from datetime import datetime

from core.regente_client import (
    ID_CONDICION_RESPONSABLE_INSCRIPTO,
    ID_TIPO_DOC_CUIT,
    ID_ESTADO_DISPONIBLE,
    ID_TIPO_PAGO_CHEQUE_FISICO,
    ID_TIPO_PAGO_CHEQUE_ELECTRONICO,
    TRANSFERENCIAS_POR_CODIGO_BCRA,
    resolver_id_adm_desde_codigo_bcra,
)

ID_USUARIO_API = "ia_client"


# ==========================================
# 1. HELPERS DE FECHA (cada entidad de Regente usa un formato distinto)
# ==========================================
def _fecha_hoy_iso():
    """Para rgReciboNg: formato AAAA-MM-DD, confirmado con el ejemplo real de Damián."""
    return datetime.now().strftime("%Y-%m-%d")


def _fecha_hora_hoy_iso():
    """Para rgReciboNg: formato AAAA-MM-DD HH:mm:ss."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _formatear_fecha_para_valor(fecha_iso, hora="00:00:00"):
    """
    Para rgValorNg: formato DD/MM/AAAA HH:mm:ss (distinto al de rgReciboNg).
    Convierte una fecha guardada por el bot en formato 'AAAA-MM-DD' (o
    'AAAA-MM-DD' con hora ya incluida) al formato que espera Regente.
    Devuelve None si la fecha viene vacía o no se puede interpretar.

    PENDIENTE DE VERIFICAR: no sabemos si Regente exige una hora específica
    acá o si con "00:00:00" alcanza — se puede ajustar cuando probemos.
    """
    if not fecha_iso:
        return None
    try:
        fecha_limpia = str(fecha_iso).strip()[:10]
        dt = datetime.strptime(fecha_limpia, "%Y-%m-%d")
    except ValueError:
        return None
    return f"{dt.strftime('%d/%m/%Y')} {hora}"


# ==========================================
# 2. ARMADO DE UN "VALOR" (un cheque o una transferencia individual)
# ==========================================
def _armar_valor(fila):
    """
    Traduce una fila de cobranzas_pendientes a los datos que necesita
    rgValorNg, MÁS los datos del emisor (para buscarlo/crearlo en la Etapa 3).

    Devuelve (valor_armado, motivo_error). Si motivo_error no es None,
    la fila no se pudo armar y hay que excluirla (ver `sin_procesar` en
    armar_grupos_para_regente).
    """
    tipo = fila.get("tipo_comprobante")
    codigo_banco = str(fila.get("codigo_banco") or "").strip()

    if tipo == "Cheque Físico":
        id_tipo_pago = ID_TIPO_PAGO_CHEQUE_FISICO
    elif tipo == "Cheque Electrónico":
        id_tipo_pago = ID_TIPO_PAGO_CHEQUE_ELECTRONICO
    elif tipo == "Transferencia":
        info_banco = TRANSFERENCIAS_POR_CODIGO_BCRA.get(codigo_banco)
        if not info_banco:
            return None, (
                f"Transferencia con código de banco '{codigo_banco}' no está "
                "en el catálogo de bancos conocidos (TRANSFERENCIAS_POR_CODIGO_BCRA "
                "en core/regente_client.py). Hay que revisarla a mano."
            )
        id_tipo_pago = info_banco["id_tipo_pago"]
    else:
        # "Otro", o cualquier valor inesperado
        return None, (
            f"tipo_comprobante '{tipo}' no tiene id_tipo_pago definido en "
            "Regente (decisión de Diego, 26/08/2026: se carga a mano)."
        )

    if not codigo_banco:
        return None, "Falta codigo_banco en esta fila, no se puede resolver el id_adm."

    try:
        id_adm = resolver_id_adm_desde_codigo_bcra(codigo_banco)
    except (ValueError, TypeError):
        return None, f"codigo_banco '{codigo_banco}' no es un código numérico válido."

    valor = {
        "_fila_id": fila.get("id"),  # referencia interna nuestra, no se manda a Regente
        "_tipo_comprobante": tipo,   # idem, solo para uso interno/logs
        "emisor": {
            "cuit": fila.get("cuit_emisor") or "",
            "sujeto": fila.get("razon_social_emisor") or "",
            "id_condicion": ID_CONDICION_RESPONSABLE_INSCRIPTO,
            "id_tipo_doc": ID_TIPO_DOC_CUIT,
        },
        "datos_valor": {
            "id_valor": 0,
            "id_tipo_pago": id_tipo_pago,
            "id_adm": id_adm,
            "id_titular": None,   # PENDIENTE: se completa en la Etapa 3
            "id_recibo": None,    # PENDIENTE: se completa en la Etapa 3
            "nro": fila.get("numero_identificador") or "",
            "fecha": _formatear_fecha_para_valor(fila.get("fecha_pago")),
            "fec_emision": _formatear_fecha_para_valor(fila.get("fecha_emision")),
            "monto": fila.get("monto") or 0,
            "nro_cuenta": fila.get("numero_cuenta") or "",
            "cod_postal_plaza": fila.get("codigo_sucursal") or "",
            "cuit_librador": fila.get("cuit_emisor") or "",
            "id_estado": ID_ESTADO_DISPONIBLE,
            # NOTA: "sujeto" y "administradora" en texto (los nombres, no los
            # ids) NO los mandamos acá a propósito. Por el mismo patrón que
            # vimos con "completra" y "estado" (campos que resultaron ser
            # de la VISTA, no de la tabla real), sospechamos que estos dos
            # también podrían calcularse solos a partir de id_titular e
            # id_adm. PENDIENTE DE VERIFICAR con una prueba real antes de
            # asumirlo — si hiciera falta mandarlos, se agregan acá.
        },
    }
    return valor, None


# ==========================================
# 3. ARMADO DE UN RECIBO (agrupa una lista de "valores" ya armados)
# ==========================================
def _armar_recibo(id_sujeto_cliente):
    return {
        "usuario": ID_USUARIO_API,
        "criterios": {"id_recibo": 0},
        "datos": {
            "id_recibo": 0,
            "id_sujeto": id_sujeto_cliente,
            "fec_recibo": _fecha_hoy_iso(),
            "fec_carga_recibo": _fecha_hora_hoy_iso(),
            "id_usuario": ID_USUARIO_API,
        },
    }


# ==========================================
# 4. FUNCIÓN PRINCIPAL
# ==========================================
def armar_grupos_para_regente(filas_lote, id_sujeto_cliente):
    """
    filas_lote: lista de diccionarios, cada uno una fila de cobranzas_pendientes
                ya auditada (mismo lote_id, mismo cliente).
    id_sujeto_cliente: el id_sujeto de Regente del cliente de este lote
                        (columna clientes.id_sujeto_regente en Supabase).

    Devuelve un diccionario:
    {
        "grupos": [
            {
                "tipo_grupo": "Cheque Físico" | "Cheque Electrónico" | "Transferencia",
                "recibo": {...},      # el payload para POST rgReciboNg
                "valores": [...],     # lista de "valores" armados (ver _armar_valor)
            },
            ...
        ],
        "sin_procesar": [
            {"fila_id": ..., "motivo": "..."},
            ...
        ],
    }

    Ningún dato de este resultado se manda todavía a Regente — es para
    revisar antes (Etapa 3: modo simulación) y recién después, con el OK
    de Diego, usarlo para las llamadas reales.
    """
    valores_fisicos = []
    valores_electronicos = []
    valores_transferencias = []  # cada transferencia queda sola en su lista
    sin_procesar = []

    for fila in filas_lote:
        valor, motivo_error = _armar_valor(fila)
        if motivo_error:
            sin_procesar.append({"fila_id": fila.get("id"), "motivo": motivo_error})
            continue

        tipo = fila.get("tipo_comprobante")
        if tipo == "Cheque Físico":
            valores_fisicos.append(valor)
        elif tipo == "Cheque Electrónico":
            valores_electronicos.append(valor)
        elif tipo == "Transferencia":
            valores_transferencias.append(valor)

    grupos = []

    if valores_fisicos:
        grupos.append({
            "tipo_grupo": "Cheque Físico",
            "recibo": _armar_recibo(id_sujeto_cliente),
            "valores": valores_fisicos,
        })

    if valores_electronicos:
        grupos.append({
            "tipo_grupo": "Cheque Electrónico",
            "recibo": _armar_recibo(id_sujeto_cliente),
            "valores": valores_electronicos,
        })

    for valor_transferencia in valores_transferencias:
        grupos.append({
            "tipo_grupo": "Transferencia",
            "recibo": _armar_recibo(id_sujeto_cliente),
            "valores": [valor_transferencia],
        })

    return {"grupos": grupos, "sin_procesar": sin_procesar}
