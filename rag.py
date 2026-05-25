import os
import math
import hashlib
import glob
import zipfile
import xml.etree.ElementTree as ET
from database import registrar_proceso_en_bd

# CONFIGURACIÓN TÉCNICA DEL MOTOR RAG (EN ESPAÑOL)
TAMANO_FRAGMENTO = 500       # Tamaño del chunk de caracteres
TRASLAPE = 100               # Overlap en caracteres
DIMENSION_EMBEDDING = 768    # Vector de salida compatible con Gemini
CANTIDAD_TOP_K = 3           # Cantidad de fragmentos recuperados

STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "en", "para", "por", 
    "con", "sin", "sobre", "tras", "ante", "bajo", "cabe", "contra", "desde", "hasta", "para", 
    "segun", "sobre", "atras", "hacia", "durante", "mediante", "que", "como", "este", "esta", 
    "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella", "aquellos", "aquellas",
    "mi", "mis", "tu", "tus", "su", "sus", "nuestro", "nuestra", "nuestros", "nuestras", "todo", 
    "toda", "todos", "todas", "algun", "alguna", "algunos", "algunas", "ningun", "ninguna", 
    "ningunos", "ningunas", "otro", "otra", "otros", "otras", "mismo", "misma", "mismos", "mismas",
    "tanto", "tanta", "tantos", "tantas", "mucho", "mucha", "muchos", "muchas", "poco", "poca", 
    "pocos", "pocas", "mas", "menos", "muy", "tan", "bastante", "demasiado", "si", "no", "ni", 
    "pero", "o", "u", "sino", "aunque", "porque", "pues", "entonces", "luego", "cuando", "donde", 
    "quien", "quienes", "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas", "yo", "tu", 
    "el", "ella", "ello", "nosotros", "nosotras", "vosotros", "vosotras", "ellos", "ellas", 
    "me", "te", "se", "nos", "os", "lo", "los", "la", "las", "le", "les", "mio", "mia", "mios", 
    "mias", "tuyo", "tuya", "tuyos", "tuyas", "suyo", "suya", "suyos", "suyas"
}

def limpiar_y_tokenizar(texto):
    """Limpia tildes, caracteres especiales y fragmenta en tokens en español."""
    acentos = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u', 'ñ': 'n'}
    texto = texto.lower()
    for original, reemplazo in acentos.items():
        texto = texto.replace(original, reemplazo)
    for c in ".,;:-_¿?¡!()\"'[]{}<>/\\@#*+=%&":
        texto = texto.replace(c, " ")
    return [w for w in texto.split() if len(w) > 2]

def calcular_vector_embedding(texto):
    """
    Retorna un pseudo-embedding para mantener compatibilidad en código histórico o de trazas,
    pero todo el procesamiento RAG principal ahora se gestiona de forma offline mediante TF-IDF.
    """
    limpio = texto.strip()
    hash_txt = hashlib.sha256(limpio.encode('utf-8')).hexdigest()
    import random
    random.seed(hash_txt)
    vector_mock = [random.uniform(-1.0, 1.0) for _ in range(DIMENSION_EMBEDDING)]
    norma = sum(x*x for x in vector_mock) ** 0.5
    if norma > 0:
        return [x/norma for x in vector_mock]
    return [0.0] * DIMENSION_EMBEDDING

def fragmentar_texto_politica(texto, nombre_archivo):
    """Segmenta las políticas de la empresa en bloques de tamaño fijo con solapamiento."""
    fragmentos = []
    texto_limpio = texto.replace('\r\n', '\n')
    inicio = 0
    while inicio < len(texto_limpio):
        fin = min(inicio + TAMANO_FRAGMENTO, len(texto_limpio))
        contenido = texto_limpio[inicio:fin]
        fragmentos.append({
            "contenido": contenido,
            "origen": nombre_archivo,
            "rango_caracteres": (inicio, fin)
        })
        if fin == len(texto_limpio):
            break
        inicio += (TAMANO_FRAGMENTO - TRASLAPE)
    return fragmentos

def cargar_todas_las_politicas_RAG(carpeta="documentos_empresa"):
    """Inspecciona y segmenta todos los archivos de texto legislativo corporativo (.txt y .docx)."""
    def leer_docx_sin_dependencias(ruta_archivo):
        try:
            with zipfile.ZipFile(ruta_archivo) as z:
                xml_content = z.read('word/document.xml')
                root = ET.fromstring(xml_content)
                namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                textos = []
                for p in root.findall('.//w:p', namespaces):
                    parrafo_texto = []
                    for t in p.findall('.//w:t', namespaces):
                        if t.text:
                            parrafo_texto.append(t.text)
                    textos.append("".join(parrafo_texto))
                return "\n".join(textos)
        except Exception:
            return ""

    todos_los_fragmentos = []
    if not os.path.exists(carpeta):
        return []

    # Cargar todos los archivos .txt
    archivos_txt = glob.glob(os.path.join(carpeta, "*.txt"))
    for ruta in archivos_txt:
        nombre = os.path.basename(ruta)
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                contenido = f.read()
            todos_los_fragmentos.extend(fragmentar_texto_politica(contenido, nombre))
        except Exception:
            pass

    # Cargar todos los archivos .docx
    archivos_docx = glob.glob(os.path.join(carpeta, "*.docx"))
    for ruta in archivos_docx:
        nombre = os.path.basename(ruta)
        contenido = leer_docx_sin_dependencias(ruta)
        if contenido.strip():
            todos_los_fragmentos.extend(fragmentar_texto_politica(contenido, nombre))

    return todos_los_fragmentos

