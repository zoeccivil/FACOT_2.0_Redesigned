from __future__ import annotations
import os
from typing import Dict, Any, List, Any as AnyType
from datetime import datetime as dt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
    QDateEdit, QCheckBox, QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog,
    QHeaderView, QGroupBox, QGridLayout, QDialog, QInputDialog
)
from PyQt6.QtCore import QDate, Qt, pyqtSignal, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator

from constants import NCF_TYPES, ITBIS_RATE, DEFAULT_CURRENCY

from utils.quotation_templates import (
    generate_quotation_excel as generate_invoice_excel,
    generate_quotation_pdf as generate_invoice_pdf,
)

from dialogs.item_picker_dialog import ItemPickerDialog
from dialogs.template_editor_dialog import TemplateEditorDialog

from utils.template_integration import (
    export_invoice_excel_with_template,
    export_invoice_pdf_with_template,
)

try:
    from utils.template_manager import load_template, get_data_root
except Exception:
    def load_template(company_id: int):
        return {}
    def get_data_root():
        return os.getcwd()

try:
    from dialogs.invoice_preview_dialog import InvoicePreviewDialog
except Exception:
    InvoicePreviewDialog = None

from utils.asset_paths import resolve_logo_uri

try:
    from company_management_window import CompanyManagementWindow
except Exception:
    CompanyManagementWindow = None

try:
    import config_facot
except Exception:
    class _Cfg:
        QUOTATION_DUE_DAYS = 30
        INVOICE_DUE_DAYS = 30
        INVOICE_FIXED_DUE_DATE = ""
        COMPANY_LOGOS = {}
        DEFAULT_LOGO_PATH = ""
    config_facot = _Cfg()

CATEGORY_TO_PREFIX = {
    "FACTURA PRIVADA": "B01",
    "FACTURA GUBERNAMENTAL": "B15",
    "FACTURA GUBERMAMENTAL": "B15",
    "FACTURA CONSUMIDOR FINAL": "B02",
    "FACTURA EXENTA": "B14",
    "FACTURA EXENTA (REGIMEN ESPECIAL)": "B14",
    "FACTURA EXCENTA (REGIMEN ESPECIAL)": "B14",
}
DEFAULT_UNIT_FALLBACK = "UND"


