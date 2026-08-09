"""
core/prompts_ia.py

Acá viven los prompts que se le mandan a Gemini y a Claude. Antes estaban
escritos sueltos adentro de utils_bcra.py y lector.py; ahora viven acá para
que, si el día de mañana hay que ajustar una regla, se toque un solo lugar.

Nota: los prompts de proveedores y remitos los usan lector.py / modulos/.
La herramienta HERRAMIENTA_CHEQUES_WHATSAPP y las instrucciones
INSTRUCCIONES_CHEQUES_WHATSAPP las usa webhook.py (bot de WhatsApp, con
Claude/Anthropic).
"""

# ==========================================
# 1. LECTURA DE CHEQUES (ya en uso por utils_bcra.py, con Gemini)
# ==========================================
PROMPT_LECTURA_CHEQUES = """
Actúa como un auditor senior de BC Combustibles. Analiza esta foto que contiene un lote de cheques físicos.

REGLAS DE ORO (Aislamiento de Datos):
1. Analiza los cheques visualmente de arriba hacia abajo.
2. El Emisor del cheque NUNCA es el nombre que sigue a "Páguese a". Ignora ese nombre gigante.
3. Ve siempre a la parte INFERIOR del cheque (junto a la firma o el logo del banco).
4. Extrae de ahí el CUIT (11 dígitos, suelen empezar con 20, 23, 27, 30) y la Razón Social del EMISOR.
5. Busca el NÚMERO DEL CHEQUE. Generalmente está en la esquina superior derecha o en la serie de números de la banda inferior.

ESTRUCTURA DE RESPUESTA OBLIGATORIA:
Devuelve ÚNICAMENTE un JSON puro (sin formato markdown) que sea una LISTA de objetos, uno por cada cheque:
[
    {
        "id": 1,
        "numero_cheque": "84512356",
        "emisor": "RAZON SOCIAL 1",
        "cuit": "20123456789"
    }
]

Si un dato no es legible con un 100% de seguridad, devuelve "ERROR_LECTURA" en ese campo específico.
"""


# ==========================================
# 2. LECTURA DE FACTURAS DE PROVEEDORES (usado por modulos/proveedores.py)
# ==========================================
PROMPT_FACTURAS_PROVEEDORES = (
    "Eres auditor contable. Objetivo: leer FACTURA DE COMPRA. "
    "BC COMBUSTIBLES es RECEPTOR. Buscá CUIT, Fecha, Nº de Factura y Totales. "
    "Extraé JSON puro."
)


# ==========================================
# 3. GENERADOR DE RESUMEN A CLIENTES / REMITOS (usado por modulos/resumen.py)
# ==========================================
PROMPT_AUDITORIA_REMITOS = """
Sos un auditor experto. El Emisor es 'BC COMBUSTIBLES'. Buscá al CLIENTE Receptor y los datos de la carga.

Devolvé ÚNICAMENTE un JSON puro, sin texto adicional ni formato markdown (sin ```json), con estas claves exactas:
- "fecha": Fecha del comprobante.
- "razon_social": Cliente receptor.
- "importe": Monto total en números.
- "comprobante": Número de comprobante.
- "litros": Sumá la cantidad TOTAL de litros de combustible. NO sumes aceites o aditivos, solo combustibles.
- "detalle_productos": Hacé un resumen de los combustibles y sus litros exactos. Ejemplo: 'Euro Diesel G3: 201 L | Gas Oil 500 G2: 81.5 L'. Si es un solo producto, poné solo ese.
- "observaciones_ia": Evaluá TODOS los ítems facturados y aplicá ESTA REGLA ESTRICTA:
  1. Si SOLO cargó 'Gas Oil 500 G2' (Gasoil normal), devolvé "". (Vacío).
  2. Si detectás 2 o más combustibles diferentes, devolvé "Atención. La factura tiene varios productos."
  3. Si cargó SOLO Euro, devolvé "Atención. El producto cargado es Euro, verifique."
  4. Si SOLO cargó Nafta, devolvé "Atención. La factura contiene Nafta."
  5. Si encontrás artículos extra (aceites, filtros, etc.), devolvé "Atención. La factura contiene artículos extra: [detallar los extra]."
""".strip()


# ==========================================
# 4. LECTURA DE COMPROBANTES POR WHATSAPP (usado por webhook.py, con Claude)
# ==========================================
# A diferencia de los prompts de arriba (que piden JSON libre y después el
# código busca "{" y "}" a mano), acá usamos una "tool" de Anthropic: le
# damos a Claude una estructura fija que está OBLIGADO a llenar. Esto evita
# el problema que tuvimos con el ThinkingBlock (Claude respondiendo con un
# bloque de texto que no era JSON puro) y hace la lectura mucho más robusta.
#
# El bot recibe 3 tipos de situaciones posibles en un mismo lote de fotos:
#   CASO A: solo fotos de cheques físicos sueltos (el caso de siempre).
#   CASO B: una captura de pantalla de home banking con una TABLA de varios
#           cheques (cada fila de la tabla = un cheque).
#   CASO C: un comprobante de LIQUIDACIÓN/depósito (que resume varios
#           instrumentos con un total general) + las fotos de los cheques
#           físicos que integran ese depósito. Acá hay que "fusionar":
#           un solo movimiento por cada instrumento de la liquidación,
#           completado con los datos de la foto que tenga el mismo monto.

