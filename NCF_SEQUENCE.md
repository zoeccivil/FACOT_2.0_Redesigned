# Sistema de Secuencias NCF en FACOT 2.0

## Introducción

El NCF (Número de Comprobante Fiscal) es un número único requerido por la DGII (Dirección General de Impuestos Internos) de República Dominicana para cada factura fiscal emitida.

FACOT 2.0 implementa un sistema robusto para la generación de NCF que garantiza:
- **Unicidad**: Cada NCF es único por empresa y tipo de comprobante
- **Consistencia**: Las secuencias son consistentes incluso bajo concurrencia
- **Persistencia**: La configuración se almacena en Firestore

## Formato del NCF

### NCF Estándar
- Formato: `XYY########` (1 letra + 2 dígitos + 8 dígitos = 11 caracteres)
- Ejemplo: `B0100000163`

Donde:
- `X`: Letra que indica el tipo general (B, F, etc.)
- `YY`: Código de tipo específico (01, 02, 14, 15, etc.)
- `########`: Secuencia numérica con padding de 8 dígitos

### e-CF (Comprobante Electrónico)
- Formato: `EYY###########` (E + 2 dígitos + 11 dígitos = 14 caracteres)
- Ejemplo: `E3100000000001`

## Tipos de Comprobantes

| Prefijo | Nombre | Descripción |
|---------|--------|-------------|
| B01 | Crédito Fiscal | Factura para contribuyentes con crédito fiscal |
| B02 | Consumidor Final | Factura para consumidores finales |
| B04 | Nota de Crédito | Corrección de factura emitida |
| B14 | Régimen Especial | Factura para regímenes especiales |
| B15 | Gubernamental | Factura para entidades gubernamentales |
| B16 | Exportación | Factura para exportaciones |
| E31 | e-CF Consumidor Final | Comprobante electrónico |
| E32 | e-CF Crédito Fiscal | Comprobante electrónico |

## Colección ncf_sequence_configs

La configuración de secuencias se almacena en Firestore en la colección `ncf_sequence_configs`.

### Estructura del Documento

```json
{
  "company_id": 1,
  "category": "FACTURA PRIVADA",
  "prefix": "B01",
  "last_assigned": "B0100000163",
  "next_sequence": 164,
  "effective_from": "2024-01-01",
  "notes": "",
  "created_at": "2024-01-01T00:00:00Z",
  "created_by": "admin",
  "updated_at": "2024-11-27T12:00:00Z",
  "updated_by": "system"
}
```

### Campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `company_id` | int | ID de la empresa |
| `category` | string | Categoría descriptiva del comprobante |
| `prefix` | string | Prefijo de 3 caracteres (ej: "B01") |
| `last_assigned` | string | Último NCF asignado completamente |
| `next_sequence` | int | Siguiente número de secuencia |
| `effective_from` | string | Fecha desde la cual aplica esta secuencia |
| `notes` | string | Notas opcionales |
| `created_at` | string | Fecha de creación (ISO 8601) |
| `created_by` | string | Usuario que creó el registro |
| `updated_at` | string | Última actualización |
| `updated_by` | string | Usuario que actualizó |

## Transacciones Firestore

### Flujo de Asignación de NCF

```
1. Cliente solicita NCF para (company_id, category)
2. Derivar prefix desde category
3. Iniciar transacción Firestore
4. Leer documento de ncf_sequence_configs
5. Si existe:
   a. Verificar coherencia (last_assigned + 1 == next_sequence)
   b. Si hay inconsistencia, invocar corrector
   c. Formar NCF con next_sequence
   d. Actualizar last_assigned y next_sequence
6. Si no existe:
   a. Buscar último NCF en facturas
   b. Calcular siguiente secuencia
   c. Crear documento inicial
7. Commit transacción
8. Retornar NCF
```

### Reintentos ante Contención

Cuando múltiples procesos intentan obtener un NCF simultáneamente, Firestore puede detectar contención. El servicio implementa:

- Máximo de reintentos: `MAX_NCF_TX_RETRIES` (default: 5)
- Backoff exponencial entre reintentos
- Logging de intentos fallidos

## Corrector de Secuencias

Cuando se detecta una inconsistencia entre `last_assigned` y `next_sequence`:

1. Se busca el NCF máximo real en la colección `invoices`
2. Se calcula el siguiente número válido
3. Se actualiza la secuencia corregida
4. Se registra el ajuste en logs

## API del Servicio

### get_next_ncf

```python
from services.ncf_firestore_service import get_next_ncf

# Obtener NCF por categoría
ncf = get_next_ncf(company_id=1, category="FACTURA PRIVADA")
# Resultado: "B0100000164"

# Obtener NCF con prefix explícito
ncf = get_next_ncf(company_id=1, category="", prefix="B02")
# Resultado: "B0200000001"
```

### get_sequence_info

```python
from services.ncf_firestore_service import get_ncf_firestore_service

service = get_ncf_firestore_service()
info = service.get_sequence_info(company_id=1, prefix="B01")

# Retorna:
# {
#   'exists': True,
#   'prefix': 'B01',
#   'last_assigned': 'B0100000163',
#   'next_sequence': 164,
#   'next_ncf': 'B0100000164',
#   ...
# }
```

### set_sequence

Para correcciones manuales:

```python
service.set_sequence(
    company_id=1,
    prefix="B01",
    last_sequence=163,
    category="FACTURA PRIVADA"
)
```

## Configuración

### Variables de Entorno

```env
# Longitud del padding numérico (default: 8)
NCF_PADDING=8

# Máximo de reintentos (default: 5)
MAX_NCF_TX_RETRIES=5
```

### Mapeo de Categorías

El servicio mapea automáticamente categorías comunes a prefijos:

| Categoría | Prefix |
|-----------|--------|
| "FACTURA PRIVADA" | B01 |
| "Crédito Fiscal" | B01 |
| "CONSUMIDOR FINAL" | B02 |
| "FACTURA EXENTA" | B14 |
| "FACTURA GUBERNAMENTAL" | B15 |

## Cambio de Nomenclatura 2026

FACOT soporta la preparación para el cambio de prefijos previsto para 2026:

- Se pueden configurar nuevos prefijos por empresa
- Se puede establecer una fecha de activación
- El cambio puede ser automático o manual

Ver el diálogo de configuración NCF en la aplicación para más detalles.

## Consideraciones de Seguridad

- Los NCF no se exponen en logs
- Las transacciones usan bloqueos optimistas de Firestore
- Se valida el formato antes de asignar
- Se verifica duplicados antes de confirmar

## Solución de Problemas

### "Error al reservar NCF después de N intentos"
- Verificar conexión a Firestore
- Revisar logs para errores de transacción
- Si hay muchos intentos, puede haber contención alta

### "NCF ya existe (colisión detectada)"
- Verificar integridad de la secuencia
- Usar set_sequence para corregir manualmente

### Secuencia desincronizada
- El corrector automático debería ajustar
- Si persiste, revisar manualmente en Firestore Console
