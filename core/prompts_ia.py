"""
core/prompts_ia.py

Acá viven los prompts que se le mandan a Gemini. Antes estaban escritos
sueltos adentro de utils_bcra.py y lector.py; ahora viven acá para que,
si el día de mañana hay que ajustar una regla, se toque un solo lugar.

Nota: los dos prompts nuevos de abajo (proveedores y remitos) todavía
NO los usa ningún archivo — quedan preparados para conectarlos a
lector.py en una próxima sesión, sin apuro.
"""

# ==========================================
# 1. LECTURA DE CHEQUES (ya en uso por utils_bcra.py)
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
# 2. LECTURA DE FACTURAS DE PROVEEDORES (todavía no conectado)
# ==========================================
PROMPT_FACTURAS_PROVEEDORES = (
    "Eres auditor contable. Objetivo: leer FACTURA DE COMPRA. "
    "BC COMBUSTIBLES es RECEPTOR. Buscá CUIT, Fecha, Nº de Factura y Totales. "
    "Extraé JSON puro."
)


# ==========================================
# 3. GENERADOR DE RESUMEN A CLIENTES / REMITOS (todavía no conectado)
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
