from __future__ import annotations
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base import DataAccess
from firebase import get_firebase_client


class FirebaseDataAccess(DataAccess):
    """
    Implementación de DataAccess usando Firebase Firestore.

    Nota: Este archivo incluye métodos adicionales para persistir
    vencimiento fijo de facturas por empresa en la colección 'sequences'.
    """

    def __init__(self, user_id: Optional[str] = None):
        """
        Inicializa con cliente Firebase.

        Args:
            user_id: ID del usuario actual (para created_by/updated_by)
        """
        self.client = get_firebase_client()
        self.db = self.client.get_firestore()
        self.storage = self.client.get_storage()
        self.user_id = user_id or "system"

        if not self.db:
            raise RuntimeError("Firestore no está disponible. Verificar configuración de Firebase.")

    def _add_metadata(self, data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """Agrega metadatos de auditoría a un documento."""
        now = datetime.utcnow().isoformat()

        if not is_update:
            data['created_at'] = now
            data['created_by'] = self.user_id

        data['updated_at'] = now
        data['updated_by'] = self.user_id

        return data
    
    # ===== EMPRESAS (COMPANIES) =====

    def get_all_companies(self) -> List[Dict[str, Any]]:
        """Obtiene todas las empresas."""
        try:
            companies_ref = self.db.collection('companies')
            docs = companies_ref.stream()

            companies = []
            for doc in docs:
                company_data = doc.to_dict() or {}
                company_data['id'] = int(doc.id) if str(doc.id).isdigit() else doc.id
                companies.append(company_data)

            return companies
        except Exception as e:
            print(f"[FIREBASE] Error getting companies: {e}")
            return []

    def get_company_details(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene detalles completos de una empresa."""
        try:
            doc_ref = self.db.collection('companies').document(str(company_id))
            doc = doc_ref.get()

            if doc.exists:
                company_data = doc.to_dict() or {}
                company_data['id'] = company_id
                return company_data

            return None
        except Exception as e:
            print(f"[FIREBASE] Error getting company {company_id}: {e}")
            return None

    def add_company(self, name: str, rnc: str, address: str = "") -> int:
        """Agrega una nueva empresa. Retorna el ID."""
        try:
            # Generar ID tipo timestamp (compatible con implementacion previa)
            import time
            company_id = int(time.time() * 1000) % 1000000

            company_data = {
                'name': name,
                'rnc': rnc,
                'address': address,
            }
            company_data = self._add_metadata(company_data)

            doc_ref = self.db.collection('companies').document(str(company_id))
            doc_ref.set(company_data)

            return company_id
        except Exception as e:
            print(f"[FIREBASE] Error adding company: {e}")
            raise


    # -------------------------
    # Persistencia de vencimiento de facturas (company-level)
    # -------------------------
    def set_company_due_date(self, company_id: int, due_date: str) -> bool:
        """
        Persiste el vencimiento fijo de facturas para una empresa en Firestore.

        Strategy:
          - Guardamos en la colección 'sequences' como documento '<company_id>_meta'
            con campo 'invoice_due_date': "<YYYY-MM-DD>" o "" para vaciar.

        Args:
            company_id: ID de la empresa
            due_date: cadena 'YYYY-MM-DD' o '' para limpiar

        Returns:
            True si se guardó correctamente, False en caso contrario.
        """
        try:
            doc_id = f"{company_id}_meta"
            doc_ref = self.db.collection("sequences").document(doc_id)
            # Usar merge para no borrar otros campos
            doc_ref.set({"invoice_due_date": due_date}, merge=True)
            return True
        except Exception as e:
            print(f"[FIREBASE] Error setting company due date for {company_id}: {e}")
            return False

    def get_company_due_date(self, company_id: int) -> str:
        """
        Lee el vencimiento fijo de facturas para una empresa desde Firestore
        (colección 'sequences', doc '<company_id>_meta', campo 'invoice_due_date').

        Returns:
            Cadena con fecha 'YYYY-MM-DD' o '' si no existe.
        """
        try:
            doc_id = f"{company_id}_meta"
            doc_ref = self.db.collection("sequences").document(doc_id)
            doc = doc_ref.get()
            if not doc.exists:
                return ""
            data = doc.to_dict() or {}
            return data.get("invoice_due_date", "") or ""
        except Exception as e:
            print(f"[FIREBASE] Error getting company due date for {company_id}: {e}")
            return ""

    # -------------------------
    # Compat/Hooks: mantener compatibilidad con set_company_field/update_company_fields
    # -------------------------
    def set_company_field(self, company_id: int, key: str, value: Any) -> None:
        """
        Sobrescribir o ampliar para que, si el campo es 'invoice_due_date',
        se almacene en sequences/<company>_meta para centralizar la configuración.
        Para otros campos, intentar actualizar el documento companies/{company_id}.
        """
        try:
            if key == "invoice_due_date":
                ok = self.set_company_due_date(int(company_id), str(value or ""))
                if not ok:
                    raise RuntimeError("No se pudo persistir invoice_due_date en sequences.")
                return

            # Intentar actualizar en companies doc por defecto
            doc_ref = self.db.collection("companies").document(str(company_id))
            doc_ref.update({key: value})
        except Exception as e:
            # Re-raise para que UI maneje el error si lo desea
            print(f"[FIREBASE] set_company_field error for {company_id}.{key}: {e}")
            raise

    def update_company_fields(self, company_id: int, fields: Dict[str, Any]) -> None:
        """
        Actualiza múltiples campos de la empresa.
        Si fields contiene 'invoice_due_date', lo persistimos en sequences/*_meta.
        El resto se aplica al documento companies/{company_id}.
        """
        if not fields:
            return
        fields_copy = dict(fields)
        try:
            # Manejar invoice_due_date por separado
            if "invoice_due_date" in fields_copy:
                try:
                    self.set_company_due_date(int(company_id), str(fields_copy.pop("invoice_due_date") or ""))
                except Exception as e:
                    print(f"[FIREBASE] Error persisting invoice_due_date in set_company_fields: {e}")
                    # no stop, intentar actualizar demás campos

            if fields_copy:
                doc_ref = self.db.collection("companies").document(str(company_id))
                # agregar metadata de auditoría si lo deseas
                # fields_copy['_updated_by'] = self.user_id
                doc_ref.update(fields_copy)
        except Exception as e:
            print(f"[FIREBASE] update_company_fields error for {company_id}: {e}")
            raise
    
    # ===== ÍTEMS =====

    def get_all_items(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los ítems de Firestore.
        Returns:
            Lista de ítems con todos sus campos
        """
        try:
            items_ref = self.db.collection('items')
            docs = items_ref.stream()

            items = []
            for doc in docs:
                item_data = doc.to_dict() or {}
                item_data['id'] = int(doc.id) if str(doc.id).isdigit() else doc.id
                # Normalizar nombres comunes a los que espera la UI
                normalized = {
                    'id': item_data.get('id'),
                    'code': item_data.get('code') or item_data.get('codigo') or '',
                    'name': item_data.get('name') or item_data.get('nombre') or '',
                    'unit': item_data.get('unit') or item_data.get('unidad') or '',
                    'cost': float(item_data.get('cost') or item_data.get('costo') or 0.0),
                    'price': float(item_data.get('price') or item_data.get('precio') or 0.0),
                    'category_id': int(item_data.get('category_id')) if item_data.get('category_id') is not None else item_data.get('category_id'),
                    'description': item_data.get('description') or item_data.get('desc') or ''
                }
                items.append(normalized)

            return items
        except Exception as e:
            print(f"[FIREBASE] Error getting all items: {e}")
            return []

    def get_items_like(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Busca ítems por código o nombre (cliente-side)."""
        try:
            items = []
            for doc in self.db.collection('items').limit(200).stream():
                d = doc.to_dict() or {}
                code = str(d.get('code', '')).lower()
                name = str(d.get('name', '')).lower()
                q = query.lower()
                if q in code or q in name:
                    normalized = {
                        'id': int(doc.id) if str(doc.id).isdigit() else doc.id,
                        'code': d.get('code') or '',
                        'name': d.get('name') or '',
                        'unit': d.get('unit') or '',
                        'cost': float(d.get('cost') or 0),
                        'price': float(d.get('price') or 0),
                        'category_id': d.get('category_id'),
                        'description': d.get('description') or ''
                    }
                    items.append(normalized)
                    if len(items) >= limit:
                        break
            return items
        except Exception as e:
            print(f"[FIREBASE] Error searching items: {e}")
            return []

    def get_item_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Obtiene un ítem por código exacto."""
        try:
            items_ref = self.db.collection('items')
            query = items_ref.where('code', '==', code).limit(1)

            docs = list(query.stream())
            if docs:
                item_data = docs[0].to_dict() or {}
                item_data['id'] = int(docs[0].id) if str(docs[0].id).isdigit() else docs[0].id
                return item_data

            return None
        except Exception as e:
            print(f"[FIREBASE] Error getting item by code {code}: {e}")
            return None
    
    # ===== TERCEROS (THIRD PARTIES) =====
    
    def get_third_party_by_rnc(self, rnc: str) -> Optional[Dict[str, Any]]:
        """Obtiene un tercero por RNC."""
        try:
            parties_ref = self.db.collection('third_parties')
            query = parties_ref.where('rnc', '==', rnc).limit(1)
            
            docs = list(query.stream())
            if docs:
                party_data = docs[0].to_dict()
                party_data['id'] = docs[0].id
                return party_data
            
            return None
        except Exception as e:
            print(f"[FIREBASE] Error getting third party by RNC {rnc}: {e}")
            return None
    
    # ===== FACTURAS (INVOICES) =====
    
    def add_invoice(self, invoice_data: Dict[str, Any], items: List[Dict[str, Any]]) -> int:
        """Agrega una nueva factura con sus ítems. Retorna el ID."""
        try:
            import time
            invoice_id = int(time.time() * 1000) % 1000000
            
            # Preparar datos de factura
            invoice_doc = dict(invoice_data)
            invoice_doc = self._add_metadata(invoice_doc)
            
            # Crear documento de factura
            invoice_ref = self.db.collection('invoices').document(str(invoice_id))
            invoice_ref.set(invoice_doc)
            
            # Agregar ítems como subcolección
            items_ref = invoice_ref.collection('items')
            for idx, item in enumerate(items):
                item_doc = self._add_metadata(dict(item))
                items_ref.document(str(idx)).set(item_doc)
            
            return invoice_id
        except Exception as e:
            print(f"[FIREBASE] Error adding invoice: {e}")
            raise
    
    def get_invoices(
        self, 
        company_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Obtiene facturas (opcionalmente filtradas por empresa)."""
        try:
            invoices_ref = self.db.collection('invoices')
            
            if company_id:
                query = invoices_ref.where('company_id', '==', company_id)
            else:
                query = invoices_ref
            
            query = query.limit(limit).offset(offset)
            
            invoices = []
            for doc in query.stream():
                invoice_data = doc.to_dict()
                invoice_data['id'] = int(doc.id) if doc.id.isdigit() else doc.id
                invoices.append(invoice_data)
            
            return invoices
        except Exception as e:
            print(f"[FIREBASE] Error getting invoices: {e}")
            return []
    
    def get_invoice_by_id(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene una factura específica con sus ítems."""
        try:
            invoice_ref = self.db.collection('invoices').document(str(invoice_id))
            doc = invoice_ref.get()
            
            if not doc.exists:
                return None
            
            invoice_data = doc.to_dict()
            invoice_data['id'] = invoice_id
            
            # Obtener ítems de la subcolección
            items_ref = invoice_ref.collection('items')
            items = []
            for item_doc in items_ref.stream():
                item_data = item_doc.to_dict()
                items.append(item_data)
            
            invoice_data['items'] = items
            
            return invoice_data
        except Exception as e:
            print(f"[FIREBASE] Error getting invoice {invoice_id}: {e}")
            return None
    
    # ===== COTIZACIONES (QUOTATIONS) =====
    
    def add_quotation(self, quotation_data: Dict[str, Any], items: List[Dict[str, Any]]) -> int:
        """Agrega una nueva cotización con sus ítems. Retorna el ID."""
        try:
            import time
            quotation_id = int(time.time() * 1000) % 1000000
            
            # Preparar datos de cotización
            quotation_doc = dict(quotation_data)
            quotation_doc = self._add_metadata(quotation_doc)
            
            # Crear documento de cotización
            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            quotation_ref.set(quotation_doc)
            
            # Agregar ítems como subcolección
            items_ref = quotation_ref.collection('items')
            for idx, item in enumerate(items):
                item_doc = self._add_metadata(dict(item))
                items_ref.document(str(idx)).set(item_doc)
            
            return quotation_id
        except Exception as e:
            print(f"[FIREBASE] Error adding quotation: {e}")
            raise
    
    def get_quotations(
        self,
        company_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Obtiene cotizaciones (opcionalmente filtradas por empresa)."""
        try:
            quotations_ref = self.db.collection('quotations')
            
            if company_id:
                query = quotations_ref.where('company_id', '==', company_id)
            else:
                query = quotations_ref
            
            query = query.limit(limit).offset(offset)
            
            quotations = []
            for doc in query.stream():
                quotation_data = doc.to_dict()
                quotation_data['id'] = int(doc.id) if doc.id.isdigit() else doc.id
                quotations.append(quotation_data)
            
            return quotations
        except Exception as e:
            print(f"[FIREBASE] Error getting quotations: {e}")
            return []
    
    def get_quotation_by_id(self, quotation_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene una cotización específica con sus ítems."""
        try:
            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            doc = quotation_ref.get()
            
            if not doc.exists:
                return None
            
            quotation_data = doc.to_dict()
            quotation_data['id'] = quotation_id
            
            # Obtener ítems de la subcolección
            items_ref = quotation_ref.collection('items')
            items = []
            for item_doc in items_ref.stream():
                item_data = item_doc.to_dict()
                items.append(item_data)
            
            quotation_data['items'] = items
            
            return quotation_data
        except Exception as e:
            print(f"[FIREBASE] Error getting quotation {quotation_id}: {e}")
            return None
    
    # ===== NCF / SECUENCIAS =====
    
    def get_next_ncf(self, company_id: int, ncf_type: str) -> str:
        """Obtiene el siguiente NCF disponible para una empresa y tipo."""
        try:
            # Importar firestore ANTES de usarlo en el decorador
            from google.cloud import firestore
            
            # Usar transacción para asegurar atomicidad
            sequence_ref = self.db.collection('sequences').document(f"{company_id}_ncf_{ncf_type}")
            
            @firestore.transactional
            def increment_sequence(transaction):
                snapshot = sequence_ref.get(transaction=transaction)
                
                if snapshot.exists:
                    current = snapshot.get('current')
                else:
                    current = 0
                
                new_value = current + 1
                transaction.set(sequence_ref, {'current': new_value})
                
                return new_value
            
            transaction = self.db.transaction()
            seq_num = increment_sequence(transaction)
            
            # Formatear NCF
            return f"B{ncf_type}{seq_num:08d}"
        except Exception as e:
            print(f"[FIREBASE] Error getting next NCF: {e}")
            return f"B{ncf_type}00000001"
    
    # ===== MÉTODOS ADICIONALES PARA COMPATIBILIDAD =====
    
    def get_invoice_items(self, invoice_id: int) -> List[Dict[str, Any]]:
        """Obtiene los ítems de una factura específica."""
        try:
            invoice_ref = self.db.collection('invoices').document(str(invoice_id))
            items_ref = invoice_ref.collection('items')
            
            items = []
            for doc in items_ref.stream():
                item_data = doc.to_dict()
                item_data['id'] = doc.id
                items.append(item_data)
            
            return items
        except Exception as e:
            print(f"[FIREBASE] Error getting invoice items for {invoice_id}: {e}")
            return []
    
    def get_quotation_items(self, quotation_id: int) -> List[Dict[str, Any]]:
        """Obtiene los ítems de una cotización específica."""
        try:
            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            items_ref = quotation_ref.collection('items')
            
            items = []
            for doc in items_ref.stream():
                item_data = doc.to_dict()
                item_data['id'] = doc.id
                items.append(item_data)
            
            return items
        except Exception as e:
            print(f"[FIREBASE] Error getting quotation items for {quotation_id}: {e}")
            return []
    
    def search_third_parties(self, query: str, search_by: str = 'name') -> List[Dict[str, Any]]:
        """Busca terceros por nombre o RNC."""
        try:
            parties_ref = self.db.collection('third_parties')
            
            # Firestore no soporta LIKE, filtrar en cliente
            all_parties = []
            for doc in parties_ref.limit(100).stream():
                party_data = doc.to_dict()
                party_data['id'] = doc.id
                
                if search_by == 'name':
                    if query.lower() in str(party_data.get('name', '')).lower():
                        all_parties.append(party_data)
                elif search_by == 'rnc':
                    if query in str(party_data.get('rnc', '')):
                        all_parties.append(party_data)
                
                if len(all_parties) >= 20:
                    break
            
            return all_parties
        except Exception as e:
            print(f"[FIREBASE] Error searching third parties: {e}")
            return []
    
    def add_or_update_third_party(self, rnc: str, name: str) -> None:
        """Agrega o actualiza un tercero por RNC."""
        try:
            parties_ref = self.db.collection('third_parties')
            query = parties_ref.where('rnc', '==', rnc).limit(1)
            
            docs = list(query.stream())
            
            party_data = {
                'rnc': rnc,
                'name': name,
            }
            party_data = self._add_metadata(party_data, is_update=len(docs) > 0)
            
            if docs:
                # Actualizar existente
                docs[0].reference.update(party_data)
            else:
                # Crear nuevo
                parties_ref.add(party_data)
                
        except Exception as e:
            print(f"[FIREBASE] Error adding/updating third party: {e}")
            raise
    
    def validate_ncf(self, ncf: str) -> bool:
        """Valida formato de NCF."""
        if not ncf:
            return False
        
        # Validación básica de formato
        import re
        # NCF estándar: letra + 10 dígitos
        if re.match(r'^[A-Z][0-9]{10}$', ncf):
            return True
        # e-CF: E + 13 dígitos
        if re.match(r'^E[0-9]{13}$', ncf):
            return True
        
        return False
    
    def get_facturas(self, company_id: int, only_issued: bool = True) -> List[Dict[str, Any]]:
        """Alias de get_invoices para compatibilidad con LogicController."""
        return self.get_invoices(company_id=company_id)
    
    def delete_factura(self, factura_id: int) -> None:
        """Elimina una factura y sus ítems."""
        try:
            invoice_ref = self.db.collection('invoices').document(str(factura_id))
            
            # Eliminar ítems primero
            items_ref = invoice_ref.collection('items')
            for item_doc in items_ref.stream():
                item_doc.reference.delete()
            
            # Eliminar factura
            invoice_ref.delete()
            
        except Exception as e:
            print(f"[FIREBASE] Error deleting invoice {factura_id}: {e}")
            raise
    
    def delete_invoice(self, invoice_id: int) -> bool:
        """Alias for delete_factura for compatibility with history tabs."""
        try:
            self.delete_factura(invoice_id)
            return True
        except Exception:
            return False
    
    def delete_quotation(self, quotation_id: int) -> None:
        """Elimina una cotización y sus ítems."""
        try:
            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            
            # Eliminar ítems primero
            items_ref = quotation_ref.collection('items')
            for item_doc in items_ref.stream():
                item_doc.reference.delete()
            
            # Eliminar cotización
            quotation_ref.delete()
            
        except Exception as e:
            print(f"[FIREBASE] Error deleting quotation {quotation_id}: {e}")
            raise
    
    def update_quotation(self, quotation_id: int, quotation_data: Dict[str, Any], items: List[Dict[str, Any]]) -> None:
        """Actualiza una cotización con sus ítems."""
        try:
            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            
            # Actualizar datos de cotización
            quotation_doc = dict(quotation_data)
            quotation_doc = self._add_metadata(quotation_doc, is_update=True)
            quotation_ref.update(quotation_doc)
            
            # Eliminar ítems antiguos
            items_ref = quotation_ref.collection('items')
            for item_doc in items_ref.stream():
                item_doc.reference.delete()
            
            # Agregar nuevos ítems
            for idx, item in enumerate(items):
                item_doc = self._add_metadata(dict(item))
                items_ref.document(str(idx)).set(item_doc)
                
        except Exception as e:
            print(f"[FIREBASE] Error updating quotation {quotation_id}: {e}")
            raise
    
    # ===== UTILIDADES =====
    
    def commit(self) -> None:
        """No-op para Firestore (commits automáticos)."""
        pass
    
    def close(self) -> None:
        """No-op para Firestore (no necesita cierre explícito)."""
        pass
    
    # ===== LOGOS EN STORAGE =====
    
    def upload_logo_to_storage(self, local_path: str, template_id: str) -> Optional[str]:
        """
        Sube un logo de plantilla a Firebase Storage.
        
        Args:
            local_path: Ruta local del archivo de imagen
            template_id: ID de la plantilla
        
        Returns:
            URL pública del archivo o None si falla
        """
        if not self.storage:
            print("[FIREBASE] Storage no disponible")
            return None
        
        if not os.path.exists(local_path):
            print(f"[FIREBASE] Archivo no existe: {local_path}")
            return None
        
        try:
            import os
            
            # Determinar extensión
            _, ext = os.path.splitext(local_path)
            if not ext:
                ext = ".png"
            
            # Ruta en Storage
            storage_path = f"templates/{template_id}/logo{ext}"
            
            # Obtener blob
            blob = self.storage.blob(storage_path)
            
            # Determinar content type
            content_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp"
            }
            content_type = content_types.get(ext.lower(), "application/octet-stream")
            
            # Subir archivo
            blob.upload_from_filename(local_path, content_type=content_type)
            
            # Hacer público (opcional)
            try:
                blob.make_public()
                public_url = blob.public_url
            except Exception:
                # Si no se puede hacer público, usar URL de descarga
                public_url = blob.generate_signed_url(
                    version="v4",
                    expiration=3600 * 24 * 365,  # 1 año
                    method="GET"
                )
            
            print(f"[FIREBASE] Logo subido: {storage_path}")
            return public_url
            
        except Exception as e:
            print(f"[FIREBASE] Error subiendo logo: {e}")
            return None
    
    def download_logo(self, storage_path: str, template_id: str) -> Optional[str]:
        """
        Descarga un logo desde Storage a cache local.
        
        Args:
            storage_path: Ruta en Storage (ej: templates/{id}/logo.png)
            template_id: ID de la plantilla
        
        Returns:
            Ruta del archivo en cache local o None si falla
        """
        if not self.storage:
            print("[FIREBASE] Storage no disponible")
            return None
        
        # Constante para cache expiration (24 horas en segundos)
        CACHE_EXPIRATION_SECONDS = 24 * 60 * 60  # 86400
        
        try:
            # Crear directorio de cache si no existe
            cache_dir = os.path.join(".", "data", "cache", "logos")
            os.makedirs(cache_dir, exist_ok=True)
            
            # Determinar extensión del archivo
            _, ext = os.path.splitext(storage_path)
            if not ext:
                ext = ".png"
            
            # Ruta local de cache
            local_path = os.path.join(cache_dir, f"{template_id}{ext}")
            
            # Verificar si ya existe en cache (evitar descargas repetidas)
            if os.path.exists(local_path):
                # Verificar antigüedad (re-descargar si tiene más de 24 horas)
                import time
                if time.time() - os.path.getmtime(local_path) < CACHE_EXPIRATION_SECONDS:
                    return local_path
            
            # Descargar desde Storage
            blob = self.storage.blob(storage_path)
            
            if not blob.exists():
                print(f"[FIREBASE] Logo no existe en Storage: {storage_path}")
                return None
            
            blob.download_to_filename(local_path)
            print(f"[FIREBASE] Logo descargado: {local_path}")
            
            return local_path
            
        except Exception as e:
            print(f"[FIREBASE] Error descargando logo: {e}")
            return None
    
    def update_template_logo(self, template_id: str, local_logo_path: str) -> Dict[str, Any]:
        """
        Sube un logo y actualiza el documento de plantilla.
        
        Args:
            template_id: ID de la plantilla
            local_logo_path: Ruta local del logo
        
        Returns:
            Dict con logo_storage_path y logo_url, o vacío si falla
        """
        result = {}
        
        # Subir logo
        public_url = self.upload_logo_to_storage(local_logo_path, template_id)
        
        if public_url:
            import os
            _, ext = os.path.splitext(local_logo_path)
            storage_path = f"templates/{template_id}/logo{ext}"
            
            result = {
                "logo_storage_path": storage_path,
                "logo_url": public_url
            }
            
            # Actualizar documento de plantilla
            try:
                template_ref = self.db.collection('templates').document(str(template_id))
                template_ref.update({
                    "logo_storage_path": storage_path,
                    "logo_url": public_url,
                    "updated_at": datetime.utcnow().isoformat(),
                    "updated_by": self.user_id
                })
            except Exception as e:
                print(f"[FIREBASE] Error actualizando plantilla: {e}")
        
        return result
    
    def get_template_logo(self, template_id: str, fallback_local_path: Optional[str] = None) -> Optional[str]:
        """
        Obtiene el logo de una plantilla desde cache/Storage con fallback local.
        
        Args:
            template_id: ID de la plantilla
            fallback_local_path: Ruta local alternativa si falla la descarga
        
        Returns:
            Ruta del logo (cache, descargado o fallback) o None
        """
        try:
            # Buscar info de plantilla
            template_ref = self.db.collection('templates').document(str(template_id))
            doc = template_ref.get()
            
            if doc.exists:
                template_data = doc.to_dict()
                storage_path = template_data.get('logo_storage_path')
                
                if storage_path:
                    # Intentar descargar
                    local_path = self.download_logo(storage_path, template_id)
                    if local_path:
                        return local_path
            
            # Fallback a ruta local
            if fallback_local_path and os.path.exists(fallback_local_path):
                print(f"[FIREBASE] Usando logo local como fallback: {fallback_local_path}")
                return fallback_local_path
            
            return None
            
        except Exception as e:
            print(f"[FIREBASE] Error obteniendo logo de plantilla: {e}")
            
            # Fallback
            if fallback_local_path and os.path.exists(fallback_local_path):
                return fallback_local_path
            
            return None


    # ===== CATEGORIES =====

    def get_all_categories(self) -> List[Dict[str, Any]]:
        """
        Obtiene todas las categorías desde la colección 'categories'.
        Retorna lista de dicts con claves: id, name, code_prefix, next_seq, description (simil sql).
        """
        try:
            cols = self.db.collection('categories')
            docs = cols.stream()
            cats = []
            for doc in docs:
                d = doc.to_dict() or {}
                # normalizar campos comunes
                cat = {
                    'id': int(doc.id) if str(doc.id).isdigit() else doc.id,
                    'name': d.get('name') or d.get('nombre') or '',
                    'code_prefix': d.get('code_prefix') or d.get('prefix') or '',
                    'next_seq': int(d.get('next_seq', 1) or 1),
                    'description': d.get('description') or ''
                }
                cats.append(cat)
            # ordenar por name para consistencia con sqlite UI
            cats.sort(key=lambda x: (x.get('name') or '').lower())
            return cats
        except Exception as e:
            print(f"[FIREBASE] Error getting categories: {e}")
            return []
