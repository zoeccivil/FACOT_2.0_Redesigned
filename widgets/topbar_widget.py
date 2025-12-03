"""
Topbar action widget for FACOT 2.0 Redesigned
"""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont
from icon_manager import IconManager


class TopbarWidget(QWidget):
    """
    Topbar con acciones contextuales según la vista activa.
    """
    
    # Señales para acciones
    new_clicked = pyqtSignal()
    save_clicked = pyqtSignal()
    preview_clicked = pyqtSignal()
    export_clicked = pyqtSignal()
    filter_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    company_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topbar")
        self._build_ui()
    
    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)
        
        # Company selector
        company_label = QLabel("Empresa:")
        company_label.setProperty("muted", True)
        self.company_selector = QComboBox()
        self.company_selector.setMinimumWidth(200)
        self.company_selector.currentTextChanged.connect(lambda text: self.company_changed.emit(text))
        
        layout.addWidget(company_label)
        layout.addWidget(self.company_selector)
        
        # Spacer
        layout.addItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Action buttons (contextuales)
        self.btn_new = self._create_action_button("Nuevo", "new", primary=True)
        self.btn_save = self._create_action_button("Guardar", "save", primary=True)
        self.btn_preview = self._create_action_button("Vista Previa", "preview", secondary=True)
        self.btn_export = self._create_action_button("Exportar", "pdf", secondary=True)
        self.btn_filter = self._create_action_button("Filtrar", "filter", secondary=True)
        
        # Conectar señales
        self.btn_new.clicked.connect(self.new_clicked.emit)
        self.btn_save.clicked.connect(self.save_clicked.emit)
        self.btn_preview.clicked.connect(self.preview_clicked.emit)
        self.btn_export.clicked.connect(self.export_clicked.emit)
        self.btn_filter.clicked.connect(self.filter_clicked.emit)
        
        # Por defecto, ocultar todos los botones de acción
        self.btn_new.hide()
        self.btn_save.hide()
        self.btn_preview.hide()
        self.btn_export.hide()
        self.btn_filter.hide()
    
    def _create_action_button(self, text: str, icon_name: str, primary: bool = False, secondary: bool = False) -> QPushButton:
        """Crea un botón de acción con icono"""
        btn = QPushButton(text)
        
        if secondary:
            btn.setProperty("secondary", True)
        
        # Aplicar icono
        try:
            IconManager.apply_icon_to_button(btn, icon_name)
        except Exception:
            pass
        
        return btn
    
    def set_context(self, context: str):
        """
        Configura qué botones mostrar según el contexto.
        
        Contextos:
        - "invoice": Nuevo, Guardar, Vista Previa, Exportar
        - "quotation": Nuevo, Guardar, Vista Previa, Exportar
        - "invoice_history": Filtrar, Exportar
        - "quotation_history": Filtrar, Exportar
        - "settings": ninguno
        """
        # Limpiar layout de botones
        # Primero, remover todos los botones del layout
        for btn in [self.btn_new, self.btn_save, self.btn_preview, self.btn_export, self.btn_filter]:
            btn.hide()
            btn.setParent(None)
        
        # Determinar qué botones mostrar
        buttons_to_show = []
        
        if context in ["invoice", "quotation"]:
            buttons_to_show = [self.btn_new, self.btn_save, self.btn_preview, self.btn_export]
        elif context in ["invoice_history", "quotation_history"]:
            buttons_to_show = [self.btn_filter, self.btn_export]
        
        # Agregar botones al layout
        layout = self.layout()
        for btn in buttons_to_show:
            btn.show()
            btn.setParent(self)
            layout.addWidget(btn)
    
    def set_companies(self, companies: list):
        """Actualiza la lista de empresas"""
        self.company_selector.clear()
        self.company_selector.addItems(companies)
    
    def get_current_company(self) -> str:
        """Retorna la empresa seleccionada"""
        return self.company_selector.currentText()
    
    def set_current_company(self, company_name: str):
        """Establece la empresa actual"""
        index = self.company_selector.findText(company_name)
        if index >= 0:
            self.company_selector.setCurrentIndex(index)
