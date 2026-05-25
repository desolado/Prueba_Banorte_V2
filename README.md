# Agente de Soporte Multi-Agente Inteligente

Este es un agente de IA diseñado para la orquestación cognitiva multi-agente en soporte corporativo. Está implementado en **Python 3** y utiliza la biblioteca oficial **`google-genai`** para interactuar de forma óptima con los modelos Gemini de última generación, además de componentes internos y almacenamiento local de datos en SQLite.

---

## 📂 Arquitectura Modular de Archivos

Para mantener el código limpio, mantenible y escalable, las funcionalidades del agente se dividen en los siguientes módulos especializados:

1. **`agente.py` (Archivo Maestro / CLI)**:
   - Orquestador central de la ejecución del bucle interactivo por consola (CLI).
   - Coordina el flujo cognitivo secuencial de pensamientos, llamadas a herramientas del Agente 2 y redacción final de respuestas de cara al usuario.

2. **`classifiers.py` (Clasificadores e IA)**:
   - Contiene la lógica inteligente con Gemini utilizando **Structured Outputs** y contratos Pydantic para la clasificación de intenciones (`clasificar_tema_con_gemini`), detección de preguntas específicas (`es_pregunta_especifica_de_procesos`), extracción de datos de contacto (`extraer_datos_contacto_con_gemini`) y de descripción de problemas (`extraer_descripcion_problema_de_cuenta`).
   - Aloja la generación de respuesta compleja final (`generar_respuesta_compleja_gemini`).

3. **`database.py` (Capa de Base de Datos / SQLite)**:
   - Inicializa el esquema de tablas en SQLite y centraliza todas las consultas relacionales (`buscar_usuario_por_correo`, `registrar_o_actualizar_usuario`, `registrar_proceso_en_bd`, `agregar_mensaje_a_conversacion`, etc.).

4. **`rag.py` (Motor de Recuperación / RAG)**:
   - Lógica de tokenización, limpieza y segmentación con overlap (traslape) para documentos empresariales.
   - Ejecuta la búsqueda TF-IDF offline contra manuales corporativos (`consultar_motor_rag`) y asocia metadatos de procesos operativos.

5. **`tools.py` (Herramientas y Acciones del Backend)**:
   - Implementa las funciones ejecutables que interactúan de forma directa con los estados del backend (ej: `tool_cancelar_suscripcion`, `tool_escalar_ticket`, `tool_actualizar_contacto`, `tool_registrar_queja`).

6. **`models.py` (Esquemas de Datos y Pydantic)**:
   - Define las estructuras de tipado estricto Pydantic utilizadas para obligar a Gemini a retornar datos consistentes (Structured Outputs) y asiste en la carga segura de variables de entorno.

---

## 🚀 Características Principales

- **Razonamiento Cognitivo Multi-Agente**: Orquesta pensamientos, llamadas a herramientas RAG locales, toma de decisiones y generación de respuestas de forma estructurada.
- **Motor RAG 100% Local y Offline**: Utiliza búsquedas vectoriales simétricas basadas en TF-IDF locales contra guías empresariales.
- **Base de Datos SQLite Persistente**: Mantiene registros estructurales para usuarios, historial de hilos de chat, procesos operativos inmutables y procesos de negocio/tickets creados.
- **Formato ISO 8601 Limpio**: Guarda marcas de tiempo exactas UTC redondeadas al segundo sin microsegundos extras para mayor legibilidad estética.

---

## 🛠️ Requisitos Previos y Configuración

### 1. Requisitos de Software
- **Python 3.10 o superior** instalado en el sistema.

### 2. Configuración de Variables de Entorno (`.env`)
El agente consume la API de Gemini mediante solicitudes directas de red seguras. Para ello, es necesario declarar sus credenciales en un archivo `.env` ubicado en la raíz del proyecto.

Crea un archivo llamado `.env` en la raíz de la carpeta y añade el siguiente contenido:

```env
# Clave API de Gemini para las solicitudes de IA
GEMINI_API_KEY="TU_GEMINI_API_KEY_AQUÍ"
```

*Nota: Reemplaza `"TU_GEMINI_API_KEY_AQUÍ"` con una clave válida que puedes obtener gratuitamente en Google AI Studio.*

### 3. Instalación de Dependencias
Instala el SDK oficial de Google GenAI y la librería de Pydantic ejecutando el siguiente comando en tu terminal:

```bash
pip install google-genai
pip install pydantic
```

---

## 🖥️ Cómo Utilizar la Aplicación

La aplicación se ejecuta de manera directa desde la consola/terminal de tu sistema utilizando el intérprete de Python:

```bash
python3 agente.py
```

Al iniciar la ejecución, la aplicación te solicitará tu **correo electrónico** en consola:
- Si ya eres un usuario registrado, cargará de forma segura tu perfil e historial de tickets activos.
- Si es la primera vez que ingresas, iniciará un sencillo asistente interactivo para registrar tu **Nombre Completo** y **Número de Teléfono**.

