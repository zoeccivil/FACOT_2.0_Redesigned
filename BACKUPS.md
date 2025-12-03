# Sistema de Backups en FACOT 2.0

## Introducción

FACOT 2.0 incluye un sistema automático de backups que exporta los datos de Firestore a archivos locales. Esto proporciona:

- **Respaldo local**: Copia de seguridad independiente de la nube
- **Recuperación ante desastres**: Posibilidad de restaurar datos
- **Auditoría**: Histórico de estados de datos

## Backups Automáticos

### Programación

- **Hora**: Por defecto a las 02:00 (configurable)
- **Frecuencia**: Diaria
- **Retención**: 30 días por defecto

### Inicio Automático

El scheduler de backups se inicia automáticamente con la aplicación si Firebase está disponible.

## Formato de Backups

Los backups se guardan en formato JSON en la siguiente estructura:

```
backups/
├── 2024-11-27/
│   ├── _metadata.json
│   ├── companies.json
│   ├── invoices.json
│   ├── quotations.json
│   ├── clients.json
│   ├── items.json
│   ├── third_parties.json
│   └── ncf_sequence_configs.json
├── 2024-11-26/
│   └── ...
└── 2024-11-25/
    └── ...
```

### Archivo _metadata.json

Contiene información sobre el backup:

```json
{
  "backup_date": "2024-11-27",
  "backup_time": "2024-11-27T02:00:05.123456",
  "collections": ["companies", "invoices", ...],
  "total_documents": 1523,
  "errors": []
}
```

### Estructura de Documentos

Cada archivo JSON contiene un array de documentos con un campo `_id` adicional:

```json
[
  {
    "_id": "1",
    "name": "Empresa Ejemplo",
    "rnc": "123456789",
    ...
  },
  ...
]
```

### Subcolecciones

Las facturas y cotizaciones incluyen sus ítems en un campo `_items`:

```json
{
  "_id": "12345",
  "company_id": 1,
  "invoice_number": "B0100000001",
  ...
  "_items": [
    {"description": "Producto 1", "quantity": 10, ...},
    {"description": "Producto 2", "quantity": 5, ...}
  ]
}
```

## Configuración

### Variables de Entorno

```env
# Directorio de backups
BACKUP_DIR=./backups

# Hora del backup diario (formato 24h)
BACKUP_HOUR=02:00

# Días de retención
BACKUP_RETENTION_DAYS=30
```

### Configuración en facot_config.json

```json
{
  "backups": {
    "backup_dir": "./backups",
    "backup_hour": "02:00",
    "retention_days": 30
  }
}
```

## Uso Manual

### Desde la Interfaz

1. Ir a **Configuración** (Settings)
2. En la sección "Backups y Firebase":
   - **📦 Crear backup ahora**: Ejecuta un backup inmediato
   - **📂 Abrir carpeta de backups**: Abre el directorio de backups

### Desde Código

```python
from utils.backups import create_backup, cleanup_old_backups, get_backup_stats

# Crear backup
result = create_backup()
print(f"Backup creado en: {result['backup_path']}")

# Limpiar backups antiguos
cleanup_old_backups(retention_days=30)

# Obtener estadísticas
stats = get_backup_stats()
print(f"Total backups: {stats['total_backups']}")
print(f"Tamaño total: {stats['total_size_mb']} MB")
```

## API del Sistema de Backups

### BackupRunner

```python
from utils.backups.backup_runner import BackupRunner

runner = BackupRunner(backup_dir="./backups")

# Ejecutar backup
result = runner.run_backup()

# Verificar si existe backup de hoy
exists = runner.backup_exists_for_date("2024-11-27")

# Listar todos los backups
backups = runner.list_backups()
```

### Retention (Limpieza)

```python
from utils.backups.retention import cleanup_old_backups, get_backup_stats

# Limpiar backups > 30 días
result = cleanup_old_backups(retention_days=30)

# Modo simulación (no elimina realmente)
result = cleanup_old_backups(retention_days=30, dry_run=True)

# Ver qué se eliminaría
for backup in result['deleted']:
    print(f"Se eliminaría: {backup['date']}")
```

### Scheduler

```python
from utils.backups import start_backup_scheduler, stop_backup_scheduler

# Iniciar scheduler
start_backup_scheduler()

# Detener scheduler
stop_backup_scheduler()

# Verificar estado
from utils.backups.scheduler import get_backup_scheduler
scheduler = get_backup_scheduler()
status = scheduler.get_status()
print(f"Próximo backup: {status['next_backup']}")
```

## Restauración Manual

Los backups son archivos JSON estándar que pueden ser:

1. **Importados manualmente** a Firestore usando scripts
2. **Revisados** para auditoría o análisis
3. **Cargados** a otra instancia de Firebase

### Ejemplo de Script de Restauración

```python
import json
from firebase_admin import firestore

db = firestore.client()

# Restaurar una colección
with open('backups/2024-11-27/companies.json', 'r') as f:
    companies = json.load(f)

for company in companies:
    doc_id = company.pop('_id')
    db.collection('companies').document(doc_id).set(company)
```

**⚠️ ADVERTENCIA**: La restauración sobrescribirá datos existentes. Hacer backup antes de restaurar.

## Monitoreo

### Logs

El sistema registra eventos importantes:

```
[SCHEDULER] Iniciando backup programado: 2024-11-27 02:00:00
[BACKUP] Exportados 50 documentos de invoices
[BACKUP] Exportados 30 documentos de quotations
[BACKUP] Backup completado: ./backups/2024-11-27
[RETENTION] Limpieza completada: 2 eliminados, 28 conservados
```

### Verificación de Salud

```python
stats = get_backup_stats()

# Alertar si no hay backup reciente
from datetime import datetime
if stats['newest_backup']:
    last = datetime.strptime(stats['newest_backup'], '%Y-%m-%d')
    days_ago = (datetime.now() - last).days
    if days_ago > 1:
        print(f"⚠️ Último backup hace {days_ago} días")
```

## Solución de Problemas

### "Firestore no disponible"
- Verificar configuración de Firebase
- Revisar credenciales
- Comprobar conexión a internet

### Backups vacíos
- Verificar que hay datos en Firestore
- Revisar permisos del service account

### Espacio en disco
- Monitorear uso de disco
- Ajustar `BACKUP_RETENTION_DAYS` si es necesario
- Considerar compresión manual de backups antiguos

### Scheduler no inicia
- Verificar que Firebase está inicializado
- Revisar logs de errores
- Reiniciar la aplicación
