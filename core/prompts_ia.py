"""
core/prompts_ia.py

Acá viven los prompts que se le mandan a Gemini y a Claude. Antes estaban
escritos sueltos adentro de utils_bcra.py y lector.py; ahora viven acá para
que, si el día de mañana hay que ajustar una regla, se toque un solo lugar.

Nota: el prompt de proveedores (versión vieja, Gemini) lo usa
modulos/proveedores.py — que Diego va a sacar del sistema, no se va a migrar.
La herramienta HERRAMIENTA_CHEQUES_WHATSAPP y las instrucciones
INSTRUCCIONES_CHEQUES_WHATSAPP las usa webhook.py (bot de WhatsApp, con
Claude/Anthropic). La herramienta HERRAMIENTA_LECTURA_REMITO la usa
modulos/resumen.py (migrado de Gemini a Claude en agosto 2026). La
herramienta HERRAMIENTA_LECTURA_CHEQUES_BCRA la usa utils_bcra.py, para el
escáner de cheques del módulo Verificación BCRA (migrado de Gemini a Claude
en agosto 2026).
"""

# ==========================================
# 1. LECTURA DE CHEQUES — VERSIÓN VIEJA (Gemini)
# ==========================================
# NOTA (agosto 2026): este prompt de texto libre ya NO lo usa utils_bcra.py,
# que migró a Claude con la herramienta HERRAMIENTA_LECTURA_CHEQUES_BCRA (ver
# sección 6, al final del archivo). Se deja acá por si quedara alguna otra
# referencia suelta — no se detectó ninguna esta sesión.
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
# NOTA (agosto 2026): Diego confirmó que modulos/proveedores.py se va a sacar
# del sistema y no se va a usar más. Este prompt queda acá sin tocar por ahora
# — cuando se saque el módulo, este bloque también se puede borrar.
PROMPT_FACTURAS_PROVEEDORES = (
    "Eres auditor contable. Objetivo: leer FACTURA DE COMPRA. "
    "BC COMBUSTIBLES es RECEPTOR. Buscá CUIT, Fecha, Nº de Factura y Totales. "
    "Extraé JSON puro."
)


# ==========================================
# 3. GENERADOR DE RESUMEN A CLIENTES / REMITOS — VERSIÓN VIEJA (Gemini)
# ==========================================
# NOTA (agosto 2026): este prompt de texto libre ya NO lo usa
# modulos/resumen.py, que migró a Claude con la herramienta
# HERRAMIENTA_LECTURA_REMITO (más abajo, sección 5). Se deja acá por si
# quedara alguna otra referencia suelta — no se detectó ninguna esta sesión.
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
# El bot recibe distintas situaciones posibles en un mismo lote de fotos:
#   CASO A: solo fotos de cheques físicos sueltos (el caso de siempre).
#   CASO B: una captura de pantalla de home banking con una TABLA de varios
#           cheques (cada fila de la tabla = un cheque).
#   CASO C: un comprobante de LIQUIDACIÓN/depósito (que resume varios
#           instrumentos con un total general) + las fotos de los cheques
#           físicos que integran ese depósito. Acá hay que "fusionar":
#           un solo movimiento por cada instrumento de la liquidación,
#           completado con los datos de la foto que tenga el mismo monto.
#   CASO D: comprobantes que NO son cheques (ej: transferencias bancarias).
#           También se registran, marcados con su tipo real.

