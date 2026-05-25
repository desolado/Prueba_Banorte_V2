import sqlite3
import datetime
import uuid
import json

# Nombre de la base de datos central de procesos e historial SQLite
DB_ARCHIVADOR = "agent_system.db"

def obtener_conexion():
    """Establece conexión nativa con la base de datos SQLite."""
    conn = sqlite3.connect(DB_ARCHIVADOR)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_base_de_datos():
    """Crea y consolida las tablas estructurales si no existen en el sistema."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    # 1. Tabla de Procesos de Negocio Registrados
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processes (
        process_id TEXT PRIMARY KEY,
        process_name TEXT NOT NULL,
        area TEXT NOT NULL,
        expected_timeframe_for_solution TEXT NOT NULL,
        channel TEXT NOT NULL,
        priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 3),
        user_id INTEGER,
        timestamp TEXT
    );
    """)
    
    # Verificar si la columna user_id y timestamp ya existen en la tabla processes o si hay que migrar/agregar
    try:
        cursor.execute("PRAGMA table_info(processes)")
        columnas_procs = [col["name"] for col in cursor.fetchall()]
        if "user_id" not in columnas_procs:
            cursor.execute("ALTER TABLE processes ADD COLUMN user_id INTEGER;")
        if "timestamp" not in columnas_procs:
            cursor.execute("ALTER TABLE processes ADD COLUMN timestamp TEXT;")
            fecha_defecto = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            cursor.execute("UPDATE processes SET timestamp = ? WHERE timestamp IS NULL", (fecha_defecto,))
    except Exception:
        pass
    
    # 2. Tabla de Conversaciones (Memoria viva de Agente)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        sender TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL
    );
    """)

    # 3. Tabla de Usuarios (Información del cliente)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER UNIQUE,
        correo TEXT PRIMARY KEY,
        nombre_completo TEXT NOT NULL,
        telefono TEXT NOT NULL,
        estatus_cuenta TEXT NOT NULL,
        tickets_activos TEXT NOT NULL,
        created_at TEXT
    );
    """)
    
    # Migrar tabla 'users' vieja si no tiene la columna 'user_id' o 'created_at'
    try:
        cursor.execute("PRAGMA table_info(users)")
        columnas_users = [col["name"] for col in cursor.fetchall()]
        if "user_id" not in columnas_users:
            cursor.execute("ALTER TABLE users ADD COLUMN user_id INTEGER;")
            cursor.execute("SELECT correo FROM users")
            filas_users = cursor.fetchall()
            id_actual = 1000
            for row in filas_users:
                cursor.execute("UPDATE users SET user_id = ? WHERE correo = ?", (id_actual, row["correo"]))
                id_actual += 1
        if "created_at" not in columnas_users:
            cursor.execute("ALTER TABLE users ADD COLUMN created_at TEXT;")
            fecha_defecto = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            cursor.execute("UPDATE users SET created_at = ? WHERE created_at IS NULL", (fecha_defecto,))
    except Exception:
        pass
    
    # 4. Tabla de Procesos Operativos Internos Inmutables
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS procesos_operativos (
            id_del_proceso TEXT PRIMARY KEY,
            nombre_proceso TEXT NOT NULL,
            area_responsable TEXT NOT NULL,
            tiempo_promedio_resolución TEXT NOT NULL,
            canal_de_atención TEXT NOT NULL,
            nivel_de_criticidad INTEGER NOT NULL
        );
        """)
        
        cursor.execute("SELECT COUNT(*) as count FROM procesos_operativos;")
        if cursor.fetchone()["count"] == 0:
            procesos_iniciales = [
                ("P_001", "atención a aclaraciones", "Servicio a cliente", "2 horas", "SMS, EMAIL", 3),
                ("P_002", "cancelación de productos", "Servicio a cliente", "24 horas", "SMS, EMAIL", 3),
                ("P_003", "escalamiento de incidencias", "Supervisores", "7 días hábiles", "SMS, EMAIL", 1),
                ("P_004", "actualización de datos", "Finanzas", "inmediato", "SMS, EMAIL", 3),
                ("P_005", "gestión de quejas internas", "Recursos Humanos", "7 días hábiles", "SMS, EMAIL", 2)
            ]
            cursor.executemany("""
            INSERT INTO procesos_operativos (id_del_proceso, nombre_proceso, area_responsable, tiempo_promedio_resolución, canal_de_atención, nivel_de_criticidad)
            VALUES (?, ?, ?, ?, ?, ?);
            """, procesos_iniciales)
    except Exception:
        pass
    
    conn.commit()
    conn.close()

def buscar_usuario_por_correo(correo):
    """Busca un registro de usuario en la tabla 'users' por su correo de forma segura."""
    inicializar_base_de_datos()
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE correo = ?", (correo,))
    fila = cursor.fetchone()
    conn.close()
    if fila:
        return dict(fila)
    return None

def buscar_usuario_por_telefono(telefono):
    """Busca si existe algún registro de usuario con el número de teléfono dado."""
    inicializar_base_de_datos()
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telefono = ?", (telefono,))
    fila = cursor.fetchone()
    conn.close()
    if fila:
        return dict(fila)
    return None

def registrar_o_actualizar_usuario(correo, nombre_completo, telefono, estatus_cuenta="activa", tickets_activos="[]"):
    """Inserta o actualiza la información completa de un usuario en 'users', asignando un ID único de forma secuencial con su fecha de creación."""
    inicializar_base_de_datos()
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE correo = ?", (correo,))
    fila = cursor.fetchone()
    if fila:
        # El usuario ya existe, actualizamos sus datos pero dejamos intacto su user_id y su created_at
        cursor.execute("""
        UPDATE users
        SET nombre_completo = ?, telefono = ?, estatus_cuenta = ?, tickets_activos = ?
        WHERE correo = ?
        """, (nombre_completo, telefono, estatus_cuenta, tickets_activos, correo))
    else:
        # Nuevo usuario: calculamos el siguiente ID único empezando en 1000
        cursor.execute("SELECT MAX(user_id) FROM users")
        max_id_row = cursor.fetchone()
        max_id = max_id_row[0] if max_id_row and max_id_row[0] is not None else None
        if max_id is None:
            nuevo_user_id = 1000
        else:
            nuevo_user_id = max(1000, max_id + 1)
            
        fecha_actual = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        cursor.execute("""
        INSERT INTO users (user_id, correo, nombre_completo, telefono, estatus_cuenta, tickets_activos, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (nuevo_user_id, correo, nombre_completo, telefono, estatus_cuenta, tickets_activos, fecha_actual))
    conn.commit()
    conn.close()

