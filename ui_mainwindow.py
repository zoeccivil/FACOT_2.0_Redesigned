from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QComboBox, QMessageBox,
    QMenuBar, QMenu, QFileDialog, QStatusBar, QHBoxLayout
)
from PyQt6.QtGui import QAction
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtCore import QUrl
import os, sys

import facot_config
from logic import LogicController
from widgets.connection_status_bar import ConnectionStatusBar

# Tabs modulares
from tabs.invoice_tab import InvoiceTab
import sys
# Fuerza recarga de módulos
if 'tabs.quotation_tab' in sys.modules:
    del sys.modules['tabs.quotation_tab']
from tabs.quotation_tab import QuotationTab
from tabs.invoice_history_tab import InvoiceHistoryTab
from tabs.quotation_history_tab import QuotationHistoryTab

# Ventanas secundarias
from settings_window import SettingsWindow
from company_management_window import CompanyManagementWindow
from items_management_window import ItemsManagementWindow

# Dialog para editar plantillas (botón/menú)
from dialogs.template_editor_dialog import TemplateEditorDialog

# -*- coding: utf-8 -*-

# ahora las importaciones normales
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QDateEdit, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QComboBox,
    QHeaderView, QGroupBox, QToolButton, QCheckBox, QDialog
)
from PyQt6.QtCore import QDate, Qt, pyqtSignal

