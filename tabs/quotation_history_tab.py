from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QWidget as QWidgetAlias, QFileDialog, QMessageBox, QHeaderView, QSizePolicy
)
from PyQt6.QtCore import QSize, Qt

logger = logging.getLogger(__name__)

# Dependencies that can fail — import defensivo y fallback
QuotationPreviewDialog = None
try:
    from dialogs.quotation_preview_dialog import QuotationPreviewDialog
except Exception as e:
    logger.debug("Aviso: QuotationPreviewDialog no disponible: %s", e)
    QuotationPreviewDialog = None

# Carga de plantilla
try:
    from utils.template_manager import load_template
except Exception as e:
    logger.debug("Aviso: utils.template_manager.load_template no disponible: %s", e)
    def load_template(company_id: int):
        return {}

# Resolver logo relativo -> file:///
try:
    from utils.asset_paths import resolve_logo_uri
except Exception as e:
    logger.debug("Aviso: utils.asset_paths.resolve_logo_uri no disponible: %s", e)
    def resolve_logo_uri(path):
        return path or ""

try:
    from utils.template_integration import export_quotation_pdf_with_template, export_quotation_excel_with_template
except Exception as e:
    logger.debug("Aviso: utils.template_integration funciones no disponibles: %s", e)
    def export_quotation_pdf_with_template(*args, **kwargs):
        raise RuntimeError("export_quotation_pdf_with_template no disponible")
    def export_quotation_excel_with_template(*args, **kwargs):
        raise RuntimeError("export_quotation_excel_with_template no disponible")

# IconManager fallback
IconManager = None
try:
    from icon_manager import IconManager
except Exception as e:
    logger.debug("Aviso: icon_manager no disponible: %s", e)
    IconManager = None

# Constants (puede lanzar si falta)
try:
    from constants import ITBIS_RATE
except Exception:
    ITBIS_RATE = 0.18

