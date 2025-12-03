"""
Compat + Theme utilities for FACOT
"""
from __future__ import annotations
import json
import os
import re
from typing import Dict, List, Optional

# --- FIX RUTAS ---
# Usamos abspath para asegurar que encontramos la carpeta real del archivo
_CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CURRENT_FILE_DIR) # Subir un nivel desde utils/
_THEMES_DIR = os.path.join(_PROJECT_ROOT, "themes")

_BASE_QSS = os.path.join(_THEMES_DIR, "style_template.qss")
_INFOFIELDS_QSS = os.path.join(_THEMES_DIR, "infofields_transparent.qss")
_FACOT_CONFIG_JSON = os.path.join(_PROJECT_ROOT, "facot_config.json")

try:
    import facot_config
except Exception:
    facot_config = None

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh: return fh.read()
    except Exception as e:
        print(f"[ThemeError] No se pudo leer {path}: {e}")
        return ""

def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh: return json.load(fh) or {}
    except Exception as e:
        print(f"[ThemeError] JSON inválido en {path}: {e}")
        return {}

def _write_json(path: str, data: dict) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data or {}, fh, ensure_ascii=False, indent=2)
        return True
    except Exception: return False

def _list_theme_files() -> List[str]:
    # Debug: Verificar que la carpeta existe
    if not os.path.exists(_THEMES_DIR):
        print(f"[ThemeError] La carpeta de temas no existe en: {_THEMES_DIR}")
        return []
    
    try:
        files = [os.path.join(_THEMES_DIR, f) for f in os.listdir(_THEMES_DIR) if f.lower().endswith(".json")]
        # Filtrar config o archivos que no son temas si es necesario
        return [f for f in files if "facot_config" not in f]
    except Exception as e:
        print(f"[ThemeError] Error listando directorio: {e}")
        return []

def _resolve_theme_file(selector: str) -> Optional[str]:
    if not selector: return None
    # 1. Check directo
    if selector.endswith(".json"):
        p = os.path.join(_THEMES_DIR, selector)
        return p if os.path.exists(p) else None
    
    # 2. Check con nombre base
    candidates = [f"{selector}.json", f"theme_{selector}.json"]
    for c in candidates:
        p = os.path.join(_THEMES_DIR, c)
        if os.path.exists(p): return p

    # 3. Check interno por ID
    for path in _list_theme_files():
        data = _read_json(path)
        if str(data.get("id", "")).strip().lower() == selector.strip().lower():
            return path
            
    # Fallback
    fallback = os.path.join(_THEMES_DIR, "theme_light.json")
    return fallback if os.path.exists(fallback) else None

def _flatten_vars_from_theme(theme_json: dict) -> Dict[str, str]:
    palette = theme_json.get("palette") or {}
    return {str(k): str(v) for k, v in palette.items()}

def _replace_tokens(qss: str, vars_map: Dict[str, str]) -> str:
    if not qss: return ""
    for k, v in vars_map.items():
        qss = qss.replace("{{" + k + "}}", str(v))
    # Limpiar tokens huérfanos
    qss = re.sub(r"\{\{[^\}]+\}\}", "", qss)
    return qss

class ThemeManager:
    def __init__(self):
        self._app = None

    def set_app(self, qt_app) -> None:
        self._app = qt_app

    def generate_stylesheet(self, theme_selector: str = "modern-midnight") -> str:
        theme_file = _resolve_theme_file(theme_selector)
        if not theme_file:
            print(f"[ThemeManager] Tema no encontrado: {theme_selector}")
            return ""
        
        theme_json = _read_json(theme_file)
        vars_map = _flatten_vars_from_theme(theme_json)
        
        base_qss = _read_text(_BASE_QSS)
        info_qss = _read_text(_INFOFIELDS_QSS)
        
        # Cargar override específico si existe
        theme_id = theme_json.get("id", theme_selector)
        theme_qss_path = os.path.join(_THEMES_DIR, f"{theme_id}.qss")
        # Compatibilidad con nombres antiguos
        if not os.path.exists(theme_qss_path):
             theme_qss_path = os.path.join(_THEMES_DIR, f"theme_{theme_id}.qss")
        
        theme_specific_qss = _read_text(theme_qss_path) if os.path.exists(theme_qss_path) else ""
        
        combined = "\n\n".join(filter(None, [base_qss, info_qss, theme_specific_qss])).strip()
        return _replace_tokens(combined, vars_map)

    def apply_theme(self, qt_app, theme_selector: str = "modern-midnight") -> None:
        if qt_app:
            qss = self.generate_stylesheet(theme_selector)
            if qss: qt_app.setStyleSheet(qss)

    def save_and_apply_theme(self, theme_id: str) -> bool:
        if facot_config and hasattr(facot_config, "set_theme"):
            facot_config.set_theme(str(theme_id))
        
        cfg = _read_json(_FACOT_CONFIG_JSON)
        cfg["theme"] = str(theme_id)
        saved = _write_json(_FACOT_CONFIG_JSON, cfg)
        if self._app:
            self.apply_theme(self._app, str(theme_id))
        return saved
    
    def load_saved_theme(self) -> str:
        if facot_config and hasattr(facot_config, "get_theme"):
            t = facot_config.get_theme()
            if t: return str(t)
        cfg = _read_json(_FACOT_CONFIG_JSON)
        return str(cfg.get("theme", "modern-midnight"))

def get_available_themes() -> Dict[str, str]:
    """ Devuelve dict {id: nombre} para el menú """
    out: Dict[str, str] = {}
    files = _list_theme_files()
    if not files:
        print(f"[ThemeManager] ADVERTENCIA: No se encontraron archivos JSON en {_THEMES_DIR}")
    
    for path in files:
        data = _read_json(path)
        # Ignorar JSONs que no sean temas (por si acaso)
        if "palette" not in data: 
            continue
            
        theme_id = str(data.get("id", "")).strip()
        if not theme_id:
            filename = os.path.splitext(os.path.basename(path))[0]
            theme_id = filename.replace("theme_", "")
            
        name = str(data.get("name", theme_id.capitalize())).strip()
        out[theme_id] = name
    return out

_default_mgr: Optional[ThemeManager] = None

def get_theme_manager() -> ThemeManager:
    global _default_mgr
    if _default_mgr is None: _default_mgr = ThemeManager()
    return _default_mgr

def apply_theme(qt_app, theme_selector: str = "modern-midnight"):
    get_theme_manager().apply_theme(qt_app, theme_selector)