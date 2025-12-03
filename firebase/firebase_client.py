"""
FirebaseClient - Cliente unificado para Firebase (Firestore, Storage, Auth).

Proporciona inicialización y acceso a servicios de Firebase para FACOT.

Uso:
    client = FirebaseClient()
    db = client.get_firestore()
    storage = client.get_storage()
    auth = client.get_auth()

Para inicialización con diálogo si faltan credenciales:
    from firebase.firebase_client import ensure_initialized
    ensure_initialized(parent_widget)
"""

from __future__ import annotations
import os
import json
from typing import Optional, Dict, Any, Tuple

# Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, firestore, storage, auth
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("[FIREBASE] Firebase Admin SDK no disponible. Instalar con: pip install firebase-admin")


class FirebaseClient:
    """
    Cliente singleton para servicios de Firebase.
    
    Inicializa Firebase Admin SDK y proporciona acceso a:
    - Firestore (base de datos)
    - Storage (archivos/logos)
    - Auth (autenticación)
    
    Configuración vía variables de entorno o archivo de credenciales.
    """
    
    _instance: Optional[FirebaseClient] = None
    _initialized: bool = False
    _credentials_path: Optional[str] = None
    _storage_bucket: Optional[str] = None
    
    def __new__(cls):
        """Singleton pattern - una sola instancia del cliente."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Inicializa Firebase si no está ya inicializado."""
        if not self._initialized and FIREBASE_AVAILABLE:
            self._initialize_firebase()
            FirebaseClient._initialized = True
    
    def _initialize_firebase(self, cred_path: Optional[str] = None, storage_bucket: Optional[str] = None) -> bool:
        """
        Inicializa Firebase Admin SDK.
        
        Args:
            cred_path: Ruta explícita a las credenciales (opcional)
            storage_bucket: Nombre del bucket de storage (opcional)
        
        Busca credenciales en este orden:
        1. Parámetro cred_path si se proporciona
        2. Configuración guardada en facot_config
        3. Variable de entorno FIREBASE_CREDENTIALS o FIREBASE_CREDENTIALS_PATH
        4. Variable de entorno GOOGLE_APPLICATION_CREDENTIALS
        5. Archivo firebase-credentials.json en directorio actual
        6. Archivo firebase-credentials.json en APPDATA/FACOT
        
        Returns:
            True si la inicialización fue exitosa, False en caso contrario
        """
        # Si ya está inicializado, no hacer nada
        try:
            firebase_admin.get_app()
            print("[FIREBASE] Ya inicializado")
            return True
        except ValueError:
            pass
        
        # Buscar archivo de credenciales
        final_cred_path = cred_path or self._find_credentials_file()
        
        if not final_cred_path:
            print("[FIREBASE] ⚠️ No se encontró archivo de credenciales Firebase")
            print("[FIREBASE] Configurar FIREBASE_CREDENTIALS o colocar firebase-credentials.json")
            return False
        
        try:
            # Inicializar con credenciales
            cred = credentials.Certificate(final_cred_path)
            
            # Obtener configuración de storage bucket
            final_storage_bucket = storage_bucket or self._get_storage_bucket(final_cred_path)
            
            firebase_admin.initialize_app(cred, {
                'storageBucket': final_storage_bucket
            })
            
            # Guardar valores usados
            FirebaseClient._credentials_path = final_cred_path
            FirebaseClient._storage_bucket = final_storage_bucket
            
            print(f"[FIREBASE] ✓ Inicializado correctamente")
            print(f"[FIREBASE]   Credenciales: {final_cred_path}")
            print(f"[FIREBASE]   Storage Bucket: {final_storage_bucket}")
            
            return True
            
        except Exception as e:
            print(f"[FIREBASE] ✗ Error al inicializar: {e}")
            return False
    
    def _find_credentials_file(self) -> Optional[str]:
        """Busca el archivo de credenciales en ubicaciones comunes."""
        # 0. Configuración guardada en facot_config
        try:
            import facot_config
            if hasattr(facot_config, 'get_firebase_config'):
                cred_path, _ = facot_config.get_firebase_config()
                if cred_path and os.path.exists(cred_path):
                    return cred_path
        except Exception:
            pass
        
        # 1. Variable de entorno específica (FIREBASE_CREDENTIALS)
        env_path = os.getenv("FIREBASE_CREDENTIALS")
        if env_path and os.path.exists(env_path):
            return env_path
        
        # 2. Variable de entorno específica (FIREBASE_CREDENTIALS_PATH - legacy)
        env_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if env_path and os.path.exists(env_path):
            return env_path
        
        # 3. Variable de entorno de Google
        google_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if google_path and os.path.exists(google_path):
            return google_path
        
        # 4. Directorio actual
        local_path = os.path.join(os.getcwd(), "firebase-credentials.json")
        if os.path.exists(local_path):
            return local_path
        
        # 5. APPDATA/FACOT
        try:
            appdata = os.environ.get("APPDATA") or str(os.path.expanduser("~"))
            facot_path = os.path.join(appdata, "FACOT", "firebase-credentials.json")
            if os.path.exists(facot_path):
                return facot_path
        except Exception:
            pass
        
        return None
    
    def _normalize_storage_bucket(self, bucket: str) -> str:
        """
        Normaliza el nombre del bucket para soportar formatos antiguos y nuevos.
        
        Firebase cambió de '.appspot.com' a '.firebasestorage.app'.
        Esta función acepta ambos formatos.
        """
        if not bucket:
            return bucket
        
        # Si ya tiene el formato correcto (termina con sufijo esperado), retornar tal cual
        if bucket.endswith('.firebasestorage.app') or bucket.endswith('.appspot.com'):
            return bucket
        
        # Si solo es el project_id, agregar el sufijo nuevo por defecto
        return f"{bucket}.firebasestorage.app"
    
    def _get_storage_bucket(self, cred_path: str) -> str:
        """
        Obtiene el nombre del bucket de Storage.
        
        Prioridad:
        1. Variable de entorno FIREBASE_STORAGE_BUCKET
        2. Configuración guardada en facot_config
        3. Auto-derivar desde project_id en credenciales
        
        Nota: Soporta tanto el formato antiguo (.appspot.com) como el nuevo
        (.firebasestorage.app) para compatibilidad.
        """
        # 1. Variable de entorno
        env_bucket = os.getenv("FIREBASE_STORAGE_BUCKET")
        if env_bucket:
            return self._normalize_storage_bucket(env_bucket)
        
        # 2. Configuración guardada
        try:
            import facot_config
            if hasattr(facot_config, 'get_firebase_config'):
                _, bucket = facot_config.get_firebase_config()
                if bucket:
                    return self._normalize_storage_bucket(bucket)
        except Exception:
            pass
        
        # 3. Auto-derivar desde credenciales
        try:
            with open(cred_path, 'r') as f:
                cred_data = json.load(f)
                project_id = cred_data.get('project_id', 'facot-app')
                return f"{project_id}.firebasestorage.app"
        except Exception:
            return "facot-app.firebasestorage.app"
    
    def is_available(self) -> bool:
        """Verifica si Firebase está disponible y correctamente inicializado."""
        if not FIREBASE_AVAILABLE:
            return False
        
        try:
            firebase_admin.get_app()
            return True
        except ValueError:
            return False
    
    def get_firestore(self):
        """
        Obtiene cliente de Firestore.
        
        Returns:
            firestore.Client o None si no disponible
        """
        if not self.is_available():
            print("[FIREBASE] Firestore no disponible")
            return None
        
        try:
            return firestore.client()
        except Exception as e:
            print(f"[FIREBASE] Error al obtener Firestore: {e}")
            return None
    
    def get_storage(self):
        """
        Obtiene cliente de Storage.
        
        Returns:
            storage.bucket() o None si no disponible
        """
        if not self.is_available():
            print("[FIREBASE] Storage no disponible")
            return None
        
        try:
            return storage.bucket()
        except Exception as e:
            print(f"[FIREBASE] Error al obtener Storage: {e}")
            return None
    
    def get_auth(self):
        """
        Obtiene módulo de Auth.
        
        Returns:
            auth module o None si no disponible
        """
        if not self.is_available():
            print("[FIREBASE] Auth no disponible")
            return None
        
        return auth
    
    def get_current_user_id(self) -> Optional[str]:
        """
        Obtiene el ID del usuario actual (si está autenticado).
        
        En desktop app, esto podría venir de:
        - Token guardado localmente
        - Variable de sesión
        - Configuración
        
        Returns:
            User ID o None
        """
        # Por ahora, retornar None - se implementará con Auth real
        # TODO: Implementar gestión de sesión de usuario
        return None