HERRAMIENTA_CHEQUES_WHATSAPP = {
    "name": "registrar_cheques_whatsapp",
    "description": (
        "Registra los comprobantes de este lote de WhatsApp. Si el lote incluye un "
        "comprobante de liquidación/depósito con un total general, fusioná esa "
        "liquidación con las fotos de los cheques físicos (un movimiento por "
        "cada instrumento de la liquidación, ni más ni menos). Si el lote son "
        "solo cheques sueltos, transferencias, o una tabla de home banking, "
        "generá un comprobante por cada uno."
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
                "description": "Un objeto por cada comprobante detectado en el lote (cheque, transferencia, etc.).",
                "items": {
                    "type": "object",
                    "properties": {
                        "tipo_comprobante": {
                            "type": "string",
                            "enum": ["Cheque Físico", "Cheque Electrónico", "Transferencia", "Otro"],
                            "description": (
                                "El tipo real de este comprobante. 'Cheque Físico' para un cheque "
                                "fotografiado o de una liquidación de cheques. 'Cheque Electrónico' "
                                "para uno visto en una tabla de home banking. 'Transferencia' para "
                                "un comprobante de transferencia bancaria (sin número de cheque). "
                                "'Otro' si no encaja en ninguno de los anteriores."
                            ),
                        },
                        "numero_imagen": {
                            "type": ["integer", "null"],
                            "description": (
                                "Número de archivo (1 para el primero enviado, 2 para el "
                                "segundo, etc.) de la FOTO FÍSICA que corresponde a este "
                                "comprobante, si existe una foto propia de él en el lote. Si "
                                "este comprobante viene SOLO de un documento de liquidación y "
                                "no tiene foto propia en el lote, dejá este campo en null. Nunca "
                                "pongas acá el número de imagen del comprobante de liquidación en sí."
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
                            "description": (
                                "El número del cheque. Si es una transferencia u otro comprobante "
                                "sin número de cheque, usá el número de operación/comprobante que "
                                "figure, o dejalo vacío si no hay ninguno."
                            ),
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
                            "description": "Formato 'AAAA-MM-DD'. Si el comprobante no aclara fecha de pago diferida, usá la misma que fecha_emision.",
                        },
                        "cuit_emisor": {
                            "type": ["string", "null"],
                            "description": "11 dígitos. Podés incluir los guiones tal cual figuran (ej: '20-12345678-9').",
                        },
                        "razon_social_emisor": {
                            "type": ["string", "null"],
                            "description": (
                                "Para cheques: el texto impreso junto al CUIT, en la zona de firma/datos "
                                "del titular del cheque. NUNCA el nombre que sigue a 'Páguese a' o "
                                "'A la orden de' (ese es el beneficiario, no el emisor). Para "
                                "transferencias: el nombre de quien envía el dinero (titular de la "
                                "cuenta de ORIGEN). Si el comprobante no identifica claramente al "
                                "emisor, dejá este campo en null — no asumas ni inventes."
                            ),
                        },
                        "cuenta_destino": {
                            "type": ["string", "null"],
                            "description": (
                                "SOLO para tipo_comprobante = 'Transferencia'. El número de cuenta "
                                "bancaria de DESTINO (la cuenta a la que entró la plata), tal como "
                                "figura en el comprobante, sin guiones ni espacios. Null si no aplica "
                                "(no es una transferencia) o no figura en el documento. NUNCA pongas "
                                "acá un dato del emisor/origen."
                            ),
                        },
                        "cbu_cvu_destino": {
                            "type": ["string", "null"],
                            "description": (
                                "SOLO para tipo_comprobante = 'Transferencia'. El CBU o CVU de DESTINO "
                                "(a donde entró la plata), sin espacios. Null si no aplica o no figura."
                            ),
                        },
                        "alias_destino": {
                            "type": ["string", "null"],
                            "description": (
                                "SOLO para tipo_comprobante = 'Transferencia'. El alias bancario de la "
                                "cuenta de DESTINO (ej: 'bccombustibles.mp'), tal como figura en el "
                                "comprobante. Null si no aplica o no figura."
                            ),
                        },
                    },
                    "required": ["tipo_comprobante", "monto"],
                },
            },
        },
        "required": ["total_declarado", "cheques"],
    },
}