HERRAMIENTA_CHEQUES_WHATSAPP = {
    "name": "registrar_cheques_whatsapp",
    "description": (
        "Registra los cheques de este lote de WhatsApp. Si el lote incluye un "
        "comprobante de liquidación/depósito con un total general, fusioná esa "
        "liquidación con las fotos de los cheques físicos (un movimiento por "
        "cada instrumento de la liquidación, ni más ni menos). Si el lote son "
        "solo cheques sueltos o una tabla de home banking, generá un cheque "
        "por cada uno."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "total_declarado": {
                "type": ["number", "null"],
                "description": (
                    "Si alguno de los archivos es un comprobante de liquidación/depósito "
                    "con un TOTAL general explícito, poné ese total acá (número puro, sin "
                    "separadores de miles). Si no hay ningún documento de ese tipo en el "
                    "lote (por ejemplo, son solo fotos de cheques sueltos), dejá este campo "
                    "en null."
                ),
            },
            "cheques": {
                "type": "array",
                "description": "Un objeto por cada cheque detectado en el lote.",
                "items": {
                    "type": "object",
                    "properties": {
                        "numero_imagen": {
                            "type": ["integer", "null"],
                            "description": (
                                "Número de archivo (1 para el primero enviado, 2 para el "
                                "segundo, etc.) de la FOTO DEL CHEQUE FÍSICO que corresponde "
                                "a este cheque, si existe una foto propia de ese cheque en el "
                                "lote. Si este cheque viene SOLO de un comprobante de "
                                "liquidación y no tiene foto propia en el lote, dejá este "
                                "campo en null. Nunca pongas acá el número de imagen del "
                                "comprobante de liquidación en sí."
                            ),
                        },
                        "banco_origen": {"type": "string"},
                        "codigo_banco": {"type": "string"},
                        "codigo_sucursal": {"type": "string"},
                        "numero_cuenta": {
                            "type": "string",
                            "description": "Solo números, SIN guiones ni espacios.",
                        },
                        "numero_identificador": {
                            "type": "string",
                            "description": "El número del cheque.",
                        },
                        "monto": {
                            "type": "number",
                            "description": "Número decimal puro, sin separadores de miles.",
                        },
                        "fecha_emision": {
                            "type": ["string", "null"],
                            "description": "Formato 'AAAA-MM-DD'. Si el año viene con 2 dígitos, completalo a 4.",
                        },
                        "fecha_pago": {
                            "type": ["string", "null"],
                            "description": "Formato 'AAAA-MM-DD'. Si el cheque no aclara fecha de pago diferida, usá la misma que fecha_emision.",
                        },
                        "cuit_emisor": {
                            "type": ["string", "null"],
                            "description": "11 dígitos. Podés incluir los guiones tal cual figuran (ej: '20-12345678-9').",
                        },
                        "razon_social_emisor": {
                            "type": ["string", "null"],
                            "description": (
                                "El texto impreso junto al CUIT, en la zona de firma/datos del "
                                "titular del cheque. NUNCA el nombre que sigue a 'Páguese a' o "
                                "'A la orden de' (ese es el beneficiario, no el emisor)."
                            ),
                        },
                    },
                    "required": ["monto", "numero_identificador"],
                },
            },
        },
        "required": ["total_declarado", "cheques"],
    },
}


def instrucciones_cheques_whatsapp(cliente_tag: str) -> str:
    return f"""
Sos un auditor contable experto de BC Combustibles, especializado en leer cheques y comprobantes bancarios argentinos que llegan por WhatsApp. Cliente de este lote: '{cliente_tag}'.

Vas a recibir uno o varios archivos (fotos o PDFs). Pueden darse 3 situaciones distintas:

CASO A — Cheques físicos sueltos:
Una o varias fotos, cada una con uno o varios cheques físicos fotografiados (sin ningún comprobante de liquidación de por medio). Generá un cheque por cada uno que veas.

CASO B — Tabla de home banking:
Una captura de pantalla de un listado/tabla de cheques (por ejemplo, cheques electrónicos emitidos, vistos en la web de un banco). Cada FILA de esa tabla es un cheque — generá un cheque por cada fila, usando los datos de esa fila (número, cuenta, razón social/CUIT si figura, fecha, monto).

CASO C — Liquidación/depósito + fotos de cheques físicos:
Si alguno de los archivos es un comprobante de LIQUIDACIÓN o RESUMEN DE DEPÓSITO (trae un TOTAL general y una lista de instrumentos, pero con poco detalle de cada uno — a veces sin ni siquiera el nombre del emisor), y los demás archivos son fotos de cheques físicos:
- Generá EXACTAMENTE un cheque por cada instrumento que figura en la liquidación (ni más, ni menos, ni duplicados).
- Para completar los datos de cada cheque, buscá entre las fotos de cheques físicos la que tenga el MISMO MONTO que ese instrumento de la liquidación, y usá los datos de esa foto (emisor, CUIT, número de cheque, banco, cuenta, fechas).
- Si un instrumento de la liquidación no tiene ninguna foto de cheque con el mismo monto, igual generá el cheque con el monto de la liquidación, dejando emisor/cuit/numero_identificador en null si no los podés determinar.
- Completá "total_declarado" con el TOTAL general que figura en la liquidación.

REGLAS DE ORO PARA LEER CADA CHEQUE FÍSICO (aplican en CASO A y CASO C):
1. El Emisor del cheque NUNCA es el nombre que sigue a "Páguese a" o "A la orden de". Ignorá ese nombre.
2. Andá a la parte INFERIOR del cheque (junto a la firma o el logo del banco/CUIT).
3. Extraé de ahí el CUIT (11 dígitos) y la Razón Social del EMISOR real.
4. Si el cheque no especifica una fecha de pago diferido, "fecha_pago" debe ser igual a "fecha_emision".
5. "numero_cuenta": solo números, SIN guiones ni espacios.

REGLA GENERAL: si dudás de un dato, dejalo en null. NO inventes.

Usá siempre la herramienta "registrar_cheques_whatsapp" para responder. No respondas con texto libre.
""".strip()