# Instancia global (singleton)
_firebase_client = None


def get_firebase_client() -> FirebaseClient:
    """
    Obtiene la instancia global del FirebaseClient.
    
    Returns:
        FirebaseClient instance
    """
    global _firebase_client
    if _firebase_client is None:
        _firebase_client = FirebaseClient()
    return _firebase_client


def reinitialize_firebase(credentials_path: str, storage_bucket: str) -> bool:
    """
    Reinicializa Firebase con nuevas credenciales.
    
    Útil después de que el usuario configure las credenciales via diálogo.
    
    Args:
        credentials_path: Ruta al archivo JSON de credenciales
        storage_bucket: Nombre del bucket de storage
    
    Returns:
        True si la reinicialización fue exitosa
    """
    global _firebase_client
    
    if not FIREBASE_AVAILABLE:
        print("[FIREBASE] SDK no disponible")
        return False
    
    # Eliminar app existente si hay una
    try:
        app = firebase_admin.get_app()
        firebase_admin.delete_app(app)
        FirebaseClient._initialized = False
    except ValueError:
        pass
    
    # Reinicializar
    _firebase_client = FirebaseClient()
    return _firebase_client._initialize_firebase(credentials_path, storage_bucket)


def ensure_initialized(parent_widget=None) -> bool:
    """
    Asegura que Firebase esté inicializado.
    
    Si las credenciales no están configuradas o son inválidas,
    abre un diálogo modal para que el usuario las configure.
    
    Args:
        parent_widget: Widget padre para el diálogo (QWidget o None)
    
    Returns:
        True si Firebase está disponible y listo para usar
    """
    if not FIREBASE_AVAILABLE:
        print("[FIREBASE] SDK no instalado. Instalar con: pip install firebase-admin")
        return False
    
    client = get_firebase_client()
    
    # Si ya está disponible, retornar True
    if client.is_available():
        return True
    
    # Intentar inicializar con credenciales existentes
    if client._find_credentials_file():
        if client._initialize_firebase():
            return True
    
    # No hay credenciales válidas, abrir diálogo
    print("[FIREBASE] Credenciales no encontradas. Abriendo diálogo de configuración...")
    
    try:
        from dialogs.firebase_config_dialog import FirebaseConfigDialog
        
        dialog = FirebaseConfigDialog(parent_widget)
        result = dialog.exec()
        
        if result == 1:  # Accepted
            cred_path = dialog.get_credentials_path()
            bucket = dialog.get_storage_bucket()
            
            if cred_path and bucket:
                # Guardar configuración
                try:
                    import facot_config
                    if hasattr(facot_config, 'set_firebase_config'):
                        facot_config.set_firebase_config(cred_path, bucket)
                except Exception as e:
                    print(f"[FIREBASE] Error guardando configuración: {e}")
                
                # Reinicializar con nuevas credenciales
                return reinitialize_firebase(cred_path, bucket)
        
        print("[FIREBASE] Usuario canceló la configuración")
        return False
        
    except ImportError as e:
        print(f"[FIREBASE] Error importando diálogo de configuración: {e}")
        return False
    except Exception as e:
        print(f"[FIREBASE] Error en diálogo de configuración: {e}")
        return False