def instrucciones_cheques_whatsapp(cliente_tag: str) -> str:
    return f"""
Sos un auditor contable experto de BC Combustibles, especializado en leer cheques y comprobantes bancarios argentinos que llegan por WhatsApp. Cliente de este lote: '{cliente_tag}'.

Vas a recibir uno o varios archivos (fotos o PDFs). Pueden darse varias situaciones distintas, incluso mezcladas en un mismo lote:

CASO A — Cheques físicos sueltos:
Una o varias fotos, cada una con uno o varios cheques físicos fotografiados (sin ningún comprobante de liquidación de por medio). Generá un comprobante por cada uno que veas, con tipo_comprobante = "Cheque Físico".

CASO B — Tabla de home banking:
Una captura de pantalla de un listado/tabla de cheques (por ejemplo, cheques electrónicos emitidos, vistos en la web de un banco). Cada FILA de esa tabla es un comprobante — generá uno por cada fila, con tipo_comprobante = "Cheque Electrónico", usando los datos de esa fila (número, cuenta, razón social/CUIT si figura, fecha, monto).

CASO C — Liquidación/depósito + fotos de cheques físicos:
Si alguno de los archivos es un comprobante de LIQUIDACIÓN o RESUMEN DE DEPÓSITO (trae un TOTAL general y una lista de instrumentos, pero con poco detalle de cada uno — a veces sin ni siquiera el nombre del emisor), y los demás archivos son fotos de cheques físicos:
- Generá EXACTAMENTE un comprobante por cada instrumento que figura en la liquidación (ni más, ni menos, ni duplicados), con tipo_comprobante = "Cheque Físico".
- Para completar los datos de cada uno, buscá entre las fotos de cheques físicos la que tenga el MISMO MONTO que ese instrumento de la liquidación, y usá los datos de esa foto (emisor, CUIT, número de cheque, banco, cuenta, fechas).
- Si un instrumento de la liquidación no tiene ninguna foto con el mismo monto, igual generá el comprobante con el monto de la liquidación, dejando emisor/cuit/numero_identificador en null si no los podés determinar.
- Completá "total_declarado" con el TOTAL general que figura en la liquidación.

CASO D — Comprobantes que no son cheques (Transferencias):
Si alguno de los archivos es una transferencia bancaria (comprobante de "Transferencia enviada", "Transferencia recibida", "Endoso de eCheq/echeq a...", o similar, SIN número de cheque), generá un comprobante con tipo_comprobante = "Transferencia". Usá como "numero_identificador" el número de operación/comprobante si figura.

Datos del EMISOR (quien envía la plata — la cuenta de ORIGEN):
- "razon_social_emisor" y "cuit_emisor": el nombre y CUIT de quien envía el dinero.
- ⚠️ MUY IMPORTANTE: si en el comprobante aparece el nombre "BONAZZOLA FLORENCIA Y BUYATTI ANDRES" (o cualquier variante parecida), ESE ES BC COMBUSTIBLES — es el nombre bajo el cual BC recibe pagos, NUNCA es el emisor. Si ese nombre (o el nombre de BC) aparece asociado a "Beneficiario", "Destino", "Titular de la cuenta destino", o similar, corresponde a los campos de DESTINO de abajo, no a "razon_social_emisor".
- Si el comprobante no identifica con claridad quién es el verdadero emisor (por ejemplo, solo muestra un número de cuenta de origen sin nombre ni CUIT asociado), dejá "razon_social_emisor" y "cuit_emisor" en null — no asumas que es el cliente del lote, no inventes.

Datos del DESTINO (la cuenta de BC a la que entró la plata):
- "cuenta_destino", "cbu_cvu_destino", "alias_destino": completá los que figuren en el comprobante (puede venir uno, dos, o los tres juntos). Dejalos en null si no aplican o no figuran. NUNCA pongas ahí datos del emisor/origen.

REGLAS DE ORO PARA LEER CADA CHEQUE FÍSICO (aplican en CASO A y CASO C):
1. El Emisor del cheque NUNCA es el nombre que sigue a "Páguese a" o "A la orden de". Ignorá ese nombre.
2. Andá a la parte INFERIOR del cheque (junto a la firma o el logo del banco/CUIT).
3. Extraé de ahí el CUIT (11 dígitos) y la Razón Social del EMISOR real.
4. Si el cheque no especifica una fecha de pago diferido, "fecha_pago" debe ser igual a "fecha_emision".
5. "numero_cuenta": solo números, SIN guiones ni espacios.

REGLA GENERAL: si dudás de un dato, dejalo en null. NO inventes. Elegí siempre el tipo_comprobante que mejor describa cada uno — no asumas que todo es un cheque.

Usá siempre la herramienta "registrar_cheques_whatsapp" para responder. No respondas con texto libre.
""".strip()


