"""
Sidebar navigation widget for FACOT 2.0 Redesigned
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont
from icon_manager import IconManager


class SidebarWidget(QWidget):
    """
    Sidebar de navegación para FACOT.
    Emite señales cuando se selecciona una sección.
    """
    
    section_changed = pyqtSignal(str)  # Emite el nombre de la sección
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._current_button = None
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Logo / Title
        title_label = QLabel("FACOT")
        title_label.setProperty("heading", True)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setContentsMargins(0, 20, 0, 20)
        layout.addWidget(title_label)
        
        # Navigation buttons
        self.btn_invoices = self._create_nav_button("Facturación", "invoice")
        self.btn_quotations = self._create_nav_button("Cotizaciones", "quotation")
        self.btn_invoice_history = self._create_nav_button("Historial Facturas", "history")
        self.btn_quotation_history = self._create_nav_button("Historial Cotizaciones", "history")
        self.btn_settings = self._create_nav_button("Configuración", "settings")
        
        layout.addWidget(self.btn_invoices)
        layout.addWidget(self.btn_quotations)
        layout.addWidget(self.btn_invoice_history)
        layout.addWidget(self.btn_quotation_history)
        
        # Spacer
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        # Settings at bottom
        layout.addWidget(self.btn_settings)
        
        # Margen inferior
        layout.addSpacing(20)
        
        # Activar el primer botón por defecto
        self.btn_invoices.setChecked(True)
        self._current_button = self.btn_invoices
    
    def _create_nav_button(self, text: str, icon_name: str) -> QPushButton:
        """Crea un botón de navegación con icono"""
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setAutoExclusive(False)  # Manejamos manualmente
        
        # Intentar aplicar icono
        try:
            IconManager.apply_icon_to_button(btn, icon_name)
        except Exception:
            pass
        
        btn.clicked.connect(lambda: self._on_button_clicked(btn, text.lower().replace(" ", "_")))
        return btn
    
    def _on_button_clicked(self, button: QPushButton, section_name: str):
        """Maneja el click en un botón de navegación"""
        # Desmarcar el botón anterior
        if self._current_button and self._current_button != button:
            self._current_button.setChecked(False)
        
        # Marcar el nuevo
        button.setChecked(True)
        self._current_button = button
        
        # Emitir señal
        self.section_changed.emit(section_name)
    
    def set_active_section(self, section_name: str):
        """Activa una sección programáticamente"""
        button_map = {
            "facturación": self.btn_invoices,
            "cotizaciones": self.btn_quotations,
            "historial_facturas": self.btn_invoice_history,
            "historial_cotizaciones": self.btn_quotation_history,
            "configuración": self.btn_settings,
        }
        
        btn = button_map.get(section_name.lower())
        if btn:
            self._on_button_clicked(btn, section_name)