class InvoiceTab(QWidget):
    """
    Pestaña de Facturas:
    - Secuencias NCF persistentes (preview vs consumo)
    - Ítems con unidad desde maestro
    - Exportación y vista previa

    Ahora soporta refrescar inmediatamente el vencimiento fijo de facturas guardado
    por NCFConfigDialog/Firebase (métodos backend: get_company_due_date / set_company_due_date
    o getters genéricos).
    """
    invoice_saved = pyqtSignal(int)

    def __init__(self, logic, get_current_company_callable, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable
        self._company_fixed_due = False  # si la empresa tiene vencimiento fijo (no recalcular al cambiar fecha)
        try:
            print(f"[LOAD] InvoiceTab module: {__file__}")
        except Exception:
            pass
        self._build_ui()

    # -------------------------
    # UI principal
    # -------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Top action row - moved to topbar in MainWindow, keep minimal controls here
        top_btn_row = QHBoxLayout()
        self.edit_template_btn = QPushButton("Editar plantilla")
        self.edit_template_btn.setProperty("flat", True)
        self.edit_template_btn.clicked.connect(self._on_edit_template)
        top_btn_row.addWidget(self.edit_template_btn)

        self.edit_company_btn = QPushButton("Editar empresa")
        self.edit_company_btn.setProperty("flat", True)
        self.edit_company_btn.clicked.connect(self._open_company_manager)
        top_btn_row.addWidget(self.edit_company_btn)

        self.btn_next_ncf = QPushButton("Siguiente NCF")
        self.btn_next_ncf.setToolTip("Asignar y consumir el siguiente NCF real")
        self.btn_next_ncf.clicked.connect(self._on_next_ncf_clicked)
        top_btn_row.addWidget(self.btn_next_ncf)

        top_btn_row.addStretch(1)
        layout.addLayout(top_btn_row)

        # COMBINED BLOCK: Datos de Factura + Datos del Cliente (compact)
        datos_cliente_box = QGroupBox("Información de la Factura")
        g = QGridLayout(datos_cliente_box)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)

        # NCF asignado (read-only for user, programmatically writable)
        self.ncf_number_edit = QLineEdit()
        self.ncf_number_edit.setClearButtonEnabled(True)
        self._setup_ncf_validator()
        self.ncf_number_edit.setReadOnly(True)
        self.ncf_number_edit.setFixedWidth(180)
        self.ncf_number_edit.setObjectName("infoField")

        # invoice category (keeps prefix mapping)
        self.invoice_kind_combo = QComboBox()
        self.invoice_kind_combo.addItems([
            "FACTURA PRIVADA",
            "FACTURA GUBERNAMENTAL",
            "FACTURA CONSUMIDOR FINAL",
            "FACTURA EXENTA",
        ])

        # dates
        self.invoice_date = QDateEdit(QDate.currentDate()); self.invoice_date.setCalendarPopup(True)
        self.invoice_due_date = QDateEdit(QDate.currentDate()); self.invoice_due_date.setCalendarPopup(True)
        self.invoice_date.setFixedWidth(120); self.invoice_date.setObjectName("infoField")
        self.invoice_due_date.setFixedWidth(120); self.invoice_due_date.setObjectName("infoField")

        # currency
        self.currency_combo = QComboBox(); self.currency_combo.addItems(["RD$", "USD", "EUR"])
        try: self.currency_combo.setCurrentText(DEFAULT_CURRENCY)
        except Exception: pass
        self.currency_combo.setFixedWidth(90); self.currency_combo.setObjectName("infoField")

        self.exchange_rate_edit = QLineEdit("1.00"); self.exchange_rate_edit.setVisible(False)
        self.exchange_rate_edit.setFixedWidth(90); self.exchange_rate_edit.setObjectName("infoField")

        # client fields & suggest combo
        self.client_rnc = QLineEdit(); self.client_rnc.setPlaceholderText("RNC/Cédula…")
        self.client_rnc.setFixedWidth(140); self.client_rnc.setObjectName("infoFieldSmall")
        self.client_name = QLineEdit(); self.client_name.setPlaceholderText("Nombre / Razón Social…")
        self.client_name.setObjectName("infoField")
        self.suggestion_combo = QComboBox(); self.suggestion_combo.hide(); self.suggestion_combo.setEditable(False)
        self.client_rnc.textChanged.connect(lambda: self._suggest_third_party('rnc'))
        self.client_name.textChanged.connect(lambda: self._suggest_third_party('name'))
        self.suggestion_combo.activated.connect(self._select_suggestion)

        # refresh preview NCF button (small)
        self.btn_refresh_ncf = QPushButton("↻"); self.btn_refresh_ncf.setToolTip("Mostrar el próximo NCF (preview)")
        self.btn_refresh_ncf.setProperty("flat", True)
        self.btn_refresh_ncf.clicked.connect(self._update_ncf_sequence)

        # Row 0: NCF | Refresh | Tipo Factura | Fecha | Vencimiento
        g.addWidget(QLabel("NCF Asignado:"), 0, 0); g.addWidget(self.ncf_number_edit, 0, 1)
        g.addWidget(self.btn_refresh_ncf, 0, 2)
        g.addWidget(QLabel("Tipo Factura:"), 0, 3); g.addWidget(self.invoice_kind_combo, 0, 4)
        g.addWidget(QLabel("Fecha:"), 0, 5); g.addWidget(self.invoice_date, 0, 6)
        g.addWidget(QLabel("Vencimiento:"), 0, 7); g.addWidget(self.invoice_due_date, 0, 8)

        # Row 1: Moneda | Tasa | RNC (small) | Nombre (large span)
        g.addWidget(QLabel("Moneda:"), 1, 0)
        g.addWidget(self.currency_combo, 1, 1)
        g.addWidget(QLabel("Tasa:"), 1, 2)
        g.addWidget(self.exchange_rate_edit, 1, 3)
        g.addWidget(QLabel("RNC/Cédula:"), 1, 4)
        g.addWidget(self.client_rnc, 1, 5)
        g.addWidget(QLabel("Nombre/Razón Social:"), 1, 6)
        g.addWidget(self.client_name, 1, 7, 1, 2)
        g.addWidget(self.suggestion_combo, 1, 9)

        # column stretches to allocate remaining space to 'Nombre'
        g.setColumnStretch(1, 0)
        g.setColumnStretch(3, 0)
        g.setColumnStretch(5, 0)
        g.setColumnStretch(7, 6)
        g.setColumnStretch(8, 2)
        layout.addWidget(datos_cliente_box)

        # Connections preserved
        self.invoice_kind_combo.currentIndexChanged.connect(self._update_ncf_sequence)
        self.invoice_date.dateChanged.connect(self._maybe_new_year_reset)
        self.currency_combo.currentIndexChanged.connect(self._on_currency_change)

        # 2. Detalles de la Factura (tabla) — includes Totals inline
        detalles_box = QGroupBox("Ítems de la Factura")
        detalles_layout = QVBoxLayout(detalles_box)

        actions = QHBoxLayout()
        btn_add_items = QPushButton("Agregar ítems…"); btn_add_items.clicked.connect(self._open_item_picker)
        btn_remove_item = QPushButton("Eliminar detalle seleccionado"); btn_remove_item.clicked.connect(self._remove_invoice_item_row)
        actions.addWidget(btn_add_items); actions.addWidget(btn_remove_item); actions.addStretch(1)
        detalles_layout.addLayout(actions)

        # Items table
        self.invoice_items_table = QTableWidget(0, 7)
        self.invoice_items_table.setHorizontalHeaderLabels(["#", "Código", "Descripción", "Unidad", "Cantidad", "Precio Unitario", "Subtotal"])
        self.invoice_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.invoice_items_table.verticalHeader().setVisible(False)
        self.invoice_items_table.setAlternatingRowColors(True)
        detalles_layout.addWidget(self.invoice_items_table)

        # Totals section - sticky style
        totals_widget = QWidget()
        totals_widget.setObjectName("totalsSection")
        totals_widget.setProperty("totalsSection", True)
        totals_row = QHBoxLayout(totals_widget)
        totals_row.setContentsMargins(16, 12, 16, 12)
        totals_row.addStretch(1)
        
        self.apply_itbis_checkbox = QCheckBox("Aplicar ITBIS (18%)")
        self.apply_itbis_checkbox.setChecked(True)
        self.apply_itbis_checkbox.stateChanged.connect(self._recalculate_invoice_totals)
        
        self.subtotal_label = QLabel("Subtotal: RD$ 0.00")
        self.subtotal_label.setProperty("muted", True)
        
        self.itbis_label = QLabel("ITBIS: RD$ 0.00")
        self.itbis_label.setProperty("muted", True)
        
        self.total_label = QLabel("Total: RD$ 0.00")
        self.total_label.setProperty("totalAmount", True)
        from PyQt6.QtGui import QFont
        total_font = QFont()
        total_font.setPointSize(12)
        total_font.setBold(True)
        self.total_label.setFont(total_font)

        totals_row.addWidget(self.apply_itbis_checkbox)
        totals_row.addSpacing(20)
        totals_row.addWidget(self.subtotal_label)
        totals_row.addSpacing(12)
        totals_row.addWidget(self.itbis_label)
        totals_row.addSpacing(12)
        totals_row.addWidget(self.total_label)

        detalles_layout.addWidget(totals_widget)
        layout.addWidget(detalles_box)

        # Footer action buttons (kept simple)
        footer_actions = QHBoxLayout()
        footer_actions.addStretch(1)
        btn_preview_html = QPushButton("Vista Previa / PDF")
        btn_preview_html.setToolTip("Abrir vista previa HTML y exportar a PDF")
        btn_preview_html.clicked.connect(self._preview_invoice)

        btn_save_invoice = QPushButton("Guardar en Base de Datos")
        btn_save_invoice.setProperty("class", "primary")
        btn_save_invoice.clicked.connect(self._save_invoice)

        footer_actions.addWidget(btn_preview_html)
        footer_actions.addWidget(btn_save_invoice)
        layout.addLayout(footer_actions)

        # Initial population / hooks
        self._apply_default_due_date()
        self.invoice_date.dateChanged.connect(self._on_invoice_date_changed)
        self._update_ncf_sequence()

    # -------------------------
    # NCF helpers
    # -------------------------
    def _setup_ncf_validator(self):
        pattern = r"^(E[0-9]{13}|(?!E)[A-Z][0-9]{10})$"
        regex = QRegularExpression(pattern)
        self.ncf_number_edit.setValidator(QRegularExpressionValidator(regex, self.ncf_number_edit))
        try:
            self.ncf_number_edit.textEdited.connect(lambda _: self._enforce_upper(self.ncf_number_edit))
        except Exception:
            pass
        self.ncf_number_edit.setPlaceholderText("Formato: ETTSSSSSSSSSSS o LTTSSSSSSSS (E+13 / letra≠E+10)")

    def _enforce_upper(self, edit: QLineEdit):
        try:
            pos = edit.cursorPosition()
            edit.setText((edit.text() or "").upper())
            edit.setCursorPosition(pos)
        except Exception:
            pass

    def _category_prefix(self) -> str:
        cat = (self.invoice_kind_combo.currentText() or "").strip().upper()
        if cat in CATEGORY_TO_PREFIX:
            return CATEGORY_TO_PREFIX[cat]
        if isinstance(NCF_TYPES, dict):
            return next(iter(NCF_TYPES.keys()), "B01")
        return "B01"

    def _dedupe_ncf(self, ncf: str, prefix3: str) -> str:
        n = (ncf or "").upper()
        p = (prefix3 or "").upper()
        if len(n) >= 4 and len(p) == 3:
            if n[0] == n[1] and n[1:].startswith(p):
                return n[1:]
        return n

    def _update_ncf_sequence(self):
        company = self.get_current_company()
        if not company:
            self.ncf_number_edit.clear(); return
        prefix3 = self._category_prefix()
        preview = ""
        try:
            if hasattr(self.logic, "get_ncf_preview"):
                preview = self.logic.get_ncf_preview(int(company['id']), prefix3)
            elif hasattr(self.logic, "get_next_ncf"):
                preview = self.logic.get_next_ncf(int(company['id']), prefix3)
        except Exception as e:
            print(f"[NCF] Error preview: {e}")
        preview = self._dedupe_ncf(preview, prefix3)
        self.ncf_number_edit.setText(preview or "")

    def _on_next_ncf_clicked(self):
        comp = self.get_current_company()
        if not comp:
            QMessageBox.warning(self, "NCF", "Seleccione una empresa."); return
        prefix3 = self._category_prefix()
        try:
            if hasattr(self.logic, "allocate_next_ncf"):
                next_ncf = self.logic.allocate_next_ncf(int(comp['id']), prefix3)
            else:
                next_ncf = self.logic.get_next_ncf(int(comp['id']), prefix3)
            next_ncf = self._dedupe_ncf(next_ncf, prefix3)
            self.ncf_number_edit.setText(next_ncf)
        except Exception as e:
            QMessageBox.critical(self, "NCF", f"No se pudo asignar el siguiente NCF:\n{e}")

    def _maybe_new_year_reset(self):
        self._update_ncf_sequence()

    def _validate_ncf_or_warn(self) -> bool:
        ncf = (self.ncf_number_edit.text() or "").strip().upper()
        if not hasattr(self.logic, "validate_ncf"):
            return True
        if not self.logic.validate_ncf(ncf):
            QMessageBox.critical(self, "NCF", "NCF inválido. Formatos válidos: E + 13 dígitos, o letra≠E + 10 dígitos.")
            return False
        return True

    def _ensure_ncf_assigned_and_mark(self, company: Dict[str, Any]):
        if not company:
            return None
        prefix = self._category_prefix()
        current = (self.ncf_number_edit.text() or "").strip().upper()
        try:
            if hasattr(self.logic, "get_ncf_preview"):
                preview = self.logic.get_ncf_preview(int(company['id']), prefix)
            else:
                preview = self.logic.get_next_ncf(int(company['id']), prefix)
        except Exception:
            preview = ""
        try:
            if not current or (preview and current == preview):
                if hasattr(self.logic, "allocate_next_ncf"):
                    assigned = self.logic.allocate_next_ncf(int(company['id']), prefix)
                else:
                    assigned = self.logic.get_next_ncf(int(company['id']), prefix)
                assigned = self._dedupe_ncf(assigned, prefix)
                if assigned:
                    self.ncf_number_edit.setText(assigned)
                    current = assigned
        except Exception as ex:
            print("[InvoiceTab] _ensure_ncf_assigned_and_mark error:", ex)
        return current

    # -------------------------
    # Moneda / fechas
    # -------------------------
    def _on_currency_change(self):
        moneda = self.currency_combo.currentText()
        if moneda != "RD$":
            self.exchange_rate_edit.setVisible(True)
            try:
                tasa, ok = QInputDialog.getDouble(
                    self, "Tasa de cambio",
                    f"Ingrese la tasa para {moneda} → RD$: ",
                    value=self._safe_float(self.exchange_rate_edit.text(), 1.0),
                    min=0.0001, decimals=4
                )
            except Exception:
                ok = False; tasa = 1.0
            self.exchange_rate_edit.setText(f"{tasa:.4f}" if ok else "1.00")
        else:
            self.exchange_rate_edit.setText("1.00"); self.exchange_rate_edit.setVisible(False)

    def _apply_default_due_date(self):
        """
        Prioridad:
        1) Due date configured per-company (from backend via get_company_due_date / get_company_details)
        2) Global fixed date in config_facot.INVOICE_FIXED_DUE_DATE
        3) Global relative days in config_facot.INVOICE_DUE_DAYS (add to invoice_date)
        """
        company = None
        try:
            company = self.get_current_company()
        except Exception:
            company = None

        # 1) Try per-company due date
        try:
            if company and company.get("id") is not None:
                company_id = int(company.get("id"))
                due = self._fetch_company_due_date(company_id)
                if due:
                    # set and mark as fixed
                    self._set_invoice_due_date_widget(due)
                    self._company_fixed_due = True
                    return
        except Exception:
            pass

        # 2) Global fixed in config
        fixed = getattr(config_facot, "INVOICE_FIXED_DUE_DATE", "") or ""
        days = int(getattr(config_facot, "INVOICE_DUE_DAYS", 0) or 0)
        if fixed:
            try:
                y, m, d = [int(x) for x in fixed.split("-")]
                self.invoice_due_date.setDate(QDate(y, m, d))
                self._company_fixed_due = True
                return
            except Exception:
                pass

        # 3) Relative days
        if days > 0:
            base = self.invoice_date.date()
            self.invoice_due_date.setDate(base.addDays(days))
            self._company_fixed_due = False
            return

        # Default: today, not fixed
        self.invoice_due_date.setDate(QDate.currentDate())
        self._company_fixed_due = False

    def _on_invoice_date_changed(self, new_date: QDate):
        """
        Only auto-update due date when company does not have a fixed due date.
        """
        fixed = self._company_fixed_due
        if fixed:
            return
        days = int(getattr(config_facot, "INVOICE_DUE_DAYS", 0) or 0)
        fixed_global = getattr(config_facot, "INVOICE_FIXED_DUE_DATE", "") or ""
        if fixed_global:
            return
        if days > 0:
            self.invoice_due_date.setDate(new_date.addDays(days))

    # -------------------------
    # Cliente / sugerencias
    # -------------------------
    def _suggest_third_party(self, search_by):
        query = self.client_rnc.text() if search_by == "rnc" else self.client_name.text()
        if len(query) < 2:
            self.suggestion_combo.hide(); return
        results = self.logic.search_third_parties(query, search_by=search_by) if hasattr(self.logic, "search_third_parties") else []
        self.suggestion_combo.clear()
        for item in results:
            self.suggestion_combo.addItem(f"{item['rnc']} - {item['name']}")
        self.suggestion_combo.setVisible(bool(results))

    def _select_suggestion(self, idx: int):
        try:
            text = self.suggestion_combo.currentText() or ""
            if " - " in text:
                rnc, name = text.split(" - ", 1)
                self.client_rnc.setText(rnc.strip())
                self.client_name.setText(name.strip())
            else:
                if text:
                    self.client_name.setText(text.strip())
            self.suggestion_combo.hide()
        except Exception:
            self.suggestion_combo.hide()

    # -------------------------
    # Ítems
    # -------------------------
    def _open_item_picker(self):
        dlg = ItemPickerDialog(self, title="Agregar ítems a la Factura")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        items = dlg.get_selected_items()
        for it in items:
            code = it.get("code") or it.get("codigo") or it.get("item_code") or ""
            name = it.get("name") or it.get("nombre") or it.get("description") or ""
            unit = it.get("unit") or it.get("unidad") or ""
            qty = it.get("quantity") or it.get("cantidad") or 0
            price = it.get("unit_price") or it.get("precio") or 0.0
            self._append_row(code, name, unit, qty, price)
        self._recalculate_invoice_totals()

    def _append_row(self, code, name, unit, qty, price, subtotal=None):
        if subtotal is None:
            try:
                subtotal = float(qty) * float(price)
            except Exception:
                subtotal = 0.0
        row = self.invoice_items_table.rowCount()
        self.invoice_items_table.insertRow(row)
        self.invoice_items_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.invoice_items_table.setItem(row, 1, QTableWidgetItem(code or ""))
        self.invoice_items_table.setItem(row, 2, QTableWidgetItem(name or ""))
        self.invoice_items_table.setItem(row, 3, QTableWidgetItem((unit or "").strip()))
        self.invoice_items_table.setItem(row, 4, QTableWidgetItem(f"{float(qty):.2f}" if qty is not None else "0.00"))
        self.invoice_items_table.setItem(row, 5, QTableWidgetItem(f"{float(price):.2f}" if price is not None else "0.00"))
        self.invoice_items_table.setItem(row, 6, QTableWidgetItem(f"{float(subtotal):,.2f}"))
        self._recalculate_invoice_totals()

    def _remove_invoice_item_row(self):
        r = self.invoice_items_table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Sin Selección", "Selecciona un detalle para eliminar."); return
        self.invoice_items_table.removeRow(r)
        for i in range(self.invoice_items_table.rowCount()):
            self.invoice_items_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
        self._recalculate_invoice_totals()

    def _recalculate_invoice_totals(self):
        subtotal = 0.0
        for r in range(self.invoice_items_table.rowCount()):
            cell = self.invoice_items_table.item(r, 6)
            if not cell:
                continue
            txt = (cell.text() or "").replace(",", "").strip()
            try:
                subtotal += float(txt) if txt else 0.0
            except Exception:
                pass
        itbis = subtotal * ITBIS_RATE if getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked() else 0.0
        total = subtotal + itbis
        try:
            self.subtotal_label.setText(f"Subtotal: RD$ {subtotal:,.2f}")
            self.itbis_label.setText(f"ITBIS ({ITBIS_RATE*100:.0f}%): RD$ {itbis:,.2f}")
            self.total_label.setText(f"Total: RD$ {total:,.2f}")
        except Exception:
            pass

    # -------------------------
    # Vista previa / exportación
    # -------------------------
    def _collect_items_for_export(self) -> List[Dict[str, AnyType]]:
        items = []
        for r in range(self.invoice_items_table.rowCount()):
            desc_item = self.invoice_items_table.item(r, 2)
            code_item = self.invoice_items_table.item(r, 1)
            unit_item = self.invoice_items_table.item(r, 3)
            qty_item = self.invoice_items_table.item(r, 4)
            price_item = self.invoice_items_table.item(r, 5)
            try:
                qty_val = float(qty_item.text().replace(",", "")) if qty_item and qty_item.text().strip() else 0.0
            except Exception:
                qty_val = 0.0
            try:
                price_val = float(price_item.text().replace(",", "")) if price_item and price_item.text().strip() else 0.0
            except Exception:
                price_val = 0.0
            items.append({
                "code": code_item.text() if code_item else "",
                "description": desc_item.text() if desc_item else "",
                "unit": unit_item.text() if unit_item else DEFAULT_UNIT_FALLBACK,
                "quantity": qty_val,
                "unit_price": price_val
            })
        return items

    def _preview_invoice(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida")
            return

        company_data, tpl = self._get_company_payload_for_preview()
        self._ensure_ncf_assigned_and_mark(company)
        ncf_text = (self.ncf_number_edit.text() or "").strip().upper()

        items = self._collect_items_for_export()
        if not items:
            QMessageBox.warning(self, "Ítems", "Agrega al menos un ítem antes de previsualizar.")
            return

        invoice_data = {
            "company_id": company_data.get('id'),
            "number": f"INV-DRAFT-{dt.now().strftime('%y%m%d%H%M%S')}",
            "ncf": ncf_text,
            "date": self.invoice_date.date().toString("yyyy-MM-dd"),
            "due_date": self.invoice_due_date.date().toString("yyyy-MM-dd"),
            "client_name": self.client_name.text(),
            "client_rnc": self.client_rnc.text(),
            "currency": self.currency_combo.currentText(),
            "exchange_rate": self._safe_float(self.exchange_rate_edit.text(), 1.0),
            "items": items,
            "notes": "",
            "invoice_category": self.invoice_kind_combo.currentText(),
            "type": self.invoice_kind_combo.currentText(),
            "apply_itbis": getattr(self, "apply_itbis_checkbox", QCheckBox()).isChecked() if hasattr(self, "apply_itbis_checkbox") else False,
        }
        invoice_data["display_number"] = self._build_display_invoice_number(company_data, ncf_text, prefix_label="FACT", last_digits=6)

        template_path = os.path.join(get_data_root(), "templates", "quotation_template.html")

        if InvoicePreviewDialog is None:
            QMessageBox.critical(self, "Vista Previa", "InvoicePreviewDialog no está disponible.")
            return

        dlg = InvoicePreviewDialog(
            company=company_data,
            template=tpl,
            invoice=invoice_data,
            parent=self,
            template_path=template_path,
            debug=False
        )
        dlg.exec()

    def _generate_invoice_excel(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida")
            return

        items_for_export = []
        for r in range(self.invoice_items_table.rowCount()):
            desc = self.invoice_items_table.item(r, 2)
            qty = self.invoice_items_table.item(r, 4)
            price = self.invoice_items_table.item(r, 5)
            try:
                qty_val = float(qty.text().replace(",", "")) if qty and qty.text().strip() else 0.0
                price_val = float(price.text().replace(",", "")) if price and price.text().strip() else 0.0
            except Exception:
                qty_val = 0.0; price_val = 0.0
            items_for_export.append({"description": desc.text() if desc else "", "quantity": qty_val, "unit_price": price_val})

        data = {
            "company_id": int(company['id']),
            "invoice_date": self.invoice_date.date().toString("yyyy-MM-dd"),
            "invoice_number": (self.ncf_number_edit.text() or "").strip(),
            "invoice_type": "emitida",
            "invoice_category": self.invoice_kind_combo.currentText(),
            "client_name": self.client_name.text(),
            "client_rnc": self.client_rnc.text(),
            "currency": self.currency_combo.currentText(),
        }

        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Factura como Excel", "", "Excel Files (*.xlsx)")
        if fn:
            save_path = fn if fn.endswith(".xlsx") else fn + ".xlsx"
            self._ensure_ncf_assigned_and_mark(company)
            generate_invoice_excel(data, items_for_export, save_path, company.get('name', ''))

    def _generate_invoice_pdf(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida")
            return

        items_for_export = []
        for r in range(self.invoice_items_table.rowCount()):
            desc = self.invoice_items_table.item(r, 2)
            qty = self.invoice_items_table.item(r, 4)
            price = self.invoice_items_table.item(r, 5)
            try:
                qty_val = float(qty.text().replace(",", "")) if qty and qty.text().strip() else 0.0
            except Exception:
                qty_val = 0.0
            try:
                price_val = float(price.text().replace(",", "")) if price and price.text().strip() else 0.0
            except Exception:
                price_val = 0.0
            items_for_export.append({"description": desc.text() if desc else "", "quantity": qty_val, "unit_price": price_val})

        data = {
            "company_id": int(company['id']),
            "invoice_date": self.invoice_date.date().toString("yyyy-MM-dd"),
            "invoice_number": (self.ncf_number_edit.text() or "").strip(),
            "invoice_type": "emitida",
            "invoice_category": self.invoice_kind_combo.currentText(),
            "client_name": self.client_name.text(),
            "client_rnc": self.client_rnc.text(),
            "currency": self.currency_combo.currentText(),
        }

        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Factura como PDF", "", "PDF Files (*.pdf)")
        if fn:
            save_path = fn if fn.endswith(".pdf") else fn + ".pdf"
            self._ensure_ncf_assigned_and_mark(company)
            generate_invoice_pdf(data, items_for_export, save_path, company.get('name', ''))

    # -------------------------
    # Utilidades numéricas / texto
    # -------------------------
    def _safe_float(self, txt: str, default: float = 0.0) -> float:
        try:
            return float((txt or "").replace(",", "").strip())
        except Exception:
            return default

    def _safe_text_attr(self, attr_name: str) -> str:
        w = getattr(self, attr_name, None)
        try:
            if w is None:
                return ""
            if hasattr(w, "text"):
                return (w.text() or "").strip()
            if hasattr(w, "toPlainText"):
                return (w.toPlainText() or "").strip()
        except Exception:
            pass
        return ""

    # -------------------------
    # Empresa / payload para preview
    # -------------------------
    def _company_display_address(self, details: Dict[str, Any], company_fallback: Dict[str, Any]) -> str:
        a1 = (details.get("address_line1") or company_fallback.get("address_line1") or "").strip()
        a2 = (details.get("address_line2") or company_fallback.get("address_line2") or "").strip()
        addr = (details.get("address") or company_fallback.get("address") or "").strip()
        if a1 or a2:
            parts = [p for p in [a1, a2] if p]
            return " ".join(parts)
        return addr or "Dirección no especificada"

    def _resolve_company_logo(self, company_id: AnyType, details: Dict[str, Any], company_fallback: Dict[str, Any]) -> str:
        cand = (details.get("logo_path") or company_fallback.get("logo_path") or "").strip()
        if not cand:
            logos = getattr(config_facot, "COMPANY_LOGOS", {}) or {}
            key_id = str(company_id) if company_id is not None else ""
            cand = logos.get(key_id) or logos.get(details.get("name") or company_fallback.get("name") or "", "")
        if not cand:
            cand = getattr(config_facot, "DEFAULT_LOGO_PATH", "") or ""
        return resolve_logo_uri(cand) or ""

    def _get_company_payload_for_preview(self):
        company_min = self.get_current_company() or {}
        company_id = company_min.get("id")
        if not company_id:
            print("[InvoiceTab] ERROR: No se pudo obtener company_id")
        details = {}
        try:
            if hasattr(self.logic, "get_company_details"):
                details = self.logic.get_company_details(company_id) or {}
            else:
                print("[InvoiceTab] ERROR: self.logic no tiene get_company_details")
        except Exception as e:
            print(f"[InvoiceTab] ERROR en get_company_details: {e}")
            details = {}

        if not details:
            details = company_min

        a1 = (details.get("address_line1") or "").strip()
        a2 = (details.get("address_line2") or "").strip()
        addr = (details.get("address") or "").strip()
        if a1 or a2:
            address_full = f"{a1} {a2}".strip()
        else:
            address_full = addr or "Dirección no especificada"

        signature = (details.get("signature_name") or "").strip()
        logo_rel = (details.get("logo_path") or "").strip()

        payload = {
            "id": company_id,
            "name": details.get("name") or company_min.get("name", ""),
            "rnc": details.get("rnc") or details.get("rnc_number") or company_min.get("rnc", ""),
            "address_line1": a1,
            "address_line2": a2,
            "address": address_full,
            "phone": details.get("phone") or details.get("telefono") or company_min.get("phone", ""),
            "email": details.get("email") or details.get("correo") or company_min.get("email", ""),
            "signature_name": signature,
            "authorized_name": signature,
            "logo_path": logo_rel,
            "invoice_due_date": (details.get("invoice_due_date") or "").strip(),
        }

        try:
            # if company payload contains invoice_due_date it will set widget (fixed)
            self._set_invoice_due_date_widget(payload.get("invoice_due_date") or "")
            if payload.get("invoice_due_date"):
                self._company_fixed_due = True
        except Exception:
            pass

        tpl = {}
        try:
            tpl = load_template(int(company_id)) or {}
        except Exception as e:
            print(f"[InvoiceTab] ERROR al cargar template: {e}")
            tpl = {}
        return payload, tpl

    # -------------------------
    # Guardar factura
    # -------------------------
    def _build_display_invoice_number(self, company: Dict[str, Any], ncf: str, prefix_label: str = "FACT", last_digits: int = 6) -> str:
        initials = self._company_initials(company.get('name', 'COMPANY'))
        digits = ''.join(ch for ch in (ncf or "") if ch.isdigit())
        tail = digits[-last_digits:] if digits else ''
        if tail:
            return f"{prefix_label}-{initials}-{tail}"
        return f"{prefix_label}-{initials}-{ncf or ''}"

    def _company_initials(self, company_name: str, max_chars: int = 6) -> str:
        if not company_name:
            return "COMP"
        parts = [p for p in company_name.replace(',', ' ').split() if p]
        if len(parts) == 1:
            s = parts[0][:max_chars].upper()
            return ''.join([c for c in s if c.isalnum()])[:max_chars]
        initials = ''.join([p[0].upper() for p in parts[:3]])
        return initials[:max_chars]

    def _save_invoice(self):
        if not self._validate_ncf_or_warn():
            return
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida"); return

        cliente_nombre = self.client_name.text().strip()
        cliente_rnc = self.client_rnc.text().strip()
        if not cliente_nombre or not cliente_rnc:
            QMessageBox.warning(self, "Cliente", "Complete nombre y RNC del cliente."); return

        moneda = self.currency_combo.currentText()
        try:
            tasa = float(self.exchange_rate_edit.text().replace(",", "")) if self.exchange_rate_edit.text().strip() else 1.0
            if tasa <= 0: tasa = 1.0
        except Exception:
            tasa = 1.0

        items = self._collect_items_for_export()
        subtotal = 0.0
        for it in items:
            try: subtotal += (it.get('quantity', 0.0) or 0.0) * (it.get('unit_price', 0.0) or 0.0)
            except Exception: pass

        itbis = subtotal * ITBIS_RATE if getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked() else 0.0
        total = subtotal + itbis
        total_rd = total * tasa

        # Asegurar consumo si el campo está vacío o igual al preview
        self._ensure_ncf_assigned_and_mark(company)

        # Dedup antes de guardar
        raw_ncf = (self.ncf_number_edit.text() or "").strip().upper()
        prefix3 = self._category_prefix()
        invoice_number = self._dedupe_ncf(raw_ncf, prefix3)

        payload = {
            "company_id": int(company['id']),
            "invoice_type": "emitida",
            "invoice_category": self.invoice_kind_combo.currentText(),
            "invoice_date": self.invoice_date.date().toString("yyyy-MM-dd"),
            "invoice_number": invoice_number,
            "third_party_name": cliente_nombre,
            "rnc": cliente_rnc,
            "currency": moneda,
            "itbis": itbis,
            "total_amount": total,
            "exchange_rate": tasa,
            "total_amount_rd": total_rd,
            "excel_path": "",
            "pdf_path": "",
        }

        invoice_id = self.logic.add_invoice(payload, items)
        QMessageBox.information(self, "Factura", f"Factura creada (ID: {invoice_id})")
        self._clear_invoice_form()
        self.invoice_saved.emit(invoice_id)

    def _clear_invoice_form(self):
        try:
            self.invoice_date.setDate(QDate.currentDate())
            # If company has fixed due, reapply it; otherwise set today
            if self._company_fixed_due:
                # re-fetch to ensure widget shows current fixed date
                self.refresh_company_due_date()
            else:
                self.invoice_due_date.setDate(QDate.currentDate())
            self.ncf_number_edit.clear()
            self.client_rnc.clear(); self.client_name.clear()
            self.currency_combo.setCurrentText(DEFAULT_CURRENCY)
            self.exchange_rate_edit.setText("1.00"); self.exchange_rate_edit.setVisible(False)
            self.invoice_items_table.setRowCount(0)
            self.subtotal_label.setText("Subtotal: RD$ 0.00")
            self.itbis_label.setText("ITBIS: RD$ 0.00")
            self.total_label.setText("Total: RD$ 0.00")
        except Exception:
            pass

    def on_company_change(self):
        try: self.suggestion_combo.hide()
        except Exception: pass
        self._clear_invoice_form()
        self._apply_default_due_date()
        self._update_ncf_sequence()

    # -------------------------
    # Direcciones / vencimiento fijo
    # -------------------------
    def _fetch_company_due_date(self, company_id: int) -> str:
        """
        Intenta obtener invoice_due_date desde backend.
        Preferir métodos específicos de FirebaseDataAccess (get_company_due_date),
        luego LogicController helpers, luego company details.
        """
        if not company_id:
            return ""
        try:
            if hasattr(self.logic, "get_company_due_date"):
                try:
                    return (self.logic.get_company_due_date(int(company_id)) or "") or ""
                except Exception:
                    pass
            if hasattr(self.logic, "get_company_invoice_due_date"):
                try:
                    return (self.logic.get_company_invoice_due_date(int(company_id)) or "") or ""
                except Exception:
                    pass
            # fallback to get_company_details
            if hasattr(self.logic, "get_company_details"):
                try:
                    det = self.logic.get_company_details(int(company_id)) or {}
                    return det.get("invoice_due_date") or det.get("invoice_due") or det.get("due_date") or ""
                except Exception:
                    pass
        except Exception as e:
            print(f"[InvoiceTab] Error fetching company due date: {e}")
        return ""

    def refresh_company_due_date(self):
        """
        Public method to re-read the company's invoice_due_date from backend and update widget immediately.
        Call this after NCFConfigDialog saves to reflect changes immediately.
        """
        company = None
        try:
            company = self.get_current_company()
        except Exception:
            company = None
        if not company or not company.get("id"):
            return
        cid = int(company.get("id"))
        due = self._fetch_company_due_date(cid)
        if due:
            self._set_invoice_due_date_widget(due)
            self._company_fixed_due = True
        else:
            # cleared -> fall back to config/default
            self._company_fixed_due = False
            self._apply_default_due_date()

    def _set_invoice_due_date_widget(self, due_str: str) -> None:
        try:
            if not due_str:
                return
            y, m, d = [int(x) for x in due_str[:10].split("-")]
            self.invoice_due_date.setDate(QDate(y, m, d))
            print(f"[ITAB-DUE] Prefill widget invoice_due_date <- {due_str}")
        except Exception as e:
            print(f"[ITAB-DUE] error prefill widget: {e}")

    # -------------------------
    # Empresa / plantillas / gestión
    # -------------------------
    def _on_edit_template(self):
        company = None
        try: company = self.get_current_company()
        except Exception: pass
        if not company:
            QMessageBox.warning(self, "Plantilla", "Seleccione primero una empresa válida.")
            return
        company_id = (company.get("id") or company.get("company_id") or company.get("pk"))
        if not company_id:
            QMessageBox.warning(self, "Plantilla", "Empresa sin identificador."); return
        if TemplateEditorDialog is None:
            QMessageBox.critical(self, "Plantilla", "TemplateEditorDialog no disponible."); return
        try:
            dlg = TemplateEditorDialog(company_id=company_id, parent=self)
            if dlg.exec():
                QMessageBox.information(self, "Plantilla", "Plantilla guardada correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Plantilla", f"No se pudo abrir el editor:\n{e}")

    def _open_company_manager(self):
        if CompanyManagementWindow is None:
            QMessageBox.warning(self, "Empresas", "No se encontró CompanyManagementWindow."); return
        try:
            dlg = CompanyManagementWindow(parent=self, logic_controller=self.logic)
            dlg.exec()
        except TypeError:
            try:
                dlg = CompanyManagementWindow(self, self.logic); dlg.exec()
            except Exception as e:
                QMessageBox.critical(self, "Empresas", f"No se pudo abrir gestión de empresas:\n{e}")
                return
        except Exception as e:
            QMessageBox.critical(self, "Empresas", f"No se pudo abrir gestión de empresas:\n{e}")
            return
        self._notify_companies_changed()
        try: self.on_company_change()
        except Exception: self._update_ncf_sequence()

    def _notify_companies_changed(self):
        p = self.parent(); safety = 0
        while p is not None and safety < 12:
            if hasattr(p, "_populate_companies"):
                try: p._populate_companies()
                except Exception: pass
                break
            p = p.parent(); safety += 1

    # -------------------------
    # Public API: Load invoice for editing
    # -------------------------
    def load_invoice_by_id(self, invoice_id: int) -> bool:
        """
        Load an invoice by ID for editing. Fetches header + items from backend
        and populates all form fields.
        
        Args:
            invoice_id: The ID of the invoice to load
            
        Returns:
            True if successfully loaded, False otherwise
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not invoice_id:
            logger.warning("[InvoiceTab] load_invoice_by_id called with no ID")
            return False
        
        try:
            # Try to fetch the invoice header
            invoice_data = None
            for method_name in ("get_invoice_by_id", "get_factura_by_id", "get_invoice"):
                fn = getattr(self.logic, method_name, None)
                if callable(fn):
                    try:
                        invoice_data = fn(int(invoice_id))
                        if invoice_data:
                            logger.info(f"[InvoiceTab] Loaded invoice via {method_name}")
                            break
                    except Exception as e:
                        logger.debug(f"[InvoiceTab] {method_name} failed: {e}")
            
            # Fallback: query directly if using SQLite
            if not invoice_data and hasattr(self.logic, "conn") and self.logic.conn:
                try:
                    cur = self.logic.conn.cursor()
                    cur.execute("SELECT * FROM invoices WHERE id = ?", (int(invoice_id),))
                    row = cur.fetchone()
                    if row:
                        invoice_data = dict(row)
                        logger.info("[InvoiceTab] Loaded invoice via direct SQL query")
                except Exception as e:
                    logger.debug(f"[InvoiceTab] Direct SQL query failed: {e}")
            
            if not invoice_data:
                logger.warning(f"[InvoiceTab] Invoice {invoice_id} not found")
                return False
            
            # Fetch items
            items = []
            for method_name in ("get_invoice_items", "get_factura_items"):
                fn = getattr(self.logic, method_name, None)
                if callable(fn):
                    try:
                        items = fn(int(invoice_id)) or []
                        if items:
                            logger.info(f"[InvoiceTab] Loaded {len(items)} items via {method_name}")
                            break
                    except Exception as e:
                        logger.debug(f"[InvoiceTab] {method_name} failed: {e}")
            
            # Fallback: query items directly
            if not items and hasattr(self.logic, "conn") and self.logic.conn:
                try:
                    cur = self.logic.conn.cursor()
                    cur.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (int(invoice_id),))
                    rows = cur.fetchall()
                    items = [dict(r) for r in rows]
                    logger.info(f"[InvoiceTab] Loaded {len(items)} items via direct SQL query")
                except Exception as e:
                    logger.debug(f"[InvoiceTab] Direct items SQL query failed: {e}")
            
            # Populate form fields
            self._populate_invoice_form(invoice_data, items)
            
            # Store the current invoice ID for updates
            self._editing_invoice_id = int(invoice_id)
            
            logger.info(f"[InvoiceTab] Successfully loaded invoice {invoice_id} for editing")
            return True
            
        except Exception as e:
            logger.exception(f"[InvoiceTab] Error loading invoice {invoice_id}: {e}")
            return False

    def _populate_invoice_form(self, invoice_data: Dict[str, Any], items: List[Dict[str, Any]]):
        """
        Populate the invoice form fields with data from an existing invoice.
        """
        from PyQt6.QtCore import QDate
        
        # Clear existing items
        self.invoice_items_table.setRowCount(0)
        
        # Populate client fields
        client_name = invoice_data.get("third_party_name") or invoice_data.get("client_name") or ""
        client_rnc = invoice_data.get("rnc") or invoice_data.get("client_rnc") or ""
        self.client_name.setText(client_name)
        self.client_rnc.setText(client_rnc)
        
        # Populate NCF
        ncf = invoice_data.get("invoice_number") or invoice_data.get("ncf") or ""
        self.ncf_number_edit.setText(ncf)
        # Make it editable for editing mode
        self.ncf_number_edit.setReadOnly(False)
        
        # Populate dates
        invoice_date_str = invoice_data.get("invoice_date") or invoice_data.get("date") or ""
        if invoice_date_str:
            try:
                parts = invoice_date_str[:10].split("-")
                if len(parts) == 3:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    self.invoice_date.setDate(QDate(y, m, d))
            except Exception:
                pass
        
        due_date_str = invoice_data.get("due_date") or ""
        if due_date_str:
            try:
                parts = due_date_str[:10].split("-")
                if len(parts) == 3:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    self.invoice_due_date.setDate(QDate(y, m, d))
                    self._company_fixed_due = True
            except Exception:
                pass
        
        # Populate currency
        currency = invoice_data.get("currency") or "RD$"
        idx = self.currency_combo.findText(currency)
        if idx >= 0:
            self.currency_combo.setCurrentIndex(idx)
        
        # Populate exchange rate
        exchange_rate = invoice_data.get("exchange_rate") or 1.0
        self.exchange_rate_edit.setText(f"{float(exchange_rate):.4f}")
        if currency != "RD$":
            self.exchange_rate_edit.setVisible(True)
        
        # Populate invoice category
        category = invoice_data.get("invoice_category") or "FACTURA PRIVADA"
        idx = self.invoice_kind_combo.findText(category)
        if idx >= 0:
            self.invoice_kind_combo.setCurrentIndex(idx)
        
        # Populate ITBIS checkbox
        itbis = float(invoice_data.get("itbis") or 0)
        if hasattr(self, "apply_itbis_checkbox"):
            self.apply_itbis_checkbox.setChecked(itbis > 0.01)
        
        # Populate items
        for item in items:
            code = item.get("code") or item.get("item_code") or item.get("codigo") or ""
            desc = item.get("description") or item.get("descripcion") or ""
            unit = item.get("unit") or item.get("unidad") or ""
            qty = float(item.get("quantity") or item.get("cantidad") or 0)
            price = float(item.get("unit_price") or item.get("precio") or 0)
            subtotal = qty * price
            self._append_row(code, desc, unit, qty, price, subtotal)
        
        # Recalculate totals
        self._recalculate_invoice_totals()

    def refresh(self):
        """
        Refresh the invoice tab state (e.g., due dates, sequences, caches).
        Called after external changes to ensure UI is up-to-date.
        """
        try:
            self._apply_default_due_date()
            self._update_ncf_sequence()
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"[InvoiceTab] refresh error: {e}")