class HybridLogicWrapper:
    """
    Wrapper híbrido que combina logic (SQLite) y data_access (Firebase).
    Prioridad: data_access -> logic.
    """
    def __init__(self, logic, data_access=None):
        self._logic = logic
        self._data_access = data_access
        self._use_firebase = data_access is not None
        if self._use_firebase:
            print(f"[HYBRID] Created hybrid wrapper with Firebase backend")
        else:
            print(f"[HYBRID] Created hybrid wrapper with SQLite only")

    def __getattr__(self, name):
        if self._use_firebase and self._data_access and hasattr(self._data_access, name):
            attr = getattr(self._data_access, name)
            if callable(attr):
                def logged_call(*args, **kwargs):
                    return attr(*args, **kwargs)
                return logged_call
            return attr
        if hasattr(self._logic, name):
            attr = getattr(self._logic, name)
            if callable(attr):
                def logged_call(*args, **kwargs):
                    return attr(*args, **kwargs)
                return logged_call
            return attr
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @property
    def conn(self):
        return self._logic.conn if hasattr(self._logic, 'conn') else None

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gestión de Facturas y Cotizaciones")
        self.resize(1100, 790)
        self.data_access = None
        self.current_access_mode = "SQLITE"
        self.hybrid_logic = None
        self.companies: dict[str, dict] = {}
        self._init_db()
        self._setup_ui()
        self._setup_menu()
        self._setup_connection_status()
        self._check_online_status()
        self._detect_and_set_connection_mode()

    def _init_db(self):
        db_path = facot_config.get_db_path()
        if not db_path or not os.path.isfile(db_path):
            filename, _ = QFileDialog.getOpenFileName(self, "Selecciona tu archivo de base de datos", "", "Database Files (*.db);;Todos los archivos (*)")
            if filename:
                facot_config.set_db_path(filename); db_path = filename
            else:
                QMessageBox.critical(self, "Error", "No se seleccionó una base de datos. El programa se cerrará.")
                sys.exit(1)
        self.logic = LogicController(db_path)

        try:
            from data_access import get_data_access, DataAccessMode
            from config_facot import get_connection_mode

            preferred_mode = get_connection_mode()
            print(f"[MAIN] Modo de conexión preferido: {preferred_mode}")

            mode_enum = DataAccessMode[preferred_mode]
            # Prefer passing logic_controller where applicable
            try:
                self.data_access = get_data_access(logic_controller=self.logic, mode=mode_enum)
            except TypeError:
                # fallback to call signature without logic_controller
                self.data_access = get_data_access(mode=mode_enum)
            self.current_access_mode = preferred_mode
            self.hybrid_logic = HybridLogicWrapper(self.logic, self.data_access)
            print(f"[MAIN] Created hybrid logic wrapper")

        except Exception as e:
            print(f"[MAIN] Warning: Could not initialize data_access: {e}")
            self.data_access = None
            self.current_access_mode = "SQLITE"
            self.hybrid_logic = HybridLogicWrapper(self.logic, None)

    def _setup_ui(self):
        from PyQt6.QtWidgets import QStackedWidget
        from widgets.sidebar_widget import SidebarWidget
        from widgets.topbar_widget import TopbarWidget

        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setCentralWidget(central)

        self.sidebar = SidebarWidget()
        self.sidebar.section_changed.connect(self._on_sidebar_section_changed)
        main_layout.addWidget(self.sidebar)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.topbar = TopbarWidget()
        content_layout.addWidget(self.topbar)

        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)

        main_layout.addWidget(content_widget)

        self.companies = {}

        def get_company_callable():
            try:
                name = self.topbar.get_current_company()
                if not name:
                    return None
                return (self.companies or {}).get(name)
            except Exception:
                return None

        logic_to_pass = self.hybrid_logic if self.hybrid_logic else self.logic

        self.invoice_tab = InvoiceTab(logic_to_pass, get_company_callable)
        self.quotation_tab = QuotationTab(logic_to_pass, get_company_callable)
        self.invoice_history_tab = InvoiceHistoryTab(logic_to_pass, get_company_callable)
        self.quotation_history_tab = QuotationHistoryTab(logic_to_pass, get_company_callable)

        try:
            self.invoice_tab.invoice_saved.connect(lambda _id: self.invoice_history_tab.refresh())
        except Exception:
            pass
        try:
            self.quotation_tab.quotation_saved.connect(lambda _id: self.quotation_history_tab.refresh())
        except Exception:
            pass

        self.stacked_widget.addWidget(self.invoice_tab)
        self.stacked_widget.addWidget(self.quotation_tab)
        self.stacked_widget.addWidget(self.invoice_history_tab)
        self.stacked_widget.addWidget(self.quotation_history_tab)

        settings_placeholder = QWidget()
        self.stacked_widget.addWidget(settings_placeholder)

        self.section_index_map = {
            "facturación": 0,
            "cotizaciones": 1,
            "historial_facturas": 2,
            "historial_cotizaciones": 3,
            "configuración": 4,
        }
        self.index_context_map = {
            0: "invoice",
            1: "quotation",
            2: "invoice_history",
            3: "quotation_history",
            4: "settings",
        }

        self.stacked_widget.setCurrentIndex(0)
        try:
            self.topbar.set_context("invoice")
        except Exception:
            pass

        self._populate_companies()

        # Connect topbar signals now that companies and tabs exist
        try:
            try:
                self.topbar.blockSignals(True)
            except Exception:
                pass

            try:
                keys = list(self.companies.keys())
                if keys:
                    if hasattr(self.topbar, "set_current_company"):
                        self.topbar.set_current_company(keys[0])
                    elif hasattr(self.topbar, "select_company_by_name"):
                        self.topbar.select_company_by_name(keys[0])
            except Exception:
                pass

            try:
                self.topbar.company_changed.connect(self._on_company_change_from_topbar)
                self.topbar.new_clicked.connect(self._on_topbar_new)
                self.topbar.save_clicked.connect(self._on_topbar_save)
                self.topbar.preview_clicked.connect(self._on_topbar_preview)
                self.topbar.export_clicked.connect(self._on_topbar_export)
                self.topbar.filter_clicked.connect(self._on_topbar_filter)
            except Exception:
                pass

        finally:
            try:
                self.topbar.blockSignals(False)
            except Exception:
                pass

        self._on_company_change()

    def _on_sidebar_section_changed(self, section_name: str):
        index = self.section_index_map.get(section_name, 0)
        if section_name == "configuración":
            dlg = ConfigLauncherDialog(self, logic=self.logic, hybrid_logic=self.hybrid_logic)
            dlg.exec()
            if hasattr(self, '_previous_section_index'):
                self.stacked_widget.setCurrentIndex(self._previous_section_index)
            return
        self._previous_section_index = self.stacked_widget.currentIndex()
        self.stacked_widget.setCurrentIndex(index)
        context = self.index_context_map.get(index, "")
        try:
            self.topbar.set_context(context)
        except Exception:
            pass

    def _on_company_change_from_topbar(self, company_name: str):
        self._on_company_change()

    def _on_topbar_new(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index == 0:
            try:
                if hasattr(self.invoice_tab, "_limpiar_formulario"):
                    self.invoice_tab._limpiar_formulario()
                else:
                    self.invoice_tab.on_company_change()
            except Exception:
                pass
        elif current_index == 1:
            try:
                if hasattr(self.quotation_tab, "_limpiar_formulario"):
                    self.quotation_tab._limpiar_formulario()
                else:
                    self.quotation_tab.on_company_change()
            except Exception:
                pass

    def _on_topbar_save(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index == 0:
            try:
                if hasattr(self.invoice_tab, "_guardar_factura"):
                    self.invoice_tab._guardar_factura()
                else:
                    self.invoice_tab._save_invoice()
            except Exception:
                pass
        elif current_index == 1:
            try:
                if hasattr(self.quotation_tab, "_guardar_cotizacion"):
                    self.quotation_tab._guardar_cotizacion()
                else:
                    self.quotation_tab._save_quotation()
            except Exception:
                pass

    def _on_topbar_preview(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index == 0:
            try:
                if hasattr(self.invoice_tab, "_vista_previa"):
                    self.invoice_tab._vista_previa()
                else:
                    self.invoice_tab._preview_invoice()
            except Exception:
                pass
        elif current_index == 1:
            try:
                if hasattr(self.quotation_tab, "_vista_previa"):
                    self.quotation_tab._vista_previa()
                else:
                    self.quotation_tab._preview_quotation()
            except Exception:
                pass

    def _on_topbar_export(self):
        current_index = self.stacked_widget.currentIndex()
        try:
            if current_index == 0 and hasattr(self.invoice_tab, "_exportar_factura"):
                self.invoice_tab._exportar_factura()
            elif current_index == 1 and hasattr(self.quotation_tab, "_exportar_cotizacion"):
                self.quotation_tab._exportar_cotizacion()
        except Exception:
            pass

    def _on_topbar_filter(self):
        current_index = self.stacked_widget.currentIndex()
        try:
            if current_index == 2 and hasattr(self.invoice_history_tab, 'toggle_filters'):
                self.invoice_history_tab.toggle_filters()
            elif current_index == 3 and hasattr(self.quotation_history_tab, 'toggle_filters'):
                self.quotation_history_tab.toggle_filters()
        except Exception:
            pass

    def _setup_menu(self):
        menu_bar = QMenuBar(self); self.setMenuBar(menu_bar)
        archivo_menu = QMenu("&Archivo", self); menu_bar.addMenu(archivo_menu)

        abrir_base_action = QAction("Abrir Base de Datos...", self)
        abrir_base_action.triggered.connect(self._abrir_base_de_datos)
        archivo_menu.addAction(abrir_base_action)

        crear_base_action = QAction("Crear Nueva Base de Datos...", self)
        crear_base_action.triggered.connect(self._crear_nueva_base_de_datos)
        archivo_menu.addAction(crear_base_action)

        backup_action = QAction("Hacer Backup...", self)
        backup_action.triggered.connect(self._hacer_backup)
        archivo_menu.addAction(backup_action)

        archivo_menu.addSeparator()
        salir_action = QAction("Salir", self); salir_action.triggered.connect(self.close)
        archivo_menu.addAction(salir_action)

        reportes_menu = QMenu("&Reportes", self); menu_bar.addMenu(reportes_menu)
        reporte_ventas_action = QAction("📊 Reporte de Ventas", self)
        reporte_ventas_action.triggered.connect(self._abrir_reporte_ventas)
        reportes_menu.addAction(reporte_ventas_action)
        reporte_clientes_action = QAction("👥 Reporte por Cliente", self)
        reporte_clientes_action.triggered.connect(self._abrir_reporte_clientes)
        reportes_menu.addAction(reporte_clientes_action)

        herramientas_menu = QMenu("&Herramientas", self); menu_bar.addMenu(herramientas_menu)
        migrar_firebase_action = QAction("🔄 Migrar a Firebase...", self)
        migrar_firebase_action.setShortcut("Ctrl+Shift+M")
        migrar_firebase_action.setToolTip("Migrar datos de SQLite a Firebase")
        migrar_firebase_action.triggered.connect(self._abrir_dialogo_migracion)
        herramientas_menu.addAction(migrar_firebase_action)

        ncf_config_action = QAction("🔢 Configurar Secuencias NCF...", self)
        ncf_config_action.setShortcut("Ctrl+Shift+N")
        ncf_config_action.setToolTip("Configurar secuencias de NCF por empresa y tipo de comprobante")
        ncf_config_action.triggered.connect(self._abrir_configuracion_ncf)
        herramientas_menu.addAction(ncf_config_action)

        herramientas_menu.addSeparator()

        firebase_config_action = QAction("🔥 Configurar Firebase...", self)
        firebase_config_action.setShortcut("Ctrl+Shift+F")
        firebase_config_action.setToolTip("Configurar credenciales de Firebase")
        firebase_config_action.triggered.connect(self._abrir_configuracion_firebase)
        herramientas_menu.addAction(firebase_config_action)

        apariencias_menu = QMenu("🎨 &Apariencias", self); menu_bar.addMenu(apariencias_menu)
        self._setup_theme_menu(apariencias_menu)

        opciones_menu = QMenu("&Opciones", self); menu_bar.addMenu(opciones_menu)
        config_rutas_action = QAction("Configurar Rutas...", self)
        config_rutas_action.triggered.connect(self._abrir_configuracion)
        opciones_menu.addAction(config_rutas_action)

        gestionar_empresas_action = QAction("Gestionar Empresas...", self)
        gestionar_empresas_action.triggered.connect(self._abrir_gestion_empresas)
        opciones_menu.addAction(gestionar_empresas_action)

        gestion_items_action = QAction("Gestionar Ítems...", self)
        gestion_items_action.triggered.connect(self._abrir_gestion_items)
        opciones_menu.addAction(gestion_items_action)

        action_edit_template = QAction("Editar plantilla...", self)
        action_edit_template.setStatusTip("Editar plantilla para la empresa seleccionada")
        action_edit_template.triggered.connect(self._menu_edit_template)
        opciones_menu.addAction(action_edit_template)

    def _setup_theme_menu(self, menu: QMenu):
        try:
            from utils.theme_manager import get_available_themes, get_theme_manager

            themes = get_available_themes()
            theme_manager = get_theme_manager()

            if isinstance(themes, dict):
                theme_entries = list(themes.items())
            elif isinstance(themes, list):
                theme_entries = [(t, t) for t in themes]
            else:
                try:
                    theme_entries = [(t, t) for t in list(themes)]
                except Exception:
                    theme_entries = []

            if not theme_entries:
                placeholder = QAction("(Temas no disponibles)", self)
                placeholder.setEnabled(False)
                menu.addAction(placeholder)
                return

            try:
                current = facot_config.get_theme()
            except Exception:
                current = None

            for theme_id, theme_name in theme_entries:
                action = QAction(str(theme_name), self)
                action.setCheckable(True)
                action.setData(str(theme_id))
                try:
                    action.setChecked(str(theme_id) == str(current))
                except Exception:
                    action.setChecked(False)
                action.triggered.connect(lambda checked, t=theme_id: self._apply_theme(t))
                menu.addAction(action)

        except Exception as e:
            print(f"[THEME] Error configurando menú de temas: {e}")
            placeholder = QAction("(Temas no disponibles)", self)
            placeholder.setEnabled(False)
            menu.addAction(placeholder)

    def _apply_theme(self, theme_id: str):
        try:
            from utils.theme_manager import get_theme_manager
            from PyQt6.QtWidgets import QApplication

            theme_manager = get_theme_manager()
            theme_manager.set_app(QApplication.instance())

            if theme_manager.save_and_apply_theme(theme_id):
                self._update_theme_menu_checks(theme_id)
                QMessageBox.information(self, "Tema aplicado", f"El tema '{theme_id}' se ha aplicado correctamente.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo aplicar el tema: {e}")

    def _update_theme_menu_checks(self, current_theme: str):
        for menu in self.menuBar().findChildren(QMenu):
            if "Apariencias" in menu.title():
                for action in menu.actions():
                    action_theme_id = action.data()
                    if action_theme_id:
                        action.setChecked(action_theme_id == current_theme)

    def _abrir_configuracion_firebase(self):
        try:
            from dialogs.firebase_config_dialog import FirebaseConfigDialog

            dialog = FirebaseConfigDialog(self)
            if dialog.exec():
                QMessageBox.information(self, "Firebase Configurado", "La configuración de Firebase se ha guardado.\n\nPor favor, reinicie la aplicación para aplicar los cambios.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir la configuración de Firebase:\n{e}")

    def _abrir_reporte_ventas(self):
        try:
            from dialogs.reports_dialog import SalesReportDialog
            dialog = SalesReportDialog(self.hybrid_logic or self.logic, self)
            dialog.exec()
        except ImportError:
            QMessageBox.information(self, "Reporte de Ventas", "El módulo de reportes está en desarrollo.\n\nPróximamente podrá generar reportes de ventas por período.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error abriendo reporte de ventas: {e}")

    def _abrir_reporte_clientes(self):
        try:
            from dialogs.reports_dialog import ClientsReportDialog
            dialog = ClientsReportDialog(self.hybrid_logic or self.logic, self)
            dialog.exec()
        except ImportError:
            QMessageBox.information(self, "Reporte por Cliente", "El módulo de reportes está en desarrollo.\n\nPróximamente podrá generar reportes por cliente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error abriendo reporte de clientes: {e}")

    def _abrir_base_de_datos(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Abrir Base de Datos", "", "Database Files (*.db);;Todos los archivos (*)")
        if filename:
            facot_config.set_db_path(filename)
            self.logic = LogicController(filename)
            get_company = lambda: (self.companies or {}).get(self.topbar.get_current_company() or "")
            self.invoice_tab.logic = self.logic; self.quotation_tab.logic = self.logic
            self.invoice_history_tab.logic = self.logic; self.quotation_history_tab.logic = self.logic
            self.data_access = None
            self.hybrid_logic = HybridLogicWrapper(self.logic, None)
            self._populate_companies()
            self._on_company_change()
            QMessageBox.information(self, "Base de Datos", "Base de datos abierta correctamente.")

    def _crear_nueva_base_de_datos(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Crear Nueva Base de Datos", "", "Database Files (*.db);;Todos los archivos (*)")
        if filename:
            facot_config.set_db_path(filename)
            self.logic = LogicController(filename)
            self.data_access = None
            self.hybrid_logic = HybridLogicWrapper(self.logic, None)
            self._populate_companies()
            self._on_company_change()
            QMessageBox.information(self, "Base de Datos", "Nueva base de datos creada correctamente.")

    def _hacer_backup(self):
        import shutil
        db_path = self.logic.db_path
        backup_path, _ = QFileDialog.getSaveFileName(self, "Guardar Backup de la Base de Datos", "", "Database Files (*.db);;Todos los archivos (*)")
        if backup_path:
            shutil.copy2(db_path, backup_path)
            QMessageBox.information(self, "Backup", f"Backup guardado en:\n{backup_path}")

    def _abrir_configuracion(self):
        backend = self.hybrid_logic if self.hybrid_logic else self.logic
        dlg = SettingsWindow(backend, self)
        dlg.exec()

    def _abrir_gestion_empresas(self):
        backend = self.hybrid_logic if self.hybrid_logic else self.logic
        dlg = CompanyManagementWindow(self, backend)
        dlg.exec()
        self._populate_companies()
        self._on_company_change()

    def _abrir_configuracion_firebase(self):
        from dialogs.firebase_config_dialog import FirebaseConfigDialog
        dialog = FirebaseConfigDialog(self)
        dialog.exec()

    def _abrir_gestion_items(self):
        backend = self.hybrid_logic if self.hybrid_logic else self.logic
        dlg = ItemsManagementWindow(self, backend=backend)
        dlg.exec()

    def _abrir_dialogo_migracion(self):
        from dialogs.migration_dialog import MigrationDialog
        dialog = MigrationDialog(self)
        dialog.exec()

    def _abrir_configuracion_ncf(self):
        from dialogs.ncf_config_dialog import NCFConfigDialog
        backend = self.hybrid_logic if self.hybrid_logic else self.logic
        dialog = NCFConfigDialog(backend, self)
        dialog.exec()

    def _populate_companies(self):
        try:
            if self.hybrid_logic and hasattr(self.hybrid_logic, 'get_all_companies'):
                companies = self.hybrid_logic.get_all_companies() or []
            elif self.data_access and hasattr(self.data_access, 'get_all_companies'):
                companies = self.data_access.get_all_companies() or []
            elif self.logic and hasattr(self.logic, 'get_all_companies'):
                companies = self.logic.get_all_companies() or []
            else:
                companies = []
        except Exception as e:
            print(f"[MainWindow] Error obteniendo companies: {e}")
            companies = []

        try:
            self.companies = {str(c.get('name')): c for c in (companies or []) if c.get('name')}
        except Exception:
            self.companies = {}

        if hasattr(self, 'topbar'):
            try:
                self.topbar.blockSignals(True)
            except Exception:
                pass
            try:
                if hasattr(self.topbar, "set_companies"):
                    self.topbar.set_companies(list(self.companies.keys()))
            except Exception as e:
                print(f"[MainWindow] topbar.set_companies error: {e}")
            finally:
                try:
                    self.topbar.blockSignals(False)
                except Exception:
                    pass

    def _on_company_change(self):
        if hasattr(self, "invoice_tab"):
            try:
                self.invoice_tab.on_company_change()
            except Exception as e:
                print(f"[MainWindow] invoice_tab.on_company_change error: {e}")
        if hasattr(self, "quotation_tab"):
            try:
                self.quotation_tab.on_company_change()
            except Exception as e:
                print(f"[MainWindow] quotation_tab.on_company_change error: {e}")
        if hasattr(self, "invoice_history_tab"):
            try:
                self.invoice_history_tab.refresh()
            except Exception as e:
                print(f"[MainWindow] invoice_history_tab.refresh error: {e}")
        if hasattr(self, "quotation_history_tab"):
            try:
                self.quotation_history_tab.refresh()
            except Exception as e:
                print(f"[MainWindow] quotation_history_tab.refresh error: {e}")

    def get_current_company(self):
        try:
            company_name = self.topbar.get_current_company() if hasattr(self, 'topbar') else ""
            if not company_name:
                return None
            return (self.companies or {}).get(company_name)
        except Exception:
            return None

    def get_all_companies(self):
        try:
            if self.hybrid_logic and hasattr(self.hybrid_logic, "get_all_companies"):
                return self.hybrid_logic.get_all_companies() or []
        except Exception as e:
            print(f"[MainWindow] hybrid get_all_companies error: {e}")
        try:
            if self.data_access and hasattr(self.data_access, "get_all_companies"):
                return self.data_access.get_all_companies() or []
        except Exception as e:
            print(f"[MainWindow] data_access get_all_companies error: {e}")
        try:
            if self.logic and hasattr(self.logic, "get_all_companies"):
                return self.logic.get_all_companies() or []
        except Exception as e:
            print(f"[MainWindow] logic get_all_companies error: {e}")
        return []

    def _menu_edit_template(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Plantilla", "Seleccione primero una empresa válida.")
            return

        company_id = company.get("id") or company.get("company_id") or company.get("pk")
        if not company_id:
            QMessageBox.warning(self, "Plantilla", "La empresa seleccionada no tiene identificador.")
            return

        try:
            dlg = TemplateEditorDialog(company_id=company_id, parent=self)
            if dlg.exec():
                QMessageBox.information(self, "Plantilla", "Plantilla guardada correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Plantilla", f"No se pudo abrir el editor de plantillas:\n{e}")

    def _setup_connection_status(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self.connection_status = ConnectionStatusBar(self)
        db_path = facot_config.get_db_path()
        self.connection_status.set_mode("SQLITE", db_path)

        self.connection_status.database_changed.connect(self._on_database_changed)
        self.connection_status.mode_changed.connect(self._on_connection_mode_changed)

        status_bar.addPermanentWidget(self.connection_status)

    def _check_online_status(self):
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self._on_network_check_finished)
        request = QNetworkRequest(QUrl("https://www.google.com"))
        request.setTransferTimeout(3000)
        self.network_manager.get(request)

    def _on_network_check_finished(self, reply):
        is_online = (reply.error() == 0)
        try:
            self.connection_status.set_online_status(is_online)
        except Exception:
            pass
        reply.deleteLater()

    def _detect_and_set_connection_mode(self):
        try:
            from data_access import get_current_mode, DataAccessMode
            from firebase import get_firebase_client

            is_using_firebase = (
                self.data_access is not None and
                "Firebase" in type(self.data_access).__name__
            )

            firebase_client = get_firebase_client()
            firebase_available = firebase_client.is_available()

            if is_using_firebase and firebase_available:
                self.current_access_mode = "FIREBASE"
                self.connection_status.set_mode("FIREBASE")
                self.connection_status.set_online_status(True)
                print("[MAIN] Detected Firebase mode - updating status bar")
            else:
                self.current_access_mode = "SQLITE"
                db_path = facot_config.get_db_path()
                self.connection_status.set_mode("SQLITE", db_path)
                print(f"[MAIN] Using SQLite mode: {db_path}")

        except Exception as e:
            print(f"[MAIN] Error detecting connection mode: {e}")
            self.current_access_mode = "SQLITE"
            db_path = facot_config.get_db_path()
            try:
                self.connection_status.set_mode("SQLITE", db_path)
            except Exception:
                pass

    def _on_database_changed(self, new_db_path: str):
        try:
            facot_config.set_db_path(new_db_path)
            self.logic = LogicController(new_db_path)

            from data_access import get_data_access, DataAccessMode
            try:
                self.data_access = get_data_access(logic_controller=self.logic, mode=DataAccessMode.SQLITE)
            except TypeError:
                self.data_access = get_data_access(mode=DataAccessMode.SQLITE)
            self.current_access_mode = "SQLITE"

            # Recreate hybrid wrapper
            self.hybrid_logic = HybridLogicWrapper(self.logic, self.data_access)

            self._populate_companies()

            try:
                self.invoice_tab.logic = self.logic
                self.quotation_tab.logic = self.logic
                self.invoice_history_tab.logic = self.logic
                self.quotation_history_tab.logic = self.logic
            except Exception:
                pass

            self._on_company_change()

            QMessageBox.information(self, "Base de Datos", f"Base de datos cambiada exitosamente:\n{os.path.basename(new_db_path)}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cambiar la base de datos:\n{str(e)}")

    def _on_connection_mode_changed(self, new_mode: str):
        try:
            from data_access import set_data_access_mode, DataAccessMode, get_data_access

            mode_map = {
                "SQLITE": DataAccessMode.SQLITE,
                "FIREBASE": DataAccessMode.FIREBASE,
                "AUTO": DataAccessMode.AUTO
            }

            mode = mode_map.get(new_mode.upper())
            if mode:
                set_data_access_mode(mode)
                self.current_access_mode = new_mode.upper()

                try:
                    if mode == DataAccessMode.SQLITE:
                        self.data_access = get_data_access(logic_controller=self.logic, mode=mode)
                    elif mode == DataAccessMode.FIREBASE:
                        self.data_access = get_data_access(user_id=None, mode=mode)
                    else:
                        self.data_access = get_data_access(logic_controller=self.logic, user_id=None, mode=mode)

                    # Recreate hybrid wrapper
                    self.hybrid_logic = HybridLogicWrapper(self.logic, self.data_access)

                    self._populate_companies()
                    self._detect_and_set_connection_mode()

                    QMessageBox.information(self, "Modo de Conexión", f"Modo de conexión cambiado a: {new_mode}\n\nLa aplicación ahora usará {new_mode} para acceder a los datos.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"No se pudo cambiar al modo {new_mode}:\n{str(e)}\n\nRevirtiendo a SQLite.")
                    set_data_access_mode(DataAccessMode.SQLITE)
                    self.data_access = get_data_access(logic_controller=self.logic, mode=DataAccessMode.SQLITE)
                    self.hybrid_logic = HybridLogicWrapper(self.logic, self.data_access)
                    self.current_access_mode = "SQLITE"
                    self._detect_and_set_connection_mode()

                if new_mode in ["FIREBASE", "AUTO"]:
                    self._check_firebase_availability()

        except ImportError:
            QMessageBox.warning(self, "Modo de Conexión", "El módulo de Firebase no está disponible.\nSolo se puede usar SQLite.")

    def _check_firebase_availability(self):
        try:
            from firebase import get_firebase_client
            client = get_firebase_client()
            if not client.is_available():
                QMessageBox.warning(self, "Firebase", "Firebase no está disponible o no está configurado correctamente.\n\nVerifique que:\n1. firebase-admin esté instalado (pip install firebase-admin)\n2. El archivo de credenciales exista\n3. Las credenciales sean válidas\n\nLa aplicación usará SQLite como fallback.")
        except Exception as e:
            QMessageBox.warning(self, "Firebase", f"Error al verificar Firebase:\n{str(e)}\n\nLa aplicación usará SQLite como fallback.")


# Small launcher dialog for configuration (kept near MainWindow for cohesion)
class ConfigLauncherDialog(QDialog):
    def __init__(self, parent=None, logic=None, hybrid_logic=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setMinimumWidth(420)
        self.logic = logic
        self.hybrid_logic = hybrid_logic
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Configuración</b>"))
        layout.addSpacing(8)

        btn_appearance = QPushButton("Apariencia")
        btn_appearance.clicked.connect(self._open_appearance)
        layout.addWidget(btn_appearance)

        btn_companies = QPushButton("Gestionar Empresas")
        btn_companies.clicked.connect(self._open_companies)
        layout.addWidget(btn_companies)

        btn_paths = QPushButton("Rutas y Archivos")
        btn_paths.clicked.connect(self._open_paths)
        layout.addWidget(btn_paths)

        btn_ncf = QPushButton("Configurar Secuencias NCF")
        btn_ncf.clicked.connect(self._open_ncf)
        layout.addWidget(btn_ncf)

        btn_firebase = QPushButton("Configurar Firebase")
        btn_firebase.clicked.connect(self._open_firebase)
        layout.addWidget(btn_firebase)

        layout.addStretch(1)
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(btn_close)
        layout.addLayout(h)

    def _open_appearance(self):
        try:
            backend = self.hybrid_logic if self.hybrid_logic else self.logic
            dlg = SettingsWindow(backend, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir Apariencia:\n{e}")

    def _open_companies(self):
        try:
            backend = self.hybrid_logic if self.hybrid_logic else self.logic
            dlg = CompanyManagementWindow(self, backend)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Empresas", f"No se pudo abrir gestión de empresas:\n{e}")

    def _open_paths(self):
        try:
            backend = self.hybrid_logic if self.hybrid_logic else self.logic
            dlg = SettingsWindow(backend, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir Rutas y Archivos:\n{e}")

    def _open_ncf(self):
        try:
            backend = self.hybrid_logic if self.hybrid_logic else self.logic
            from dialogs.ncf_config_dialog import NCFConfigDialog
            dlg = NCFConfigDialog(backend, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "NCF", f"No se pudo abrir configuración NCF:\n{e}")

    def _open_firebase(self):
        try:
            from dialogs.firebase_config_dialog import FirebaseConfigDialog
            dlg = FirebaseConfigDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Firebase", f"No se pudo abrir configuración Firebase:\n{e}")