# ==========================================
# 5. LECTURA DE REMITOS PARA EL GENERADOR DE RESUMEN (usado por
#    modulos/resumen.py, con Claude — migrado desde Gemini en agosto 2026)
# ==========================================
# Reemplaza al PROMPT_AUDITORIA_REMITOS de la sección 3, con el mismo enfoque
# de "herramienta forzada" que ya usa webhook.py: en vez de pedirle a la IA
# que devuelva JSON en texto libre y después buscar "{" y "}" a mano, le
# damos una estructura fija que está obligada a llenar. Esto evita errores
# de parseo y hace innecesario "limpiar" números a mano (comas, puntos,
# separadores de miles), porque el campo ya viene tipado como número.

HERRAMIENTA_LECTURA_REMITO = {
    "name": "registrar_lectura_remito",
    "description": (
        "Registra los datos extraídos de un remito o factura de venta a un cliente "
        "de BC Combustibles, a partir de la foto del comprobante."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "fecha": {
                "type": ["string", "null"],
                "description": "Fecha del comprobante, tal como figura en el documento.",
            },
            "razon_social": {
                "type": ["string", "null"],
                "description": (
                    "Nombre del CLIENTE receptor. BC COMBUSTIBLES siempre es el "
                    "emisor de este tipo de comprobante, nunca el receptor."
                ),
            },
            "importe": {
                "type": ["number", "null"],
                "description": "Monto total en números, sin separadores de miles ni símbolo de moneda.",
            },
            "comprobante": {
                "type": ["string", "null"],
                "description": "Número de comprobante.",
            },
            "litros": {
                "type": ["number", "null"],
                "description": (
                    "Suma TOTAL de litros de combustible. NO sumes aceites, aditivos "
                    "ni otros artículos, solo combustibles."
                ),
            },
            "detalle_productos": {
                "type": ["string", "null"],
                "description": (
                    "Resumen de los combustibles y sus litros exactos. Ejemplo: "
                    "'Euro Diesel G3: 201 L | Gas Oil 500 G2: 81.5 L'. Si es un solo "
                    "producto, poné solo ese."
                ),
            },
            "observaciones_ia": {
                "type": "string",
                "description": (
                    "Evaluá TODOS los ítems facturados y aplicá esta regla estricta: "
                    "1) Si SOLO cargó 'Gas Oil 500 G2' (Gasoil normal), devolvé cadena "
                    "vacía. 2) Si hay 2 o más combustibles diferentes, devolvé "
                    "'Atención. La factura tiene varios productos.' 3) Si cargó SOLO "
                    "Euro, devolvé 'Atención. El producto cargado es Euro, verifique.' "
                    "4) Si cargó SOLO Nafta, devolvé 'Atención. La factura contiene "
                    "Nafta.' 5) Si hay artículos extra (aceites, filtros, etc.), "
                    "devolvé 'Atención. La factura contiene artículos extra: "
                    "[detallar los extra].'"
                ),
            },
        },
        "required": [
            "fecha", "razon_social", "importe", "comprobante",
            "litros", "detalle_productos", "observaciones_ia",
        ],
    },
}


