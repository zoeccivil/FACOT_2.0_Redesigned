from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Tuple, Set

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QWidget as QWidgetAlias, QFileDialog, QMessageBox, QHeaderView, QSizePolicy
)
from PyQt6.QtCore import QSize, Qt, QDate

logger = logging.getLogger(__name__)

# Tipos de categoría/tipo de factura que se consideran "ingresos" (ventas)
INVOICE_TYPE_INGRESOS: Set[str] = {
    "INGRESO",
    "FACTURA",
    "FACTURA PRIVADA",
    "EMITIDA",
    "VENTA",
    "CREDITO FISCAL",
    "CONSUMIDOR FINAL",
    "GUBERNAMENTAL",
    "REGIMEN ESPECIAL",
    "EXPORTACION",
}

# Prefijos NCF que corresponden a comprobantes de venta/ingreso
NCF_PREFIX_INGRESOS: Set[str] = {
    "B01", "B02", "B14", "B15", "B16",
}

INGRESO_TYPES: Set[str] = INVOICE_TYPE_INGRESOS | NCF_PREFIX_INGRESOS

# Optional dependencies with safe fallbacks
InvoicePreviewDialog = None
try:
    from dialogs.invoice_preview_dialog import InvoicePreviewDialog
except Exception as e:
    logger.debug("Aviso: InvoicePreviewDialog no disponible: %s", e)
    InvoicePreviewDialog = None

try:
    from utils.template_manager import load_template
except Exception as e:
    logger.debug("Aviso: utils.template_manager.load_template no disponible: %s", e)
    def load_template(company_id: int):
        return {}

try:
    from utils.asset_paths import resolve_logo_uri
except Exception as e:
    logger.debug("Aviso: utils.asset_paths.resolve_logo_uri no disponible: %s", e)
    def resolve_logo_uri(p): return p or ""

try:
    from utils.template_integration import export_invoice_pdf_with_template, export_invoice_excel_with_template
except Exception as e:
    logger.debug("Aviso: utils.template_integration no disponible: %s", e)
    def export_invoice_pdf_with_template(*args, **kwargs):
        raise RuntimeError("export_invoice_pdf_with_template no disponible")
    def export_invoice_excel_with_template(*args, **kwargs):
        raise RuntimeError("export_invoice_excel_with_template no disponible")


