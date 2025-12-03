# Configuración de Firebase para FACOT 2.0

Esta guía explica cómo configurar Firebase/Firestore para FACOT 2.0.

## Requisitos Previos

1. Una cuenta de Google
2. Acceso a la [Consola de Firebase](https://console.firebase.google.com/)
3. FACOT 2.0 instalado

## Paso 1: Crear un Proyecto Firebase

1. Ir a [Firebase Console](https://console.firebase.google.com/)
2. Click en "Agregar proyecto"
3. Nombrar el proyecto (ej: `facot-produccion`)
4. Opcionalmente habilitar Google Analytics
5. Esperar a que se cree el proyecto

## Paso 2: Habilitar Firestore

1. En el panel izquierdo, ir a **Build > Firestore Database**
2. Click en "Create database"
3. Seleccionar modo de producción o prueba según necesidad
4. Seleccionar la ubicación del servidor (recomendado: la más cercana a tus usuarios)
5. Click en "Enable"

## Paso 3: Crear Credenciales (Service Account)

1. En la consola de Firebase, ir a **Configuración del proyecto** (ícono de engranaje)
2. Ir a la pestaña **Service accounts**
3. Click en **Generate new private key**
4. Confirmar y descargar el archivo JSON
5. **IMPORTANTE**: Guardar este archivo en un lugar seguro. No compartir ni subir a repositorios públicos.

## Paso 4: Habilitar Storage (Opcional)

Si planeas usar Storage para logos y archivos:

1. En el panel izquierdo, ir a **Build > Storage**
2. Click en "Get started"
3. Aceptar las reglas de seguridad por defecto
4. Seleccionar ubicación
5. Click en "Done"

## Paso 5: Configurar FACOT

### Opción A: Diálogo de Configuración (Recomendado)

1. Iniciar FACOT
2. Si es la primera vez, aparecerá automáticamente el diálogo de configuración
3. Seleccionar el archivo JSON de credenciales descargado
4. El bucket de storage se autocompletará
5. Click en "Guardar y conectar"

### Opción B: Variables de Entorno

Crear un archivo `.env` en el directorio de FACOT:

```env
FIREBASE_CREDENTIALS=./ruta/a/credenciales.json
FIREBASE_STORAGE_BUCKET=tu-proyecto-id.firebasestorage.app
```

### Opción C: Configuración Manual

Copiar el archivo de credenciales a:
- Windows: `%APPDATA%\FACOT\firebase-credentials.json`
- Linux/Mac: `~/.FACOT/firebase-credentials.json`

O colocar `firebase-credentials.json` en el directorio de trabajo.

## Estructura de Colecciones

FACOT utiliza las siguientes colecciones en Firestore:

| Colección | Descripción |
|-----------|-------------|
| `companies` | Empresas registradas |
| `invoices` | Facturas (con subcolección `items`) |
| `quotations` | Cotizaciones (con subcolección `items`) |
| `clients` | Clientes |
| `items` | Catálogo de ítems/productos |
| `third_parties` | Terceros (proveedores/clientes por RNC) |
| `ncf_sequence_configs` | Configuración de secuencias NCF |

## Reglas de Seguridad (firestore.rules)

Ejemplo básico de reglas de seguridad:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Solo usuarios autenticados pueden leer/escribir
    match /{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
```

Para producción, se recomienda reglas más específicas por colección.

## Usar el Emulador de Firestore (Desarrollo)

Para desarrollo local sin afectar datos de producción:

1. Instalar Firebase CLI:
   ```bash
   npm install -g firebase-tools
   ```

2. Inicializar emuladores:
   ```bash
   firebase init emulators
   ```

3. Iniciar el emulador de Firestore:
   ```bash
   firebase emulators:start --only firestore
   ```

4. Configurar FACOT para usar el emulador:
   ```env
   FIRESTORE_EMULATOR_HOST=localhost:8080
   ```

## Solución de Problemas

### Error: "No se encontró archivo de credenciales"
- Verificar que el archivo JSON existe en la ruta especificada
- Verificar permisos de lectura del archivo

### Error: "Permission denied"
- Verificar que el service account tiene los permisos necesarios
- Revisar las reglas de seguridad de Firestore

### Error: "Could not refresh access token"
- El archivo de credenciales puede estar corrupto
- Generar nuevas credenciales desde Firebase Console

### Error de conexión
- Verificar conexión a internet
- Si usas proxy, configurarlo en las variables de entorno

## Migración desde SQLite

Si tienes datos existentes en SQLite:

1. Los migradores existentes en FACOT siguen funcionando
2. No se modifican las rutas ni lógica de migración
3. Usar el migrador apropiado según tu versión

## Backups

FACOT crea backups automáticos diarios de Firestore:
- Se ejecutan a las 02:00 por defecto
- Se guardan en `./backups/YYYY-MM-DD/`
- Retención de 30 días por defecto
- Ver [BACKUPS.md](BACKUPS.md) para más detalles