def registrar_proceso_en_bd(nombre, area, plazo, prioridad, canal="terminal", user_id=None):
    """
    Inserta o actualiza un registro de proceso de negocio en la tabla SQL 'processes'.
    Asigna un ID único y legible, lo vincula al ID numérico del usuario, y guarda la fecha/hora.
    """
    inicializar_base_de_datos()
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    slug_nombre = nombre.lower().replace(" ", "_").replace("/", "_")
    proceso_id = f"proc_{slug_nombre}_{str(uuid.uuid4())[:8]}"
    
    # Validación de límites de prioridad (1-Alta, 2-Media, 3-Baja)
    val_prioridad = int(prioridad)
    if val_prioridad < 1: val_prioridad = 1
    if val_prioridad > 3: val_prioridad = 3
    
    fecha_actual = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    cursor.execute("""
    INSERT INTO processes (process_id, process_name, area, expected_timeframe_for_solution, channel, priority, user_id, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (proceso_id, nombre, area, plazo, canal, val_prioridad, user_id, fecha_actual))
    
    conn.commit()
    conn.close()
    return proceso_id

def agregar_mensaje_a_conversacion(conversation_id, user_id, sender, mensaje, timestamp=None):
    """Inserta un mensaje entrante o saliente para mantener memoria conversacional."""
    if not timestamp:
        timestamp = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        
    inicializar_base_de_datos()
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO conversations (conversation_id, user_id, sender, message, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """, (conversation_id, user_id, sender, mensaje, timestamp))
    conn.commit()
    conn.close()

def obtener_memoria_conversacion(user_id_or_email):
    """Recupera la secuencia histórica del chat para alimentar el contexto del Agente 1, basada en el correo del usuario (user_id)."""
    inicializar_base_de_datos()
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT sender, message, timestamp FROM conversations
    WHERE user_id = ? OR conversation_id = ?
    ORDER BY id ASC
    """, (user_id_or_email, user_id_or_email))
    filas = cursor.fetchall()
    conn.close()
    return [{"remitente": f["sender"], "texto": f["message"], "fecha": f["timestamp"]} for f in filas]

def borrar_todas_las_conversaciones():
    """Borra todos los registros en la tabla de conversations."""
    inicializar_base_de_datos()
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()

def obtener_todos_los_procesos():
    """Recibe la lista completa de procesos registrados para inspección CLI o Web."""
    inicializar_base_de_datos()
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM processes")
    filas = cursor.fetchall()
    conn.close()
    return [dict(f) for f in filas]