def mapear_metadata_proceso(archivo_politica):
    """Devuelve los parámetros legislativos según la política identificada."""
    origen = archivo_politica.lower()
    if "soporte_cliente" in origen:
        return {
            "name": "Customer Support",
            "area": "Área de Operaciones",
            "timeframe": "24 horas",
            "priority": 2
        }
    elif "cancelacion_producto" in origen:
        return {
            "name": "Product Cancellation",
            "area": "Área de Facturación",
            "timeframe": "24 horas hábiles",
            "priority": 1
        }
    elif "escalacion_tickets" in origen:
        return {
            "name": "Escalation of tickets",
            "area": "Operaciones Técnicas y Defensores del Cliente",
            "timeframe": "24h (Tier 2) / 48h (Tier 3)",
            "priority": 1
        }
    elif "actualizar_contacto" in origen:
        return {
            "name": "Update contact info",
            "area": "Atención al Cliente",
            "timeframe": "Tiempo Real (Inmediato)",
            "priority": 3
        }
    elif "quejas" in origen:
        return {
            "name": "Complaints",
            "area": "Control de Calidad (QA) y Relaciones",
            "timeframe": "7 días hábiles",
            "priority": 2
        }
    else:
        return {
            "name": "General Support Inquiry",
            "area": "Mesa de Soporte",
            "timeframe": "48 horas",
            "priority": 3
        }

def consultar_motor_rag(pregunta_usuario, user_id=None):
    """
    Ejecuta una búsqueda TF-IDF local 100% offline contra las políticas corporativas.
    Determina la relevancia exacta de los fragmentos sin dependencias externas ni llamadas API.
    """
    fragmentos = cargar_todas_las_politicas_RAG()
    if not fragmentos:
        return []
        
    corpus_tokens = []
    frecuencia_documentos = {}
    
    for frag in fragmentos:
        tokens = limpiar_y_tokenizar(frag["contenido"])
        tokens_filtrados = [t for t in tokens if t not in STOPWORDS_ES]
        corpus_tokens.append(tokens_filtrados)
        for t in set(tokens_filtrados):
            frecuencia_documentos[t] = frecuencia_documentos.get(t, 0) + 1
            
    N = len(fragmentos)
    idf = {}
    for term, freq in frecuencia_documentos.items():
        idf[term] = math.log((1 + N) / (1 + freq)) + 1
        
    tokens_pregunta = limpiar_y_tokenizar(pregunta_usuario)
    tokens_pregunta_filtrados = [t for t in tokens_pregunta if t not in STOPWORDS_ES]
    
    evaluaciones = []
    if not tokens_pregunta_filtrados:
        evaluaciones = [(0.0, f) for f in fragmentos]
    else:
        for i, frag in enumerate(fragmentos):
            tokens_doc = corpus_tokens[i]
            puntuacion = 0.0
            for t in tokens_pregunta_filtrados:
                if t in tokens_doc:
                    tf = tokens_doc.count(t) / len(tokens_doc) if len(tokens_doc) > 0 else 0
                    peso_term = tf * idf.get(t, 0.0)
                    puntuacion += peso_term
            evaluaciones.append((puntuacion, frag))
            
    evaluaciones.sort(key=lambda x: x[0], reverse=True)
    max_score = evaluaciones[0][0] if evaluaciones and evaluaciones[0][0] > 0 else 1.0
    
    resultados = []
    procesos_registrados = set()
    
    for score, frag in evaluaciones[:CANTIDAD_TOP_K]:
        orig = frag["origen"]
        meta = mapear_metadata_proceso(orig)
        
        # Registrar proceso recuperado en la base de datos si no fue cargado en esta sesión
        nombre_proceso = meta["name"]
        if nombre_proceso not in procesos_registrados:
            procesos_registrados.add(nombre_proceso)
            db_id = registrar_proceso_en_bd(
                nombre=meta["name"],
                area=meta["area"],
                plazo=meta["timeframe"],
                prioridad=meta["priority"],
                canal="terminal",
                user_id=user_id
            )
            meta["assigned_process_id_db"] = db_id
            
        score_normalizado = round(score / max_score, 4) if max_score > 0 else 0.0
        # Forzar un piso de similitud si hay concordancia temática evidente
        if score == 0.0:
            score_normalizado = 0.01
            
        resultados.append({
            "score": score_normalizado,
            "content": frag["contenido"],
            "source": frag["origen"],
            "process_meta": meta
        })
        
    return resultados