class QuotationHistoryTab(QWidget):
    def __init__(self, logic, get_current_company_callable, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable
        self._build_ui()
        # safe refresh: si falla, no rompa el import
        try:
            self.refresh()
        except Exception as e:
            logger.exception("Error al refrescar QuotationHistoryTab en init: %s", e)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Title
        title_label = QLabel("Historial de Cotizaciones")
        title_label.setProperty("heading", True)
        layout.addWidget(title_label)
        
        # Filter row (initially visible)
        from PyQt6.QtWidgets import QDateEdit, QLineEdit
        from PyQt6.QtCore import QDate
        
        self.filter_widget = QWidget()
        self.filter_widget.setProperty("filterRow", True)
        filter_layout = QHBoxLayout(self.filter_widget)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        
        # Date range filters
        filter_layout.addWidget(QLabel("Desde:"))
        self.filter_date_from = QDateEdit()
        self.filter_date_from.setCalendarPopup(True)
        self.filter_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.filter_date_from.dateChanged.connect(self.refresh)
        filter_layout.addWidget(self.filter_date_from)
        
        filter_layout.addWidget(QLabel("Hasta:"))
        self.filter_date_to = QDateEdit()
        self.filter_date_to.setCalendarPopup(True)
        self.filter_date_to.setDate(QDate.currentDate())
        self.filter_date_to.dateChanged.connect(self.refresh)
        filter_layout.addWidget(self.filter_date_to)
        
        # Client filter
        filter_layout.addWidget(QLabel("Cliente:"))
        self.filter_client = QLineEdit()
        self.filter_client.setPlaceholderText("Buscar por nombre...")
        self.filter_client.textChanged.connect(self.refresh)
        filter_layout.addWidget(self.filter_client)
        
        filter_layout.addStretch(1)
        
        # Clear filters button
        btn_clear_filters = QPushButton("Limpiar filtros")
        btn_clear_filters.setProperty("flat", True)
        btn_clear_filters.clicked.connect(self._clear_filters)
        filter_layout.addWidget(btn_clear_filters)
        
        layout.addWidget(self.filter_widget)
        
        # Table - add actions column
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "Fecha", "Cliente", "RNC", "Moneda", "Total", "Notas", "Acciones"])
        header = self.table.horizontalHeader()
        # Make columns stretch except actions which is fixed
        for i in range(self.table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        actions_col = self.table.columnCount() - 1
        header.setSectionResizeMode(actions_col, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(actions_col, 240)  # Increased width

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        layout.addWidget(self.table)
        
        # Refresh button
        btn_refresh = QPushButton("Refrescar Historial")
        btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(btn_refresh)
    
    def _clear_filters(self):
        """Clear all filters and refresh"""
        from PyQt6.QtCore import QDate
        self.filter_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.filter_date_to.setDate(QDate.currentDate())
        self.filter_client.clear()
        self.refresh()
    
    def toggle_filters(self):
        """Toggle filter visibility"""
        if hasattr(self, 'filter_widget'):
            self.filter_widget.setVisible(not self.filter_widget.isVisible())

    def refresh(self):
        company = self.get_current_company()
        if not company:
            return
        try:
            cotizaciones = self.logic.get_quotations(company['id']) if hasattr(self.logic, "get_quotations") else []
        except Exception as e:
            logger.exception("Error al obtener cotizaciones: %s", e)
            cotizaciones = []

        self.table.setRowCount(0)
        for q in cotizaciones:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(q.get('id', ''))))
            self.table.setItem(row, 1, QTableWidgetItem(q.get('quotation_date', '')))
            self.table.setItem(row, 2, QTableWidgetItem(q.get('client_name', '')))
            self.table.setItem(row, 3, QTableWidgetItem(q.get('client_rnc', '')))
            self.table.setItem(row, 4, QTableWidgetItem(q.get('currency', '')))
            total = q.get('total_amount', q.get('total', 0.0)) or 0.0
            self.table.setItem(row, 5, QTableWidgetItem(f"{total:,.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(q.get('notes', '')))
            # actions
            try:
                self._add_quotation_action_buttons(row, q)
            except Exception:
                logger.exception("Error añadiendo boton de acciones para cotizacion id=%s", q.get('id'))

    def _add_quotation_action_buttons(self, row: int, record: Dict[str, Any]):
            """
            Añade botones de acción modernos (solo icono) estilizados por QSS.
            """
            widget = QWidgetAlias()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(8)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Botón PREVIEW (Ojo)
            btn_preview = QPushButton()
            btn_preview.setObjectName("actionButton")  # ID para CSS (themes/style_template.qss)
            btn_preview.setToolTip("Ver detalle / Vista previa")
            btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_preview.setFixedSize(32, 32)
            
            # Cargar Icono (Intenta SVG, fallback a texto unicode limpio)
            icon_path = os.path.join(os.getcwd(), "assets", "icons", "eye.svg")
            if os.path.exists(icon_path):
                from PyQt6.QtGui import QIcon
                btn_preview.setIcon(QIcon(icon_path))
                btn_preview.setIconSize(QSize(20, 20))
            else:
                btn_preview.setText("👁") # Fallback visual

            layout.addWidget(btn_preview)
            widget.setLayout(layout)

            # Ajustar altura fila para que el botón respire
            self.table.setRowHeight(row, 44)

            # Conectar acción
            btn_preview.clicked.connect(lambda _, rec=record: self._open_quotation_preview(rec))

            # Insertar en la última columna (Acciones)
            actions_col = self.table.columnCount() - 1
            try:
                self.table.setCellWidget(row, actions_col, widget)
            except Exception:
                # Fallback seguro por si la columna no es la última por alguna razón
                for c in range(self.table.columnCount()):
                    header_item = self.table.horizontalHeaderItem(c)
                    if header_item and header_item.text().strip().lower() == "acciones":
                        self.table.setCellWidget(row, c, widget)
                        break


    def _resolve_company_and_template(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        company = self.get_current_company() or {}
        tpl = {}
        try:
            tpl = load_template(int(company.get('id')))
        except Exception:
            tpl = {}
        company_data = {
            "id": company.get('id'),
            "name": company.get('name'),
            "rnc": company.get('rnc') or company.get('rnc_number') or "",
            "address_line1": company.get('address') or company.get('address_line1') or "",
            "address_line2": company.get('address_line2') or "",
            "phone": company.get('phone') or company.get('telefono') or "",
            "email": company.get('email') or company.get('correo') or "",
            "logo_path": ""
        }
        # Resolver logo relativo usando assets_root
        logo_rel = tpl.get("logo_path") or company.get("logo_path") or ""
        company_data["logo_path"] = resolve_logo_uri(logo_rel) or ""
        return company_data, tpl

    def _get_record_items(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = record.get('items') or record.get('details') or []
        if not items and hasattr(self.logic, "get_quotation_items"):
            try:
                items = self.logic.get_quotation_items(record.get('id'))
            except Exception:
                items = []
        normalized = []
        for it in items:
            normalized.append({
                "code": it.get("code") or it.get("codigo") or "",
                "description": it.get("description") or it.get("descripcion") or "",
                "unit": it.get("unit") or it.get("unidad") or "",
                "quantity": float(it.get("quantity", it.get("cantidad", 0)) or 0),
                "unit_price": float(it.get("unit_price", it.get("precio", 0)) or 0)
            })
        return normalized

    def _open_quotation_preview(self, record: Dict[str, Any]):
        company_data, tpl = self._resolve_company_and_template()

        # Detectar si la cotización original tenía ITBIS
        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                total = float(record.get("total_amount", 0) or 0)
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = False  # Por defecto False en cotizaciones

        quotation_payload = {
            "id": record.get("id"),
            "number": record.get("quotation_number") or record.get("number") or "",
            "date": record.get("quotation_date") or record.get("date") or "",
            "client_name": record.get("client_name") or record.get("third_party_name") or "",
            "client_rnc": record.get("client_rnc") or record.get("rnc") or "",
            "currency": record.get("currency") or "",
            "items": self._get_record_items(record),
            "notes": record.get("notes", "") or "",
            "apply_itbis": apply_itbis,
        }

        if QuotationPreviewDialog is None:
            QMessageBox.warning(self, "Vista Previa", "QuotationPreviewDialog no disponible.")
            return

        template_path = os.path.join(os.getcwd(), "templates", "quotation_template.html")
        dlg = QuotationPreviewDialog(company=company_data, template=tpl, quotation=quotation_payload, parent=self, template_path=template_path, debug=False)
        dlg.exec()

    def _export_quotation_pdf(self, record: Dict[str, Any]):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida"); return

        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = False

        invoice_payload = {
            "company_id": record.get("company_id", company.get('id')),
            "company_name": company.get('name', ''),
            "quotation_date": record.get("quotation_date", ""),
            "quotation_number": record.get("quotation_number") or record.get("number") or "",
            "client_name": record.get("client_name") or record.get("third_party_name") or "",
            "client_rnc": record.get("client_rnc") or record.get("rnc") or "",
            "apply_itbis": apply_itbis,
            "itbis_rate": ITBIS_RATE
        }
        items = self._get_record_items(record)
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Cotización como PDF", f"cotizacion_{invoice_payload.get('quotation_number','')}.pdf", "PDF Files (*.pdf)")
        if not fn:
            return
        save_path = fn if fn.lower().endswith(".pdf") else fn + ".pdf"
        try:
            export_quotation_pdf_with_template(invoice_payload, items, save_path, company_name=company.get('name',''))
            QMessageBox.information(self, "PDF", f"Cotización guardada como PDF en:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar la cotización a PDF:\n{e}")

    def _export_quotation_excel(self, record: Dict[str, Any]):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida"); return

        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = False

        invoice_payload = {
            "company_id": record.get("company_id", company.get('id')),
            "company_name": company.get('name', ''),
            "quotation_date": record.get("quotation_date", ""),
            "quotation_number": record.get("quotation_number") or record.get("number") or "",
            "client_name": record.get("client_name") or record.get("third_party_name") or "",
            "client_rnc": record.get("client_rnc") or record.get("rnc") or "",
            "apply_itbis": apply_itbis,
            "itbis_rate": ITBIS_RATE
        }
        items = self._get_record_items(record)
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Cotización como Excel", f"cotizacion_{invoice_payload.get('quotation_number','')}.xlsx", "Excel Files (*.xlsx)")
        if not fn:
            return
        save_path = fn if fn.lower().endswith(".xlsx") else fn + ".xlsx"
        try:
            export_quotation_excel_with_template(invoice_payload, items, save_path, company_name=company.get('name',''))
            QMessageBox.information(self, "Excel", f"Cotización guardada como Excel en:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar la cotización a Excel:\n{e}")