class InvoiceHistoryTab(QWidget):
    def __init__(self, logic, get_current_company_callable, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable
        self._build_ui()
        try:
            self.refresh()
        except Exception as e:
            logger.exception("Error al refrescar InvoiceHistoryTab en init: %s", e)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title_label = QLabel("Historial de Facturas")
        title_label.setProperty("heading", True)
        layout.addWidget(title_label)

        from PyQt6.QtWidgets import QDateEdit, QLineEdit
        self.filter_widget = QWidget()
        self.filter_widget.setProperty("filterRow", True)
        filter_layout = QHBoxLayout(self.filter_widget)
        filter_layout.setContentsMargins(12, 8, 12, 8)

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

        filter_layout.addWidget(QLabel("Cliente:"))
        self.filter_client = QLineEdit()
        self.filter_client.setPlaceholderText("Buscar por nombre...")
        self.filter_client.textChanged.connect(self.refresh)
        filter_layout.addWidget(self.filter_client)

        filter_layout.addStretch(1)
        btn_clear_filters = QPushButton("Limpiar filtros")
        btn_clear_filters.setProperty("flat", True)
        btn_clear_filters.clicked.connect(self._clear_filters)
        filter_layout.addWidget(btn_clear_filters)
        layout.addWidget(self.filter_widget)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "Fecha", "NCF", "Cliente", "RNC", "Moneda", "Total", "Acciones"])
        header = self.table.horizontalHeader()
        for i in range(self.table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        actions_col = self.table.columnCount() - 1
        header.setSectionResizeMode(actions_col, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(actions_col, 320)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        layout.addWidget(self.table)

        btn_refresh = QPushButton("Refrescar Historial")
        btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(btn_refresh)

    def _clear_filters(self):
        from PyQt6.QtCore import QDate
        self.filter_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.filter_date_to.setDate(QDate.currentDate())
        self.filter_client.clear()
        self.refresh()

    def toggle_filters(self):
        if hasattr(self, 'filter_widget'):
            self.filter_widget.setVisible(not self.filter_widget.isVisible())

    def _filter_ingreso_invoices(self, facturas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered = []
        for inv in facturas:
            invoice_type = (inv.get('type') or inv.get('invoice_type') or inv.get('category') or inv.get('invoice_category') or '') or ''
            invoice_type = invoice_type.upper().strip()
            ncf = (inv.get('invoice_number') or inv.get('ncf') or '') or ''
            ncf = ncf.upper()
            ncf_prefix = ncf[:3] if len(ncf) >= 3 else ''
            if invoice_type in INGRESO_TYPES or ncf_prefix in INGRESO_TYPES:
                filtered.append(inv)
            elif (not invoice_type) and ncf:
                filtered.append(inv)
        return filtered

    def _parse_date_str(self, value: Any) -> str:
        if not value:
            return ""
        try:
            if isinstance(value, str):
                s = value.strip()
                if len(s) >= 10:
                    return s[:10]
                return s
            try:
                return value.strftime("%Y-%m-%d")
            except Exception:
                return str(value)[:10]
        except Exception:
            return ""

    def refresh(self):
        company = self.get_current_company()
        if not company:
            return
        try:
            facturas = self.logic.get_facturas(company['id']) if hasattr(self.logic, "get_facturas") else []
        except Exception as e:
            logger.exception("Error obteniendo facturas: %s", e)
            facturas = []

        facturas = self._filter_ingreso_invoices(facturas)

        client_q = (self.filter_client.text() or "").strip().lower()
        from_date = self.filter_date_from.date().toString("yyyy-MM-dd")
        to_date = self.filter_date_to.date().toString("yyyy-MM-dd")

        self.table.setRowCount(0)
        for f in facturas:
            date_val = (f.get("invoice_date") or f.get("date") or f.get("created_at") or f.get("issued_at") or "")
            date_str = self._parse_date_str(date_val)
            date_ok = True
            if date_str:
                try:
                    date_ok = (date_str >= from_date and date_str <= to_date)
                except Exception:
                    date_ok = True

            client_name = (f.get("third_party_name") or f.get("client_name") or "").strip()
            client_ok = True
            if client_q:
                client_ok = client_q in client_name.lower()

            if not (date_ok and client_ok):
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(f.get('id', ''))))
            self.table.setItem(row, 1, QTableWidgetItem(date_str or (f.get('invoice_date', '') or f.get('date', '') or "")))
            self.table.setItem(row, 2, QTableWidgetItem(f.get('invoice_number', '') or f.get('ncf', '')))
            self.table.setItem(row, 3, QTableWidgetItem(client_name))
            self.table.setItem(row, 4, QTableWidgetItem(f.get('rnc', '') or f.get('client_rnc', '')))
            self.table.setItem(row, 5, QTableWidgetItem(f.get('currency', '')))
            total = f.get('total_amount', f.get('total', 0.0)) or 0.0
            self.table.setItem(row, 6, QTableWidgetItem(f"{total:,.2f}"))
            try:
                self._add_invoice_action_buttons(row, f)
            except Exception:
                logger.exception("Error añadiendo boton de acciones para factura id=%s", f.get('id'))

    def _add_invoice_action_buttons(self, row: int, record: Dict[str, Any]):
        widget = QWidgetAlias()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_preview = QPushButton()
        btn_preview.setObjectName("actionButton")
        btn_preview.setToolTip("Ver detalle / Vista previa")
        btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_preview.setFixedSize(32, 32)
        eye_icon = os.path.join(os.getcwd(), "assets", "icons", "eye.svg")
        if os.path.exists(eye_icon):
            from PyQt6.QtGui import QIcon
            btn_preview.setIcon(QIcon(eye_icon)); btn_preview.setIconSize(QSize(20, 20))
        else:
            btn_preview.setText("👁")
        btn_preview.clicked.connect(lambda _, rec=record: self._open_invoice_preview(rec))
        layout.addWidget(btn_preview)

        btn_edit = QPushButton()
        btn_edit.setObjectName("actionButton")
        btn_edit.setToolTip("Editar factura")
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setFixedSize(32, 32)
        edit_icon = os.path.join(os.getcwd(), "assets", "icons", "edit.svg")
        if os.path.exists(edit_icon):
            from PyQt6.QtGui import QIcon
            btn_edit.setIcon(QIcon(edit_icon)); btn_edit.setIconSize(QSize(20, 20))
        else:
            btn_edit.setText("✏️")
        btn_edit.clicked.connect(lambda _, rec=record: self._edit_invoice(rec))
        layout.addWidget(btn_edit)

        btn_del = QPushButton()
        btn_del.setObjectName("actionButton")
        btn_del.setToolTip("Eliminar factura")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setFixedSize(32, 32)
        del_icon = os.path.join(os.getcwd(), "assets", "icons", "trash.svg")
        if os.path.exists(del_icon):
            from PyQt6.QtGui import QIcon
            btn_del.setIcon(QIcon(del_icon)); btn_del.setIconSize(QSize(20, 20))
        else:
            btn_del.setText("🗑")
        btn_del.clicked.connect(lambda _, rec=record: self._delete_invoice(rec))
        layout.addWidget(btn_del)

        btn_pdf = QPushButton()
        btn_pdf.setObjectName("actionButton")
        btn_pdf.setToolTip("Exportar factura a PDF")
        btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pdf.setFixedSize(32, 32)
        pdf_icon = os.path.join(os.getcwd(), "assets", "icons", "pdf.svg")
        if os.path.exists(pdf_icon):
            from PyQt6.QtGui import QIcon
            btn_pdf.setIcon(QIcon(pdf_icon)); btn_pdf.setIconSize(QSize(20, 20))
        else:
            btn_pdf.setText("PDF")
        btn_pdf.clicked.connect(lambda _, rec=record: self._export_invoice_pdf(rec))
        layout.addWidget(btn_pdf)

        btn_xls = QPushButton()
        btn_xls.setObjectName("actionButton")
        btn_xls.setToolTip("Exportar factura a Excel")
        btn_xls.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_xls.setFixedSize(32, 32)
        xls_icon = os.path.join(os.getcwd(), "assets", "icons", "xls.svg")
        if os.path.exists(xls_icon):
            from PyQt6.QtGui import QIcon
            btn_xls.setIcon(QIcon(xls_icon)); btn_xls.setIconSize(QSize(20, 20))
        else:
            btn_xls.setText("XLS")
        btn_xls.clicked.connect(lambda _, rec=record: self._export_invoice_excel(rec))
        layout.addWidget(btn_xls)

        widget.setLayout(layout)
        self.table.setRowHeight(row, 44)
        actions_col = self.table.columnCount() - 1
        try:
            self.table.setCellWidget(row, actions_col, widget)
        except Exception:
            for c in range(self.table.columnCount()):
                header_item = self.table.horizontalHeaderItem(c)
                if header_item and header_item.text().strip().lower() == "acciones":
                    self.table.setCellWidget(row, c, widget)
                    break

    def _open_invoice_preview(self, record: Dict[str, Any]):
        company_data, tpl = self._resolve_company_and_template()
        inv_type = record.get("invoice_type") or record.get("type") or "FACTURA"
        if isinstance(inv_type, str) and inv_type.lower() == "emitida":
            inv_type = "FACTURA"
        ncf_val = record.get("invoice_number") or record.get("ncf") or ""
        display_number = self._build_display_invoice_number(company_data, ncf_val, prefix_label="FACT", last_digits=6)
        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                total = float(record.get("total_amount", 0) or 0)
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = True
        invoice_payload = {
            "company_id": record.get("company_id", company_data.get("id")),
            "number": record.get("invoice_number") or record.get("number") or ncf_val,
            "ncf": ncf_val,
            "date": record.get("invoice_date") or record.get("date") or "",
            "client_name": record.get("third_party_name") or record.get("client_name") or "",
            "client_rnc": record.get("rnc") or record.get("client_rnc") or "",
            "currency": record.get("currency") or "",
            "items": self._get_record_items(record),
            "notes": record.get("notes", "") or "",
            "type": inv_type,
            "display_number": display_number,
            "apply_itbis": apply_itbis,
        }
        if InvoicePreviewDialog is None:
            QMessageBox.warning(self, "Vista Previa", "InvoicePreviewDialog no disponible.")
            return
        template_path = os.path.join(os.getcwd(), "templates", "invoice_template.html")
        dlg = InvoicePreviewDialog(company=company_data, template=tpl, invoice=invoice_payload, parent=self, template_path=template_path, debug=False)
        dlg.exec()

    def _find_invoice_tab_in_window(self):
        try:
            win = self.window()
            if win is None:
                return None
            if hasattr(win, "invoice_tab"):
                return getattr(win, "invoice_tab")
            for attr in ("invoice_tab", "tab_invoice", "main_invoice_tab"):
                if hasattr(win, attr):
                    return getattr(win, attr)
        except Exception:
            pass
        p = self.parent()
        safety = 0
        while p is not None and safety < 12:
            if hasattr(p, "invoice_tab"):
                return getattr(p, "invoice_tab")
            p = p.parent() if callable(getattr(p, "parent", None)) else None
            safety += 1
        return None

    def _edit_invoice(self, record: Dict[str, Any]):
        iid = record.get('id')
        if not iid:
            QMessageBox.warning(self, "Editar", "ID de factura no disponible.")
            return

        itab = self._find_invoice_tab_in_window()
        if itab:
            handled = False
            for m in ("load_invoice", "edit_invoice", "load_invoice_by_id", "_load_invoice", "open_invoice"):
                fn = getattr(itab, m, None)
                if callable(fn):
                    try:
                        fn(iid)
                        try:
                            win = self.window()
                            sw = getattr(win, "stacked_widget", None)
                            if sw is not None:
                                for i in range(sw.count()):
                                    if sw.widget(i) is itab:
                                        sw.setCurrentIndex(i)
                                        break
                        except Exception:
                            pass
                        handled = True
                        break
                    except Exception as e:
                        logger.exception("Error calling %s on invoice_tab: %s", m, e)
            if handled:
                return

        QMessageBox.information(self, "Editar", "No se pudo abrir la factura en modo edición automáticamente.\nCompruebe que exista un editor integrado (invoice_tab).")

    def _delete_invoice(self, record: Dict[str, Any]):
        iid = record.get('id')
        if not iid:
            QMessageBox.warning(self, "Eliminar", "ID de factura no disponible.")
            return
        reply = QMessageBox.question(self, "Confirmar Eliminación", f"¿Eliminar la factura {iid}? Esta acción no se puede deshacer.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        tried = []
        success = False
        try:
            iid_int = None
            try:
                iid_int = int(iid)
            except Exception:
                iid_int = iid

            for fn_name in ("delete_invoice", "remove_invoice", "delete_invoice_by_id", "deleteInvoice", "delete_factura", "remove_factura"):
                fn = getattr(self.logic, fn_name, None)
                if callable(fn):
                    try:
                        res = fn(iid_int)
                        if isinstance(res, tuple):
                            success = bool(res[0])
                        else:
                            success = bool(res)
                        tried.append(f"{fn_name}: OK" if success else f"{fn_name}: returned False")
                        if success:
                            break
                    except Exception as e:
                        tried.append(f"{fn_name}: {e}")

            if not success and hasattr(self.logic, "execute_sql"):
                try:
                    for table in ("invoices", "facturas", "invoice", "factura"):
                        try:
                            self.logic.execute_sql(f"DELETE FROM {table} WHERE id=?", (iid_int,))
                            tried.append(f"execute_sql on {table}: OK")
                            success = True
                            break
                        except Exception as e:
                            tried.append(f"execute_sql on {table}: {e}")
                except Exception as e:
                    tried.append(f"execute_sql wrapper: {e}")

            if not success:
                for fn_name in ("delete_record", "remove_record"):
                    fn = getattr(self.logic, fn_name, None)
                    if callable(fn):
                        try:
                            res = fn("invoices", iid_int)
                            if isinstance(res, tuple):
                                success = bool(res[0])
                            else:
                                success = bool(res)
                            tried.append(f"{fn_name}: OK" if success else f"{fn_name}: returned False")
                            if success:
                                break
                        except Exception as e:
                            tried.append(f"{fn_name}: {e}")

        except Exception as e:
            tried.append(str(e))

        if not success:
            logger.debug("Delete invoice attempts: %s", tried)
            QMessageBox.critical(self, "Eliminar", f"No se pudo eliminar la factura. Intentos: {tried}")
            return

        QMessageBox.information(self, "Eliminar", "Factura eliminada correctamente.")
        try:
            self.refresh()
            p = self.parent()
            safety = 0
            while p is not None and safety < 8:
                if hasattr(p, "_populate_companies"):
                    try: p._populate_companies()
                    except Exception: pass
                if hasattr(p, "invoice_tab") and hasattr(p.invoice_tab, "refresh"):
                    try: p.invoice_tab.refresh()
                    except Exception: pass
                p = p.parent() if callable(getattr(p, "parent", None)) else None
                safety += 1
        except Exception:
            pass