def instrucciones_lectura_remito() -> str:
    return """
Sos un auditor experto de BC Combustibles. El Emisor de todos los comprobantes es 'BC COMBUSTIBLES'. Tu trabajo es leer el comprobante adjunto y encontrar los datos del CLIENTE Receptor y de la carga de combustible.

REGLA DE ORO: BC COMBUSTIBLES nunca es el receptor, siempre es el emisor. El receptor es el cliente al que hay que identificar.

Si algún dato no es legible con seguridad, dejalo en null (excepto "observaciones_ia", que siempre tiene que llevar un valor, según la regla que ya tenés en la descripción de ese campo).

Usá siempre la herramienta "registrar_lectura_remito" para responder. No respondas con texto libre.
""".strip()


# ==========================================
# 6. LECTURA DE CHEQUES PARA EL ESCÁNER DE VERIFICACIÓN BCRA (usado por
#    utils_bcra.py, con Claude — migrado desde Gemini en agosto 2026)
# ==========================================
# Reemplaza al PROMPT_LECTURA_CHEQUES de la sección 1, con el mismo enfoque
# de "herramienta forzada" que ya usan webhook.py y modulos/resumen.py.
# OJO: este es un caso DISTINTO al de HERRAMIENTA_CHEQUES_WHATSAPP — acá el
# objetivo es identificar rápido número de cheque + emisor + CUIT para
# consultarlos contra el BCRA, no registrar un cobro completo con banco,
# cuenta, montos y fechas.

HERRAMIENTA_LECTURA_CHEQUES_BCRA = {
    "name": "registrar_cheques_para_verificacion",
    "description": (
        "Registra los cheques físicos detectados en la foto, para consultarlos "
        "después contra la Central de Deudores del BCRA."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cheques": {
                "type": "array",
                "description": "Un objeto por cada cheque físico visible en la foto, de arriba hacia abajo.",
                "items": {
                    "type": "object",
                    "properties": {
                        "numero_cheque": {
                            "type": ["string", "null"],
                            "description": (
                                "Número del cheque. Generalmente está en la esquina superior "
                                "derecha o en la serie de números de la banda inferior."
                            ),
                        },
                        "emisor": {
                            "type": ["string", "null"],
                            "description": (
                                "Razón social del EMISOR real del cheque. NUNCA el nombre que "
                                "sigue a 'Páguese a' (ese es el beneficiario). Andá a la parte "
                                "INFERIOR del cheque, junto a la firma o el logo del banco, y "
                                "extraé de ahí el nombre del titular."
                            ),
                        },
                        "cuit": {
                            "type": ["string", "null"],
                            "description": (
                                "CUIT de 11 dígitos del emisor (suelen empezar con 20, 23, 27 o "
                                "30), tomado de la misma zona que la razón social del emisor."
                            ),
                        },
                    },
                    "required": ["numero_cheque", "emisor", "cuit"],
                },
            },
        },
        "required": ["cheques"],
    },
}


def instrucciones_lectura_cheques_bcra() -> str:
    return """
Actuá como un auditor senior de BC Combustibles. Analizá esta foto que contiene un lote de cheques físicos.

REGLAS DE ORO (Aislamiento de Datos):
1. Analizá los cheques visualmente de arriba hacia abajo.
2. El Emisor del cheque NUNCA es el nombre que sigue a "Páguese a". Ignorá ese nombre gigante.
3. Andá siempre a la parte INFERIOR del cheque (junto a la firma o el logo del banco).
4. Extraé de ahí el CUIT (11 dígitos, suelen empezar con 20, 23, 27, 30) y la Razón Social del EMISOR.
5. Buscá el NÚMERO DEL CHEQUE. Generalmente está en la esquina superior derecha o en la serie de números de la banda inferior.

Si un dato no es legible con un 100% de seguridad, dejalo en null en ese campo específico. NO inventes.

Usá siempre la herramienta "registrar_cheques_para_verificacion" para responder. No respondas con texto libre.
""".strip()
