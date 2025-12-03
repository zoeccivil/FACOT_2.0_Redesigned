"""
icon_manager.py
Gestor centralizado de iconos para FACOT 2.0 Redesigned.
Soporta iconos SVG y qtawesome (FontAwesome 6) como fallback.
"""
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QSize, QByteArray
import os
import logging

# Intentar importar qtawesome, si falla, usar modo fallback
try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False
    logging.warning("qtawesome no está instalado. Usando iconos SVG. Ejecuta: pip install qtawesome")

# Rutas de iconos
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_ICONS_DIR = os.path.join(_PROJECT_ROOT, "assets", "icons")

class IconManager:
    """
    Provee acceso centralizado a los iconos de la aplicación.
    Prioriza SVG sobre FontAwesome.
    """
    
    # Mapa de nombres semánticos a archivos SVG
    SVG_ICON_MAP = {
        "preview": "preview.svg",
        "edit": "edit.svg",
        "delete": "delete.svg",
        "pdf": "pdf.svg",
        "print": "print.svg",
        "settings": "settings.svg",
        "filter": "filter.svg",
        "save": "save.svg",
        "new": "new.svg",
        "eye": "eye.svg",
    }
    
    # Mapa de Iconos Semánticos -> Identificadores FontAwesome (fallback)
    FONTAWESOME_ICON_MAP = {
        "dashboard": "fa6s.chart-pie",
        "transactions": "fa6s.money-bill-transfer",
        "invoice": "fa6s.file-invoice",
        "quotation": "fa6s.file-lines",
        "history": "fa6s.clock-rotate-left",
        "reports": "fa6s.file-pdf",
        "settings": "fa6s.gear",
        "company": "fa6s.building",
        "items": "fa6s.box",
        "add": "fa6s.plus",
        "edit": "fa6s.pen",
        "delete": "fa6s.trash",
        "save": "fa6s.floppy-disk",
        "search": "fa6s.magnifying-glass",
        "refresh": "fa6s.rotate",
        "menu": "fa6s.bars",
        "close": "fa6s.xmark",
        "check": "fa6s.check",
        "theme": "fa6s.palette",
        "preview": "fa6s.eye",
        "pdf": "fa6s.file-pdf",
        "print": "fa6s.print",
        "filter": "fa6s.filter",
        "new": "fa6s.plus",
    }

    @staticmethod
    def _load_svg_icon(svg_path: str, color: str = None, size: QSize = None) -> QIcon:
        """
        Carga un icono SVG y opcionalmente lo colorea.
        """
        try:
            if not os.path.exists(svg_path):
                return QIcon()
            
            # Leer el SVG
            with open(svg_path, 'r', encoding='utf-8') as f:
                svg_data = f.read()
            
            # Si se especifica color, reemplazar currentColor
            if color:
                svg_data = svg_data.replace('stroke="currentColor"', f'stroke="{color}"')
                svg_data = svg_data.replace('fill="currentColor"', f'fill="{color}"')
            
            # Crear renderer
            renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
            
            # Tamaño por defecto
            if size is None:
                size = QSize(24, 24)
            
            # Crear pixmap
            pixmap = QPixmap(size)
            pixmap.fill(QColor(0, 0, 0, 0))  # Transparente
            
            # Renderizar
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            
            return QIcon(pixmap)
        except Exception as e:
            logging.warning(f"Error loading SVG icon {svg_path}: {e}")
            return QIcon()

    @staticmethod
    def get_icon(name: str, color: str = None, size: QSize = None) -> QIcon:
        """
        Obtiene un QIcon basado en el nombre semántico.
        Prioriza SVG, luego FontAwesome.
        
        Args:
            name: Nombre del icono (ej: 'preview', 'edit', 'dashboard')
            color: Hex color string (ej: '#FFFFFF'). Si es None, usa el default.
            size: QSize para el icono (solo para SVG)
        """
        # Intentar cargar SVG primero
        if name in IconManager.SVG_ICON_MAP:
            svg_filename = IconManager.SVG_ICON_MAP[name]
            svg_path = os.path.join(_ICONS_DIR, svg_filename)
            icon = IconManager._load_svg_icon(svg_path, color, size)
            if not icon.isNull():
                return icon
        
        # Fallback a FontAwesome
        if HAS_QTAWESOME and name in IconManager.FONTAWESOME_ICON_MAP:
            icon_code = IconManager.FONTAWESOME_ICON_MAP[name]
            options = {}
            if color:
                options['color'] = color
            return qta.icon(icon_code, **options)
        
        # Fallback final: icono vacío
        return QIcon()

    @staticmethod
    def apply_icon_to_button(button, icon_name: str, color: str = None, size: QSize = None):
        """Helper para establecer icono en un botón existente"""
        icon = IconManager.get_icon(icon_name, color, size)
        if not icon.isNull():
            button.setIcon(icon)
            if size:
                button.setIconSize(size)

    @staticmethod
    def get_icon_path(name: str) -> str:
        """Obtiene la ruta completa de un icono SVG"""
        if name in IconManager.SVG_ICON_MAP:
            return os.path.join(_ICONS_DIR, IconManager.SVG_ICON_MAP[name])
        return ""
