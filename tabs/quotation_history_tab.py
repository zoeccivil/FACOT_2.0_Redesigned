from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QWidget as QWidgetAlias, QFileDialog, QMessageBox, QHeaderView, QSizePolicy,
    QMenu
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


class QuotationHistoryTab(QWidget):
    def __init__(self, logic, get_current_company_callable, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable
        self._build_ui()
        try:
            self.refresh()
        except Exception as e:
            logger.exception("Error al refrescar QuotationHistoryTab en init: %s", e)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title_label = QLabel("Historial de Cotizaciones")
        title_label.setProperty("heading", True)
        layout.addWidget(title_label)

        from PyQt6.QtWidgets import QDateEdit, QLineEdit
        from PyQt6.QtCore import QDate

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

        # Table with actions column
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["ID", "Fecha", "Cliente", "RNC", "Moneda", "Total", "Notas", "Estado", "Acciones"])
        header = self.table.horizontalHeader()
        for i in range(self.table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        actions_col = self.table.columnCount() - 1
        header.setSectionResizeMode(actions_col, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(actions_col, 320)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        
        # Enable sorting
        self.table.setSortingEnabled(True)
        
        # Enable context menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        # Enable double-click for preview
        self.table.doubleClicked.connect(self._on_table_double_click)
        
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

    def refresh(self):
        company = self.get_current_company()
        if not company:
            return
        try:
            cotizaciones = self.logic.get_quotations(company['id']) if hasattr(self.logic, "get_quotations") else []
        except Exception as e:
            logger.exception("Error al obtener cotizaciones: %s", e)
            cotizaciones = []

        # Apply client filter / date range client-side
        filtered = []
        client_q = (self.filter_client.text() or "").strip().lower()
        from_date = self.filter_date_from.date().toString("yyyy-MM-dd")
        to_date = self.filter_date_to.date().toString("yyyy-MM-dd")
        for q in (cotizaciones or []):
            date_ok = True
            q_date = q.get('quotation_date') or q.get('date') or ""
            if q_date:
                try:
                    date_ok = (q_date >= from_date and q_date <= to_date)
                except Exception:
                    date_ok = True
            client_ok = True
            if client_q:
                client_ok = client_q in (q.get('client_name') or "").lower()
            if date_ok and client_ok:
                filtered.append(q)

        self.table.setRowCount(0)
        for q in filtered:
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
            self.table.setItem(row, 7, QTableWidgetItem(q.get('status', '') or ""))
            try:
                self._add_quotation_action_buttons(row, q)
            except Exception:
                logger.exception("Error añadiendo boton de acciones para cotizacion id=%s", q.get('id'))

    def _add_quotation_action_buttons(self, row: int, record: Dict[str, Any]):
        widget = QWidgetAlias()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # PREVIEW
        btn_preview = QPushButton()
        btn_preview.setObjectName("actionButton")
        btn_preview.setToolTip("Ver detalle / Vista previa")
        btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_preview.setFixedSize(32, 32)
        icon_path = os.path.join(os.getcwd(), "assets", "icons", "eye.svg")
        if os.path.exists(icon_path):
            from PyQt6.QtGui import QIcon
            btn_preview.setIcon(QIcon(icon_path)); btn_preview.setIconSize(QSize(20, 20))
        else:
            btn_preview.setText("👁")
        btn_preview.clicked.connect(lambda _, rec=record: self._open_quotation_preview(rec))
        layout.addWidget(btn_preview)

        # EDIT
        btn_edit = QPushButton()
        btn_edit.setObjectName("actionButton")
        btn_edit.setToolTip("Editar cotización")
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setFixedSize(32, 32)
        edit_icon = os.path.join(os.getcwd(), "assets", "icons", "edit.svg")
        if os.path.exists(edit_icon):
            from PyQt6.QtGui import QIcon
            btn_edit.setIcon(QIcon(edit_icon)); btn_edit.setIconSize(QSize(20, 20))
        else:
            btn_edit.setText("✏️")
        btn_edit.clicked.connect(lambda _, rec=record: self._edit_quotation(rec))
        layout.addWidget(btn_edit)

        # DELETE
        btn_del = QPushButton()
        btn_del.setObjectName("actionButton")
        btn_del.setToolTip("Eliminar cotización")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setFixedSize(32, 32)
        del_icon = os.path.join(os.getcwd(), "assets", "icons", "trash.svg")
        if os.path.exists(del_icon):
            from PyQt6.QtGui import QIcon
            btn_del.setIcon(QIcon(del_icon)); btn_del.setIconSize(QSize(20, 20))
        else:
            btn_del.setText("🗑")
        btn_del.clicked.connect(lambda _, rec=record: self._delete_quotation(rec))
        layout.addWidget(btn_del)

        # EXPORT PDF
        btn_pdf = QPushButton()
        btn_pdf.setObjectName("actionButton")
        btn_pdf.setToolTip("Exportar cotización a PDF")
        btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pdf.setFixedSize(32, 32)
        pdf_icon = os.path.join(os.getcwd(), "assets", "icons", "pdf.svg")
        if os.path.exists(pdf_icon):
            from PyQt6.QtGui import QIcon
            btn_pdf.setIcon(QIcon(pdf_icon)); btn_pdf.setIconSize(QSize(20, 20))
        else:
            btn_pdf.setText("PDF")
        btn_pdf.clicked.connect(lambda _, rec=record: self._export_quotation_pdf(rec))
        layout.addWidget(btn_pdf)

        # EXPORT XLSX
        btn_xls = QPushButton()
        btn_xls.setObjectName("actionButton")
        btn_xls.setToolTip("Exportar cotización a Excel")
        btn_xls.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_xls.setFixedSize(32, 32)
        xls_icon = os.path.join(os.getcwd(), "assets", "icons", "xls.svg")
        if os.path.exists(xls_icon):
            from PyQt6.QtGui import QIcon
            btn_xls.setIcon(QIcon(xls_icon)); btn_xls.setIconSize(QSize(20, 20))
        else:
            btn_xls.setText("XLS")
        btn_xls.clicked.connect(lambda _, rec=record: self._export_quotation_excel(rec))
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
        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                total = float(record.get("total_amount", 0) or 0)
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = False

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

    # ---------------------------
    # Helpers to find quotation_tab in window
    # ---------------------------
    def _find_quotation_tab_in_window(self):
        try:
            win = self.window()
            if win is None:
                return None
            if hasattr(win, "quotation_tab"):
                return getattr(win, "quotation_tab")
            # try common alternative names
            for attr in ("quotation_tab", "tab_quotation", "main_quotation_tab"):
                if hasattr(win, attr):
                    return getattr(win, attr)
        except Exception:
            pass
        # fallback climb parents
        p = self.parent()
        safety = 0
        while p is not None and safety < 12:
            if hasattr(p, "quotation_tab"):
                return getattr(p, "quotation_tab")
            p = p.parent() if callable(getattr(p, "parent", None)) else None
            safety += 1
        return None

    def _edit_quotation(self, record: Dict[str, Any]):
        qid = record.get('id')
        if not qid:
            QMessageBox.warning(self, "Editar", "ID de cotización no disponible.")
            return

        qtab = self._find_quotation_tab_in_window()
        if qtab:
            handled = False
            for m in ("load_quotation", "edit_quotation", "load_quotation_by_id", "_load_quotation", "open_quotation"):
                fn = getattr(qtab, m, None)
                if callable(fn):
                    try:
                        fn(qid)
                        # bring to front
                        try:
                            win = self.window()
                            sw = getattr(win, "stacked_widget", None)
                            if sw is not None:
                                for i in range(sw.count()):
                                    if sw.widget(i) is qtab:
                                        sw.setCurrentIndex(i)
                                        break
                        except Exception:
                            pass
                        handled = True
                        break
                    except Exception as e:
                        logger.exception("Error calling %s on quotation_tab: %s", m, e)
            if handled:
                return

        QMessageBox.information(self, "Editar", "No se pudo abrir la cotización en modo edición automáticamente.\nCompruebe que exista un editor integrado (quotation_tab).")

    def _delete_quotation(self, record: Dict[str, Any]):
        qid = record.get('id')
        if not qid:
            QMessageBox.warning(self, "Eliminar", "ID de cotización no disponible.")
            return
        reply = QMessageBox.question(self, "Confirmar Eliminación", f"¿Eliminar la cotización {qid}? Esta acción no se puede deshacer.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        tried = []
        success = False
        try:
            # try many backend method names
            for fn_name in ("delete_quotation", "remove_quotation", "delete_quotation_by_id", "deleteQuotation", "delete_quote", "delete_cotizacion", "remove_quote"):
                fn = getattr(self.logic, fn_name, None)
                if callable(fn):
                    try:
                        res = fn(qid)
                        if isinstance(res, tuple):
                            success = bool(res[0])
                        else:
                            success = bool(res)
                        tried.append(f"{fn_name}: OK" if success else f"{fn_name}: returned False")
                        if success:
                            break
                    except Exception as e:
                        tried.append(f"{fn_name}: {e}")

            # try generic execute_sql if available
            if not success and hasattr(self.logic, "execute_sql"):
                try:
                    self.logic.execute_sql("DELETE FROM quotations WHERE id=?", (int(qid),))
                    success = True
                    tried.append("execute_sql quotations: OK")
                except Exception as e:
                    tried.append(f"execute_sql quotations: {e}")

            # try data-access style deletion (Firestore)
            if not success and hasattr(self.logic, "get_firestore") or hasattr(self.logic, "db") or hasattr(self.logic, "client"):
                # if backend exposes a 'delete_document' or 'delete' method
                for fn_name in ("delete_document", "delete_doc", "delete"):
                    fn = getattr(self.logic, fn_name, None)
                    if callable(fn):
                        try:
                            res = fn("quotations", str(qid))
                            success = bool(res)
                            tried.append(f"{fn_name}: {res}")
                            if success:
                                break
                        except Exception as e:
                            tried.append(f"{fn_name}: {e}")

        except Exception as e:
            tried.append(str(e))

        if not success:
            logger.debug("Delete quotation attempts: %s", tried)
            QMessageBox.critical(self, "Eliminar", f"No se pudo eliminar la cotización. Intentos: {tried}")
            return

        QMessageBox.information(self, "Eliminar", "Cotización eliminada correctamente.")
        try:
            self.refresh()
            # notify ancestor to refresh
            p = self.parent()
            safety = 0
            while p is not None and safety < 8:
                if hasattr(p, "_populate_companies"):
                    try: p._populate_companies()
                    except Exception: pass
                if hasattr(p, "quotation_tab") and hasattr(p.quotation_tab, "refresh"):
                    try: p.quotation_tab.refresh()
                    except Exception: pass
                p = p.parent() if callable(getattr(p, "parent", None)) else None
                safety += 1
        except Exception:
            pass

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

    def _show_context_menu(self, position):
        """Show context menu with quick actions."""
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        
        # Get the quotation record for this row
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        
        record = self._get_record_by_row(row)
        if not record:
            return
        
        menu = QMenu(self)
        
        # Preview action
        preview_action = menu.addAction("👁 Vista Previa")
        preview_action.triggered.connect(lambda: self._open_quotation_preview(record))
        
        # Edit action
        edit_action = menu.addAction("✏️ Editar")
        edit_action.triggered.connect(lambda: self._edit_quotation(record))
        
        menu.addSeparator()
        
        # Export PDF action
        pdf_action = menu.addAction("📄 Exportar PDF")
        pdf_action.triggered.connect(lambda: self._export_quotation_pdf(record))
        
        # Export Excel action
        excel_action = menu.addAction("📊 Exportar Excel")
        excel_action.triggered.connect(lambda: self._export_quotation_excel(record))
        
        menu.addSeparator()
        
        # Delete action
        delete_action = menu.addAction("🗑 Eliminar")
        delete_action.triggered.connect(lambda: self._delete_quotation(record))
        
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _on_table_double_click(self, index):
        """Handle double-click on table row to open preview."""
        row = index.row()
        record = self._get_record_by_row(row)
        if record:
            self._open_quotation_preview(record)

    def _get_record_by_row(self, row: int) -> Dict[str, Any]:
        """Reconstruct record dict from table row data."""
        if row < 0 or row >= self.table.rowCount():
            return {}
        
        try:
            record = {
                'id': self.table.item(row, 0).text() if self.table.item(row, 0) else '',
                'quotation_date': self.table.item(row, 1).text() if self.table.item(row, 1) else '',
                'client_name': self.table.item(row, 2).text() if self.table.item(row, 2) else '',
                'client_rnc': self.table.item(row, 3).text() if self.table.item(row, 3) else '',
                'currency': self.table.item(row, 4).text() if self.table.item(row, 4) else '',
                'total_amount': self.table.item(row, 5).text().replace(',', '') if self.table.item(row, 5) else '0',
                'notes': self.table.item(row, 6).text() if self.table.item(row, 6) else '',
                'status': self.table.item(row, 7).text() if self.table.item(row, 7) else '',
            }
            # Try to convert ID and total_amount to proper types
            try:
                record['id'] = int(record['id'])
            except (ValueError, TypeError):
                pass
            try:
                record['total_amount'] = float(record['total_amount'])
            except (ValueError, TypeError):
                record['total_amount'] = 0.0
            return record
        except Exception:
            return {}