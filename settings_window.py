from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog,
    QHBoxLayout, QListWidget, QMessageBox, QInputDialog, QGroupBox, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt
import facot_config

class SettingsWindow(QDialog):
    def __init__(self, logic, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setMinimumSize(700, 650)
        self.logic = logic  # Debe ser instancia de LogicController
        self.parent_window = parent  # Store reference to parent for theme updates

        self._build_ui()
        self._load_companies()
        self._load_settings_for_active_company()

    def _build_ui(self):
        """Build UI with tabs for organization"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Tabs for better organization
        tabs = QTabWidget()
        
        # Tab 1: Apariencia
        appearance_tab = self._build_appearance_tab()
        tabs.addTab(appearance_tab, "Apariencia")
        
        # Tab 2: Empresa
        company_tab = self._build_company_tab()
        tabs.addTab(company_tab, "Empresa")
        
        # Tab 3: Rutas y Archivos
        paths_tab = self._build_paths_tab()
        tabs.addTab(paths_tab, "Rutas y Archivos")
        
        # Tab 4: Backups y Firebase
        advanced_tab = self._build_advanced_tab()
        tabs.addTab(advanced_tab, "Avanzado")
        
        layout.addWidget(tabs)
        
        # Botones de acción
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        
        btn_save = QPushButton("Guardar")
        btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(btn_save)
        
        layout.addLayout(btn_row)
    
    def _build_appearance_tab(self):
        """Build appearance settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Theme selector
        theme_group = QGroupBox("Tema de la Aplicación")
        theme_layout = QVBoxLayout(theme_group)
        
        desc_label = QLabel("Selecciona el tema visual de FACOT:")
        desc_label.setProperty("muted", True)
        theme_layout.addWidget(desc_label)
        
        self.theme_selector = QComboBox()
        self.theme_selector.setMinimumWidth(300)
        
        # Load available themes
        try:
            from utils.theme_manager import get_available_themes, get_theme_manager
            self.theme_manager = get_theme_manager()
            themes = get_available_themes()
            
            # Add themes to combo
            for theme_id, theme_name in themes.items():
                self.theme_selector.addItem(theme_name, theme_id)
            
            # Select current theme
            current_theme = self.theme_manager.load_saved_theme()
            if current_theme:
                for i in range(self.theme_selector.count()):
                    if self.theme_selector.itemData(i) == current_theme:
                        self.theme_selector.setCurrentIndex(i)
                        break
            
            # Connect change handler
            self.theme_selector.currentIndexChanged.connect(self._on_theme_changed)
            
        except Exception as e:
            QMessageBox.warning(self, "Advertencia", f"No se pudieron cargar los temas: {e}")
            self.theme_selector.setEnabled(False)
        
        theme_layout.addWidget(QLabel("Tema:"))
        theme_layout.addWidget(self.theme_selector)
        
        # Theme descriptions
        themes_info = QLabel(
            "<b>Modern Midnight:</b> Tema oscuro moderno para uso prolongado<br>"
            "<b>FACOT Light Pro:</b> Tema claro profesional para ambientes iluminados"
        )
        themes_info.setProperty("muted", True)
        themes_info.setWordWrap(True)
        theme_layout.addWidget(themes_info)
        
        layout.addWidget(theme_group)
        layout.addStretch(1)
        
        return widget
    
    def _build_company_tab(self):
        """Build company settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Selector de empresa
        self.company_selector = QComboBox()
        self.company_selector.currentIndexChanged.connect(self._load_settings_for_selected_company)
        layout.addWidget(QLabel("Empresa:"))
        layout.addWidget(self.company_selector)

        # Datos básicos
        self.name_edit = QLineEdit()
        self.rnc_edit = QLineEdit()
        self.address_edit = QLineEdit()
        layout.addWidget(QLabel("Nombre:")); layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("RNC:")); layout.addWidget(self.rnc_edit)
        layout.addWidget(QLabel("Dirección:")); layout.addWidget(self.address_edit)

        # Plantilla de factura
        self.template_edit = QLineEdit()
        btn_template = QPushButton("Seleccionar plantilla")
        btn_template.clicked.connect(self._select_template)
        hlayout_template = QHBoxLayout()
        hlayout_template.addWidget(QLabel("Ruta de plantilla:"))
        hlayout_template.addWidget(self.template_edit)
        hlayout_template.addWidget(btn_template)
        
        # Selector de empresa
        self.company_selector = QComboBox()
        self.company_selector.currentIndexChanged.connect(self._load_settings_for_selected_company)
        layout.addWidget(QLabel("Seleccionar Empresa:"))
        layout.addWidget(self.company_selector)
        
        # Datos básicos
        company_group = QGroupBox("Datos de la Empresa")
        company_layout = QVBoxLayout(company_group)
        
        self.name_edit = QLineEdit()
        self.rnc_edit = QLineEdit()
        self.address_edit = QLineEdit()
        
        company_layout.addWidget(QLabel("Nombre:"))
        company_layout.addWidget(self.name_edit)
        company_layout.addWidget(QLabel("RNC:"))
        company_layout.addWidget(self.rnc_edit)
        company_layout.addWidget(QLabel("Dirección:"))
        company_layout.addWidget(self.address_edit)
        
        layout.addWidget(company_group)
        
        # Monedas
        currency_group = QGroupBox("Monedas Permitidas")
        currency_layout = QVBoxLayout(currency_group)
        
        self.currency_list = QListWidget()
        currency_layout.addWidget(self.currency_list)
        
        currency_btn_row = QHBoxLayout()
        btn_add_currency = QPushButton("Añadir moneda")
        btn_add_currency.clicked.connect(self._add_currency)
        btn_remove_currency = QPushButton("Eliminar seleccionada")
        btn_remove_currency.clicked.connect(self._remove_currency)
        currency_btn_row.addWidget(btn_add_currency)
        currency_btn_row.addWidget(btn_remove_currency)
        currency_layout.addLayout(currency_btn_row)
        
        layout.addWidget(currency_group)
        layout.addStretch(1)
        
        return widget
    
    def _build_paths_tab(self):
        """Build paths and files tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Plantilla de factura
        self.template_edit = QLineEdit()
        btn_template = QPushButton("Seleccionar")
        btn_template.clicked.connect(self._select_template)
        
        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("Ruta de plantilla:"))
        template_row.addWidget(self.template_edit, 1)
        template_row.addWidget(btn_template)
        layout.addLayout(template_row)

        # Carpeta de salida
        self.output_edit = QLineEdit()
        btn_output = QPushButton("Seleccionar")
        btn_output.clicked.connect(self._select_output)
        
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Carpeta de salida:"))
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(btn_output)
        layout.addLayout(output_row)

        # Carpeta de descargas (origen)
        self.downloads_edit = QLineEdit()
        btn_downloads = QPushButton("Seleccionar")
        btn_downloads.clicked.connect(self._select_downloads)
        
        downloads_row = QHBoxLayout()
        downloads_row.addWidget(QLabel("Carpeta de descargas:"))
        downloads_row.addWidget(self.downloads_edit, 1)
        downloads_row.addWidget(btn_downloads)
        layout.addLayout(downloads_row)

        # Carpeta de anexos (destino)
        self.attachments_edit = QLineEdit()
        btn_attachments = QPushButton("Seleccionar")
        btn_attachments.clicked.connect(self._select_attachments)
        
        attachments_row = QHBoxLayout()
        attachments_row.addWidget(QLabel("Carpeta de anexos:"))
        attachments_row.addWidget(self.attachments_edit, 1)
        attachments_row.addWidget(btn_attachments)
        layout.addLayout(attachments_row)
        
        layout.addStretch(1)
        return widget
    
    def _build_advanced_tab(self):
        """Build advanced settings tab (backups, firebase)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Backups
        backup_group = QGroupBox("Backups")
        backup_layout = QVBoxLayout(backup_group)
        
        btn_backup_now = QPushButton("Crear backup ahora")
        btn_backup_now.clicked.connect(self._create_backup_now)
        backup_layout.addWidget(btn_backup_now)
        
        btn_open_backups = QPushButton("Abrir carpeta de backups")
        btn_open_backups.clicked.connect(self._open_backups_folder)
        backup_layout.addWidget(btn_open_backups)
        
        layout.addWidget(backup_group)
        
        # Firebase
        firebase_group = QGroupBox("Firebase")
        firebase_layout = QVBoxLayout(firebase_group)
        
        btn_firebase_config = QPushButton("Configurar Firebase")
        btn_firebase_config.clicked.connect(self._configure_firebase)
        firebase_layout.addWidget(btn_firebase_config)
        
        layout.addWidget(firebase_group)
        layout.addStretch(1)
        
        return widget
    
    def _on_theme_changed(self, index):
        """Handle theme change"""
        if not hasattr(self, 'theme_manager'):
            return
        
        theme_id = self.theme_selector.itemData(index)
        if theme_id:
            try:
                # Apply theme immediately for preview
                from PyQt6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    self.theme_manager.apply_theme(app, theme_id)
                    # Save theme preference
                    self.theme_manager.save_and_apply_theme(theme_id)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error al aplicar tema: {e}")

    def _load_companies(self):
        companies = self.logic.get_all_companies()
        self.companies = {}
        self.company_selector.clear()
        for c in companies:
            name = c["name"]
            rnc = c["rnc"]
            self.companies[name] = rnc
            self.company_selector.addItem(name)
        # Selecciona la empresa activa si existe
        empresa_activa = facot_config.get_empresa_activa()
        if empresa_activa:
            for idx, name in enumerate(self.companies):
                if self.companies[name] == empresa_activa:
                    self.company_selector.setCurrentIndex(idx)
                    break

    def _load_settings_for_selected_company(self):
        name = self.company_selector.currentText()
        company_id = self.companies.get(name)
        if not company_id:
            return
        empresa_cfg = facot_config.get_empresa_config(company_id)
        self.name_edit.setText(empresa_cfg.get("nombre", name))
        self.rnc_edit.setText(company_id)
        self.address_edit.setText(empresa_cfg.get("direccion", ""))
        self.template_edit.setText(empresa_cfg.get("ruta_plantilla", ""))
        self.output_edit.setText(empresa_cfg.get("carpeta_salida", ""))
        self.downloads_edit.setText(empresa_cfg.get("carpeta_origen", ""))
        self.attachments_edit.setText(empresa_cfg.get("carpeta_destino", ""))
        self.currency_list.clear()
        for moneda in empresa_cfg.get("monedas", []):
            self.currency_list.addItem(moneda)

    def _load_settings_for_active_company(self):
        # Solo para iniciar con la empresa activa
        self._load_settings_for_selected_company()

    def _select_template(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Selecciona la plantilla de factura", "", "Archivos Excel (*.xlsx);;Todos los archivos (*)")
        if filename:
            self.template_edit.setText(filename)

    def _select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de salida")
        if folder:
            self.output_edit.setText(folder)

    def _select_downloads(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de descargas")
        if folder:
            self.downloads_edit.setText(folder)

    def _select_attachments(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de anexos")
        if folder:
            self.attachments_edit.setText(folder)

    def _add_currency(self):
        moneda, ok = QInputDialog.getText(self, "Añadir moneda", "Introduce el símbolo de la moneda:")
        if ok and moneda and moneda.strip():
            if moneda.upper() not in [self.currency_list.item(i).text() for i in range(self.currency_list.count())]:
                self.currency_list.addItem(moneda.upper())

    def _remove_currency(self):
        selected = self.currency_list.currentRow()
        if selected >= 0:
            self.currency_list.takeItem(selected)

    def _save_settings(self):
        name = self.company_selector.currentText()
        company_id = self.companies.get(name)
        if not company_id:
            QMessageBox.warning(self, "Error", "No se pudo determinar la empresa activa.")
            return
        empresa_cfg = {
            "nombre": self.name_edit.text(),
            "direccion": self.address_edit.text(),
            "ruta_plantilla": self.template_edit.text(),
            "carpeta_salida": self.output_edit.text(),
            "carpeta_origen": self.downloads_edit.text(),
            "carpeta_destino": self.attachments_edit.text(),
            "monedas": [self.currency_list.item(i).text() for i in range(self.currency_list.count())]
        }
        facot_config.set_empresa_config(company_id, empresa_cfg)
        facot_config.set_empresa_activa(company_id)
        QMessageBox.information(self, "Configuración", "Configuración guardada correctamente.")
        self.accept()

    def _create_backup_now(self):
        """Crea un backup manual ahora."""
        try:
            from utils.backups import create_backup
            result = create_backup()
            
            if result['success']:
                QMessageBox.information(
                    self,
                    "Backup completado",
                    f"Backup creado exitosamente.\n\n"
                    f"Ubicación: {result.get('backup_path', 'N/A')}\n"
                    f"Colecciones: {len(result.get('collections', {}))}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Backup con errores",
                    f"El backup se completó con algunos errores:\n\n"
                    f"{', '.join(result.get('errors', ['Error desconocido']))}"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error de backup",
                f"No se pudo crear el backup:\n\n{str(e)}"
            )

    def _open_backups_folder(self):
        """Abre la carpeta de backups en el explorador de archivos."""
        import os
        import subprocess
        import platform
        
        backup_dir = facot_config.get_backup_config().get('backup_dir', './backups')
        backup_path = os.path.abspath(backup_dir)
        
        # Crear la carpeta si no existe
        os.makedirs(backup_path, exist_ok=True)
        
        try:
            if platform.system() == 'Windows':
                os.startfile(backup_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', backup_path])
            else:  # Linux
                subprocess.run(['xdg-open', backup_path])
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"No se pudo abrir la carpeta:\n{backup_path}\n\nError: {str(e)}"
            )

    def _configure_firebase(self):
        """Abre el diálogo de configuración de Firebase."""
        try:
            from dialogs.firebase_config_dialog import FirebaseConfigDialog
            
            dialog = FirebaseConfigDialog(self)
            result = dialog.exec()
            
            if result == 1:  # Accepted
                QMessageBox.information(
                    self,
                    "Firebase configurado",
                    "La configuración de Firebase se ha guardado.\n"
                    "Los cambios tomarán efecto la próxima vez que inicie la aplicación."
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"No se pudo abrir la configuración de Firebase:\n\n{str(e)}"
            )