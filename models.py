import os
import json
from pydantic import BaseModel, Field
from typing import Optional, Literal

class ClasificacionPreguntaProceso(BaseModel):
    es_pregunta_altamente_especifica: bool = Field(
        description="True si la pregunta del usuario es una consulta altamente específica que requiere consultar la tabla de procesos operativos internos inmutables (P_001 a P_005) para responder. False si es una consulta general de políticas corporativas generales, un saludo o una duda de soporte genérica."
    )
    id_del_proceso: str = Field(
        description="El ID del proceso operativo inmutable asociado (P_001, P_002, P_003, P_004, P_005) si aplica, de lo contrario dejar como cadena vacía."
    )

class DatosContacto(BaseModel):
    campo: Optional[Literal["nombre_completo", "correo", "telefono"]] = Field(
        default=None,
        description="El campo de contacto que el usuario desea actualizar: 'nombre_completo', 'correo' o 'telefono'. Debe ser null si no se identifica."
    )
    valor: Optional[str] = Field(
        default=None,
        description="El nuevo valor exacto provisto por el usuario para la actualización. Debe ser null si el usuario no ha proporcionado un nuevo valor todavía."
    )

class DescripcionProblema(BaseModel):
    problema: Optional[str] = Field(
        default=None,
        description="Descripción concreta del problema de cuenta proporcionado por el usuario (por ejemplo, 'banca móvil bloqueada'). Debe ser null si es un saludo o aviso genérico sin detalles."
    )

class ClasificacionTema(BaseModel):
    tema: Literal[
        "Cancelación de Producto",
        "Escalación de tickets",
        "Actualización de contacto",
        "Complaints / Quejas",
        "Soporte General"
    ] = Field(
        description="La clasificación exacta del tema basada en el mensaje del usuario."
    )

try:
    from google import genai
    from google.genai import types
    SDK_DISPONIBLE = True
except ImportError:
    SDK_DISPONIBLE = False

def cargar_variables_env():
    """Busca un archivo .env en el directorio actual y carga las variables a os.environ."""
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for linea in f:
                    linea = linea.strip()
                    if not linea or linea.startswith("#"):
                        continue
                    if "=" in linea:
                        clave, valor = linea.split("=", 1)
                        clave = clave.strip()
                        valor = valor.strip().strip("'\"")
                        os.environ[clave] = valor
        except Exception:
            pass
