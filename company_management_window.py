from __future__ import annotations

from typing import Dict, Any, Optional, List, Tuple
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QLabel,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QWidget, QHeaderView, QDateEdit
)
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QFont

# Manejo de rutas de logo relativas a assets_root
from utils.asset_paths import copy_logo_to_assets, relativize_if_under_assets


class CompanyManagementWindow(QDialog):
    """
    Ventana para gestionar empresas (compacta).
    Ajustada: inputs más pequeños y sin campos de "Ruta de Plantilla" ni "Carpeta Base de Salida".
    """

    SMALL_LINEHEIGHT = 24  # altura compacta para inputs

    def __init__(self, parent, logic_controller):
        super().__init__(parent)
        self.setWindowTitle("Gestionar Empresas")
        self.resize(980, 560)
        self.logic = logic_controller
        self.selected_company_id: Optional[int] = None
        self._pending_logo_source_abs: Optional[str] = None
        self._companies_cache: List[Dict[str, Any]] = []
        self._build_ui()
        self._load_companies()

    # -------------------------
    # Normalización
    # -------------------------
    @staticmethod
    def _norm_min(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "name": row.get("name", ""),
            "rnc": row.get("rnc") or row.get("rnc_number", "") or "",
        }

    @staticmethod
    def _norm_full(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "name": row.get("name", ""),
            "rnc": row.get("rnc") or row.get("rnc_number", "") or "",
            "address_line1": row.get("address_line1") or row.get("address", "") or "",
            "address_line2": row.get("address_line2") or row.get("address", "") or "",
            "phone": row.get("phone") or row.get("telefono", "") or "",
            "email": row.get("email") or row.get("correo") or "",
            "signature_name": row.get("signature_name", "") or "",
            "logo_path": row.get("logo_path", "") or "",
            "invoice_template_path": row.get("invoice_template_path", "") or "",
            "invoice_output_base_path": row.get("invoice_output_base_path", "") or "",
            "invoice_due_date": row.get("invoice_due_date", "") or "",
            "address": row.get("address_line1") or row.get("address", "") or "",
        }

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Tabla de empresas (compacta)
        table_frame = QWidget()
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.company_table = QTableWidget(0, 4)
        self.company_table.setHorizontalHeaderLabels(["Nombre de la Empresa", "RNC", "Teléfono", "Email"])
        header = self.company_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.company_table.verticalHeader().setVisible(False)
        self.company_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.company_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.company_table.cellClicked.connect(self._on_select)
        self.company_table.setStyleSheet("QTableWidget::item { padding: 4px 6px; }")
        table_layout.addWidget(self.company_table)
        main_layout.addWidget(table_frame, stretch=2)

        # Formulario (compacto)
        form_frame = QWidget()
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(6)
        form_layout.setContentsMargins(4, 4, 4, 4)

        def compact_lineedit(placeholder: str = "") -> QLineEdit:
            le = QLineEdit()
            if placeholder:
                le.setPlaceholderText(placeholder)
            le.setMinimumHeight(self.SMALL_LINEHEIGHT)
            le.setMaximumHeight(self.SMALL_LINEHEIGHT + 2)
            return le

        # Row 1: Nombre / RNC
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nombre:"))
        self.name_edit = compact_lineedit()
        row1.addWidget(self.name_edit, stretch=3)
        row1.addWidget(QLabel("RNC:"))
        self.rnc_edit = compact_lineedit()
        row1.addWidget(self.rnc_edit, stretch=1)
        form_layout.addLayout(row1)

        # Row 2: Dirección 1 / Dirección 2
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Dirección 1:"))
        self.address1_edit = compact_lineedit()
        row2.addWidget(self.address1_edit, stretch=3)
        row2.addWidget(QLabel("Dirección 2:"))
        self.address2_edit = compact_lineedit()
        row2.addWidget(self.address2_edit, stretch=2)
        form_layout.addLayout(row2)

        # Row 3: Teléfono / Email
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Teléfono:"))
        self.phone_edit = compact_lineedit()
        row3.addWidget(self.phone_edit, stretch=1)
        row3.addWidget(QLabel("Email:"))
        self.email_edit = compact_lineedit()
        row3.addWidget(self.email_edit, stretch=2)
        form_layout.addLayout(row3)

        # Row 4: Firma autorizada
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Firma autorizada (nombre):"))
        self.signature_edit = compact_lineedit()
        row4.addWidget(self.signature_edit, stretch=3)
        form_layout.addLayout(row4)

        # Row 5: Logo (relativo) + botón elegir
        row5 = QHBoxLayout()
        row5.addWidget(QLabel("Logo (ruta relativa a assets_root):"))
        self.logo_path_edit = compact_lineedit()
        row5.addWidget(self.logo_path_edit, stretch=3)
        btn_logo = QPushButton("Elegir logo…")
        btn_logo.setMinimumHeight(self.SMALL_LINEHEIGHT + 4)
        btn_logo.clicked.connect(self._browse_logo)
        row5.addWidget(btn_logo)
        form_layout.addLayout(row5)

        # Row 6: Vencimiento fijo facturas (fecha) + limpiar
        row6 = QHBoxLayout()
        row6.addWidget(QLabel("Vencimiento fijo facturas:"))
        self.invoice_due_date_edit = QDateEdit()
        self.invoice_due_date_edit.setCalendarPopup(True)
        self.invoice_due_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.invoice_due_date_edit.setMinimumHeight(self.SMALL_LINEHEIGHT + 2)
        self.invoice_due_date_edit.setDate(QDate.currentDate())
        row6.addWidget(self.invoice_due_date_edit, stretch=1)
        btn_clear_due = QPushButton("Limpiar")
        btn_clear_due.setMinimumHeight(self.SMALL_LINEHEIGHT + 4)
        btn_clear_due.setToolTip("Deja el vencimiento vacío (N/A) para esta empresa")
        btn_clear_due.clicked.connect(lambda: self.invoice_due_date_edit.setDate(QDate.currentDate()))
        row6.addWidget(btn_clear_due)
        form_layout.addLayout(row6)

        # Note: Se eliminaron los campos "Ruta de Plantilla (Factura)" y "Carpeta Base de Salida (Facturas)"
        # para simplificar la UI según petición.

        main_layout.addWidget(form_frame, stretch=1)

        # Botones inferiores (compactos)
        btns = QHBoxLayout()
        btn_new = QPushButton("Nuevo")
        btn_new.setMinimumHeight(self.SMALL_LINEHEIGHT + 6)
        btn_new.clicked.connect(self._clear_fields)
        btns.addWidget(btn_new)

        btn_save = QPushButton("Guardar Cambios")
        btn_save.setMinimumHeight(self.SMALL_LINEHEIGHT + 6)
        btn_save.clicked.connect(self._save_company)
        btns.addWidget(btn_save)

        btn_del = QPushButton("Eliminar Empresa")
        btn_del.setMinimumHeight(self.SMALL_LINEHEIGHT + 6)
        btn_del.clicked.connect(self._delete_company)
        btns.addWidget(btn_del)

        main_layout.addLayout(btns)

        # Guardar referencias a campos para uso posterior
        self._form_frame = form_frame

    # -------------------------
    # Carga/Selección
    # -------------------------
    def _load_companies(self):
        self.company_table.setRowCount(0)

        if not hasattr(self.logic, "get_all_companies"):
            QMessageBox.critical(self, "Empresas", "logic.get_all_companies() no está implementado.")
            return

        raw = self.logic.get_all_companies() or []
        self._companies_cache = raw[:]  # mantener referencia

        enriched_rows: List[Dict[str, Any]] = []
        for c in raw:
            m = self._norm_min(c)
            phone = c.get("phone") or c.get("telefono") or ""
            email = c.get("email") or c.get("correo") or ""
            if (not phone or not email) and hasattr(self.logic, "get_company_details"):
                try:
                    det = self.logic.get_company_details(c.get("id")) or {}
                    phone = phone or det.get("phone") or det.get("telefono") or ""
                    email = email or det.get("email") or det.get("correo") or ""
                except Exception:
                    pass
            m["phone"] = phone
            m["email"] = email
            enriched_rows.append(m)

        for row, company in enumerate(enriched_rows):
            self.company_table.insertRow(row)
            self.company_table.setItem(row, 0, QTableWidgetItem(company["name"]))
            self.company_table.setItem(row, 1, QTableWidgetItem(company["rnc"]))
            self.company_table.setItem(row, 2, QTableWidgetItem(company["phone"]))
            self.company_table.setItem(row, 3, QTableWidgetItem(company["email"]))
            self.company_table.setRowHeight(row, 22)

    def _on_select(self, row, _column):
        if row < 0 or row >= len(self._companies_cache):
            return
        cid = self._companies_cache[row].get("id")
        if not cid:
            return
        self.selected_company_id = cid

        if not hasattr(self.logic, "get_company_details"):
            QMessageBox.critical(self, "Empresas", "logic.get_company_details(company_id) no está implementado.")
            return

        try:
            det_raw = self.logic.get_company_details(cid) or {}
        except Exception as e:
            QMessageBox.critical(self, "Empresas", f"No se pudo obtener detalles de la empresa:\n{e}")
            return

        det = self._norm_full(det_raw)

        self.name_edit.setText(det["name"])
        self.rnc_edit.setText(det["rnc"])
        self.address1_edit.setText(det["address_line1"])
        self.address2_edit.setText(det["address_line2"])
        self.phone_edit.setText(det["phone"])
        self.email_edit.setText(det["email"])
        self.signature_edit.setText(det["signature_name"])
        self.logo_path_edit.setText(det["logo_path"])

        # setear fecha fija de vencimiento si existe
        self._set_due_date_from_str(det.get("invoice_due_date") or "")

    def _clear_fields(self):
        self.selected_company_id = None
        self._pending_logo_source_abs = None
        self.name_edit.clear(); self.rnc_edit.clear()
        self.address1_edit.clear(); self.address2_edit.clear()
        self.phone_edit.clear(); self.email_edit.clear()
        self.signature_edit.clear(); self.logo_path_edit.clear()
        self.invoice_due_date_edit.setDate(QDate.currentDate())
        self.company_table.clearSelection()
        self.name_edit.setFocus()

    # -------------------------
    # Helpers
    # -------------------------
    def _browse_logo(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Seleccionar Logo", "", "Imágenes (*.png *.jpg *.jpeg *.svg);;Todos los archivos (*)")
        if not fn:
            return
        if self.selected_company_id:
            try:
                rel = copy_logo_to_assets(fn, int(self.selected_company_id))
                self.logo_path_edit.setText(rel)
            except Exception as e:
                QMessageBox.warning(self, "Logo", f"No se pudo copiar el logo:\n{e}")
        else:
            self._pending_logo_source_abs = fn
            # show only filename if no company selected
            self.logo_path_edit.setText(os.path.basename(fn))

    def _dateedit_to_str(self, de: QDateEdit) -> str:
        try:
            qd = de.date()
            return f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        except Exception:
            return ""

    def _set_due_date_from_str(self, s: str):
        if not s:
            self.invoice_due_date_edit.setDate(QDate.currentDate())
            return
        try:
            parts = s[:10].split("-")
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            self.invoice_due_date_edit.setDate(QDate(y, m, d))
        except Exception:
            self.invoice_due_date_edit.setDate(QDate.currentDate())

    # -------------------------
    # Guardado
    # -------------------------
    def _save_company(self):
        name = self.name_edit.text().strip()
        rnc = self.rnc_edit.text().strip()
        address1 = self.address1_edit.text().strip()
        address2 = self.address2_edit.text().strip()
        phone = self.phone_edit.text().strip()
        email = self.email_edit.text().strip()
        signature_name = self.signature_edit.text().strip()
        logo_val = self.logo_path_edit.text().strip()
        fixed_due_date = self._dateedit_to_str(self.invoice_due_date_edit)

        if not name or not rnc:
            QMessageBox.critical(self, "Error", "El Nombre y el RNC son obligatorios.")
            return

        # Obtener rutas actuales si update_company necesita template/output
        existing_template = ""
        existing_output = ""
        try:
            if hasattr(self.logic, "get_company_details") and self.selected_company_id:
                det = self.logic.get_company_details(self.selected_company_id) or {}
                existing_template = det.get("invoice_template_path", "") or ""
                existing_output = det.get("invoice_output_base_path", "") or ""
        except Exception:
            existing_template = ""
            existing_output = ""

        if self.selected_company_id:
            cid = int(self.selected_company_id)
            try:
                if hasattr(self.logic, "update_company"):
                    self.logic.update_company(cid, name, rnc, (address1 or ""), existing_template, existing_output)
                else:
                    QMessageBox.warning(self, "Aviso", "logic.update_company(...) no existe. Se omiten campos básicos.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo actualizar la empresa (básicos):\n{e}")
                return

            logo_rel = self._prepare_logo_to_save(logo_val, cid)

            extras = {
                "address_line1": address1,
                "address_line2": address2,
                "phone": phone,
                "email": email,
                "signature_name": signature_name,
                "logo_path": logo_rel,
                "address": address1,
                "invoice_due_date": fixed_due_date,
            }
            ok_extras, msg_extras = self._persist_extra_fields(cid, extras)

            self._maybe_commit()

            # Verify persisted but ignore metadata fields that some backends append
            expected_for_verify = {k: v for k, v in extras.items() if not k.startswith("updated_") and not k.startswith("created_")}
            missing = self._verify_persisted(cid, expected_for_verify)

            if missing:
                QMessageBox.warning(
                    self, "Guardado parcial",
                    "Se guardaron cambios, pero algunos campos no persistieron:\n- " + "\n- ".join(missing) +
                    ("\n\nDetalle: " + msg_extras if msg_extras else "")
                )
            else:
                QMessageBox.information(self, "Éxito", "Empresa actualizada correctamente.")
        else:
            if not hasattr(self.logic, "add_company"):
                QMessageBox.critical(self, "Error", "logic.add_company(...) no existe; no puedo crear empresas nuevas.")
                return
            try:
                new_id = int(self.logic.add_company(name, rnc, (address1 or "")))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo crear la empresa:\n{e}")
                return

            try:
                if hasattr(self.logic, "update_company"):
                    self.logic.update_company(new_id, name, rnc, (address1 or ""), "", "")
            except Exception as e:
                QMessageBox.warning(self, "Aviso", f"La empresa se creó, pero no se pudieron guardar rutas básicas:\n{e}")

            logo_rel = self._prepare_logo_to_save(logo_val, new_id)

            extras = {
                "address_line1": address1,
                "address_line2": address2,
                "phone": phone,
                "email": email,
                "signature_name": signature_name,
                "logo_path": logo_rel,
                "address": address1,
                "invoice_template_path": "",  # no editable from this UI
                "invoice_output_base_path": "",  # no editable from this UI
                "invoice_due_date": fixed_due_date,
            }
            ok_extras, msg_extras = self._persist_extra_fields(new_id, extras)
            self._maybe_commit()

            expected_for_verify = {k: v for k, v in extras.items() if not k.startswith("updated_") and not k.startswith("created_")}
            missing = self._verify_persisted(new_id, expected_for_verify)

            if missing:
                QMessageBox.warning(
                    self, "Guardado parcial",
                    "La empresa se creó, pero algunos campos no persistieron:\n- " + "\n- ".join(missing) +
                    ("\n\nDetalle: " + msg_extras if msg_extras else "")
                )
            else:
                QMessageBox.information(self, "Éxito", "Empresa creada correctamente.")
            self.selected_company_id = new_id

        sel = self.selected_company_id
        self._load_companies()
        self._reselect_by_id(sel)

        if hasattr(self.parent(), "_populate_companies"):
            try:
                self.parent()._populate_companies()
            except Exception:
                pass

    def _prepare_logo_to_save(self, current_logo_value: str, company_id: int) -> str:
        if self._pending_logo_source_abs:
            try:
                rel = copy_logo_to_assets(self._pending_logo_source_abs, int(company_id))
                self._pending_logo_source_abs = None
                return rel
            except Exception:
                pass

        if not current_logo_value:
            return ""

        val = current_logo_value
        if val.lower().startswith("file:///") or os.path.isabs(val):
            rel_try = relativize_if_under_assets(val)
            if rel_try != val:
                return rel_try
            abs_src = val[8:].replace("/", os.sep) if val.lower().startswith("file:///") else val
            try:
                return copy_logo_to_assets(abs_src, int(company_id))
            except Exception:
                return ""
        return val.replace("\\", "/")

    def _persist_extra_fields(self, company_id: int, payload_ext: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Intenta persistir campos extra con varios métodos.
        Se usa una copia local del payload para evitar que backends (p. ej. Firebase)
        muten el dict original (añadiendo updated_at/updated_by), lo que causaba
        falsos positivos en la verificación posterior.
        Retorna (ok, msg_detalle).
        """
        tried = []
        # Use a shallow copy to avoid in-place mutation by backend helpers
        payload_copy = dict(payload_ext or {})

        for method in ("update_company_fields", "update_company_dict"):
            if hasattr(self.logic, method):
                try:
                    getattr(self.logic, method)(company_id, payload_copy)
                    return True, f"{method} OK"
                except Exception as e:
                    tried.append(f"{method}: {e}")

        if hasattr(self.logic, "set_company_field"):
            any_ok = False
            errs = []
            for k, v in payload_copy.items():
                try:
                    self.logic.set_company_field(company_id, k, v)
                    any_ok = True
                except Exception as e:
                    errs.append(f"{k}: {e}")
            if any_ok:
                return True, "set_company_field parciales OK" + (f" (err: {', '.join(errs)})" if errs else "")
            tried.append("set_company_field no logró persistir ningún campo")

        return False, "No existe método para guardar campos extra (implementa update_company_fields/update_company_dict o set_company_field). Intenté: " + " | ".join(tried)

    def _maybe_commit(self):
        if hasattr(self.logic, "commit"):
            try:
                self.logic.commit()
            except Exception:
                pass

    def _verify_persisted(self, company_id: int, expected: Dict[str, Any]) -> List[str]:
        missing = []
        if not hasattr(self.logic, "get_company_details"):
            return list(expected.keys())
        try:
            det_raw = self.logic.get_company_details(company_id) or {}
        except Exception:
            return list(expected.keys())
        det = self._norm_full(det_raw)
        for k, v in expected.items():
            if k not in det:
                missing.append(k)
                continue
            dv = det.get(k, "")
            if str(dv or "").strip() != str(v or "").strip():
                missing.append(k)
        return missing

    # -------------------------
    # Eliminación
    # -------------------------
    def _delete_company(self):
        if not self.selected_company_id:
            QMessageBox.warning(self, "Sin Selección", "Selecciona una empresa para eliminar.")
            return
        confirm = QMessageBox.question(
            self, "Confirmar",
            "¿Seguro que deseas eliminar esta empresa y TODAS sus facturas?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        success, msg = (False, "No implementado")
        try:
            if hasattr(self.logic, "delete_company"):
                result = self.logic.delete_company(self.selected_company_id)
                if isinstance(result, tuple):
                    success, msg = result
                else:
                    success, msg = bool(result), ""
            else:
                msg = "logic.delete_company no existe"
        except Exception as e:
            success, msg = False, str(e)

        if success:
            QMessageBox.information(self, "Éxito", "Empresa eliminada correctamente.")
            sel = None
            self._load_companies()
            self._reselect_by_id(sel)
            if hasattr(self.parent(), "_populate_companies"):
                try: self.parent()._populate_companies()
                except Exception: pass
        else:
            QMessageBox.critical(self, "Error", str(msg))

    # -------------------------
    # Utilidades UI
    # -------------------------
    def _reselect_by_id(self, company_id: Optional[int]):
        if not company_id:
            return
        for row, c in enumerate(self._companies_cache):
            if c.get("id") == company_id:
                self.company_table.selectRow(row)
                break