Una vez iniciada la sesión, escribe tu consulta de soporte en español o utiliza alguno de los comandos integrados:

### Comandos de la CLI:
- `/procesos` — Imprime un reporte tabular de todos los procesos de soporte y negocio registrados en la tabla SQLite local.
- `/borrar_historial` — Elimina los registros anteriores del historial conversacional en la base de datos de manera limpia.
- `/salir` — Cierra la sesión activa de forma segura.

---

## 🗄️ Estructura de la Base de Datos (`agent_system.db`)

Toda la información y registros de la aplicación se persisten localmente dentro de un archivo de base de datos SQLite llamado **`agent_system.db`** (ubicado en la raíz del directorio).

Puedes explorar y realizar consultas directas sobre este archivo ingresando a través de la terminal o con utilidades visuales como [DB Browser for SQLite](https://sqlitebrowser.org/):

```bash
# Entrar a la base de datos vía terminal interactiva de SQLite
sqlite3 agent_system.db
```

### Detalle de las Tablas e Índices correspondientes

A continuación se describe el esquema estructural exacto que procesa el motor:

#### 1. Tabla `users` (Información de Clientes)
Almacena el registro único, credenciales y estado de cuenta de los clientes.

| Columna | Tipo SQL | Descripción |
| :--- | :--- | :--- |
| `user_id` | `INTEGER UNIQUE` | Identificador numérico autoincremental de cliente (comienza en `1000`). |
| `correo` | `TEXT PRIMARY KEY` | Correo de registro principal (Llave Primaria). |
| `nombre_completo`| `TEXT` | Nombre legible por humanos verificado. |
| `telefono` | `TEXT` | Número de contacto directo validado. |
| `estatus_cuenta` | `TEXT` | Estatus actual de la cuenta del usuario (ej: `"activa"`). |
| `tickets_activos` | `TEXT` | Cadena JSON representativa de una lista de hilos de tickets activos. |
| `created_at` | `TEXT` | Fecha y hora UTC del registro inicial en formato ISO 8601 (ej: `2026-05-21T18:01:34Z`). |

---

#### 2. Tabla `processes` (Procesos de Negocio / Tickets)
Almacena y categoriza de forma automática cada ticket o proceso de negocio procesado por las herramientas del motor cognitivo.

| Columna | Tipo SQL | Descripción |
| :--- | :--- | :--- |
| `process_id` | `TEXT PRIMARY KEY` | Identificador alfanumérico legible único del ticket (ej: `PROC-3FE8`). |
| `process_name` | `TEXT` | Descripción corta del requerimiento o proceso que se generó. |
| `area` | `TEXT` | Área corporativa asignada responsable de la resolución. |
| `expected_timeframe_for_solution` | `TEXT` | Fecha estimada u objetivo de resolución acordada comercialmente. |
| `channel` | `TEXT` | Canal de ingreso (por defecto `"terminal"`). |
| `priority` | `INTEGER` | Prioridad analizada sobre el impacto (rango entero de `1` a `3`). |
| `user_id` | `INTEGER` | ID del usuario (`users.user_id`) que originó dicho proceso. |
| `timestamp` | `TEXT` | Fecha y hora UTC de la creación del proceso en formato ISO 8601 (ej: `2026-05-21T18:01:34Z`). |

---

#### 3. Tabla `conversations` (Memoria Conversacional Viva)
Mantiene un rastro claro del historial completo de mensajes cruzados entre el usuario y los agentes encargados para fines de contexto cognitivo posterior.

| Columna | Tipo SQL | Descripción |
| :--- | :--- | :--- |
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Clave técnica autoincremental del mensaje. |
| `conversation_id` | `TEXT` | Hash o UUID identificador único de la sesión del chat. |
| `user_id` | `TEXT` | Correo electrónico de inicio o id asignado de quien sostiene la interacción. |
| `sender` | `TEXT` | Autor del mensaje emitido (`"user"` o `"assistant"`). |
| `message` | `TEXT` | Contenido de texto explícito del mensaje enviado/recibido. |
| `timestamp` | `TEXT` | Fecha y hora UTC de registro en formato ISO 8601 (ej: `2026-05-21T18:01:34Z`). |

---

#### 4. Tabla `procesos_operativos` (Procesos Internos Inmutables)
Guarda la información certificada e inmutable de los procesos de soporte más solicitados.

| ID del Proceso | Nombre del Proceso | Área Responsable | Tiempo Promedio |
| :--- | :--- | :--- | :--- |
| **P_001** | atención a aclaraciones | Servicio a cliente | 2 horas |
| **P_002** | cancelación de productos | Servicio a cliente | 24 horas |
| **P_003** | escalamiento de incidencias | Supervisores | 7 días hábiles |
| **P_004** | actualización de datos | Finanzas | inmediato |
| **P_005** | gestión de quejas internas | Recursos Humanos | 7 días hábiles |
