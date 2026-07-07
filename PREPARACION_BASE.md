# Preparación de la base para `pos_bank_statement_reconcile`

## Contexto

Este módulo permite conciliar automáticamente los pagos POS agrupados (`account.payment`) con las líneas de extractos bancarios.

Para que funcione correctamente, la **cuenta outstanding del método de pago POS** debe coincidir con la **cuenta suspense del diario bancario**. De esa manera, tanto el asiento del pago POS como el asiento de la línea de extracto quedan en la misma cuenta contable y Odoo puede reconciliarlos.

## Configuración objetivo

La base `Mundolimpio_Produccion` se preparó con **cuentas transitorias específicas por medio de pago**:

| Medio de pago POS | Cuenta outstanding del método | Diario bancario | Cuenta suspense del diario |
|-------------------|------------------------------|-----------------|----------------------------|
| `Qr Clover` | `1.1.1.02.013 CT - Clover` | Clover | `1.1.1.02.013 CT - Clover` |
| `Qr MP` | `1.1.1.02.012 CT - Mercado Pago` | Mercado Pago | `1.1.1.02.012 CT - Mercado Pago` |
| `Transferencia Macro` | `1.1.1.02.011 CT - Banco Macro` | Banco Macro | `1.1.1.02.011 CT - Banco Macro` |

Esta configuración mantiene separados contablemente los pendientes de cada medio de pago.

## Situación típica antes de preparar

Antes de la preparación, la base suele tener:

- Métodos de pago POS configurados con cuentas transitorias (`1.1.1.02.011/012/013`).
- Diarios bancarios con suspense account `1.1.1.02.002 Bank Suspense Account`.
- Pagos agrupados históricos en `1.1.1.02.003 Outstanding Receipts` (cuenta anterior).
- Algunos pagos recientes ya en las cuentas transitorias (desde que se cambiaron los métodos).
- Sesiones POS abiertas.
- Extractos importados solo en Banco Macro (con líneas en `1.1.1.02.002`, `1.1.1.02.003`, etc.).

## Pasos de preparación

### 1. Cerrar sesiones POS abiertas

Las sesiones abiertas deben cerrarse para que se generen los `account.payment` agrupados correspondientes.

En el script se cierran automáticamente con `action_pos_session_closing_control()`.

### 2. Cambiar suspense accounts de los diarios

Se actualiza cada diario bancario para que su `suspense_account_id` sea igual a la cuenta outstanding del método de pago POS correspondiente:

- Clover → `1.1.1.02.013`
- Mercado Pago → `1.1.1.02.012`
- Banco Macro → `1.1.1.02.011`

**Importante:** este cambio solo afecta a extractos futuros. Los extractos ya importados no cambian automáticamente.

### 3. Reclasificar pagos agrupados históricos

Los pagos agrupados generados antes del cambio de cuentas suelen estar en `1.1.1.02.003 Outstanding Receipts`. Se reclasifican las líneas no reconciliadas de esos asientos hacia la cuenta transitoria correspondiente:

- Pagos Clover de `1.1.1.02.003` → `1.1.1.02.013`
- Pagos Mercado Pago de `1.1.1.02.003` → `1.1.1.02.012`
- Pagos Banco Macro de `1.1.1.02.003` → `1.1.1.02.011`

Solo se tocan líneas **no reconciliadas**.

### 4. Reclasificar líneas de extracto ya importadas (Banco Macro)

Para Banco Macro, como ya había extractos importados con líneas en `1.1.1.02.002` o `1.1.1.02.003`, se reclasifican las líneas no reconciliadas hacia `1.1.1.02.011`.

No se tocan las líneas en `1.1.1.02.007 Banco Macro` (cuenta real del banco) ni líneas ya reconciliadas.

### 5. Actualizar `outstanding_account_id` de pagos históricos

Al cambiar la cuenta outstanding de los métodos de pago POS, los pagos agrupados (`account.payment`) ya creados conservan en su campo `outstanding_account_id` la cuenta anterior (`1.1.1.02.003` o `1.1.1.02.004`).

Si no se actualiza este campo, el módulo de conciliación buscará conciliar en la cuenta vieja y fallará, aunque las líneas del asiento ya estén reclasificadas.

Es necesario forzar la recomputación de `outstanding_account_id` en todos los pagos de los diarios Clover, Mercado Pago y Banco Macro. El script `prepare_base.py` lo hace llamando a `_compute_outstanding_account_id()`.

### 6. Instalar/actualizar el módulo

```bash
./odoo-bin -c odoo.conf -d NOMBRE_BASE -i pos_bank_statement_reconcile --stop-after-init --no-http
```

Si el módulo ya está instalado, usar `-u` en lugar de `-i`.

### 7. Reconstruir vínculos `pos.payment` → `account.payment`

El módulo agrega el campo `account_payment_id` en `pos.payment`. Para las sesiones cerradas antes de instalar el módulo, ese campo está vacío.

Se ejecuta `action_rebuild_pos_payment_links()` sobre todas las sesiones POS cerradas para reconstruir los vínculos.

### 8. Reiniciar el servidor

Después de instalar/actualizar el módulo y hacer cambios en la base, reiniciar el servidor de Odoo para que cargue los modelos y vistas actualizados.

## Scripts

Los scripts se encuentran en `addons/pos_bank_statement_reconcile/scripts/`:

- `prepare_base.py`: cierra sesiones, cambia suspense accounts, reclasifica asientos, reclasifica líneas de extracto y actualiza `outstanding_account_id` de pagos históricos.
- `rebuild_links.py`: instala el módulo (manual) y reconstruye vínculos.

**Antes de ejecutar los scripts, reemplazar `NOMBRE_BASE` por el nombre real de la base de datos.**

### Ejemplo de ejecución

```bash
# Preparar base
./odoo-bin shell -c odoo.conf -d Mundolimpio_Produccion --no-http < addons/pos_bank_statement_reconcile/scripts/prepare_base.py

# Instalar/actualizar modulo
./odoo-bin -c odoo.conf -d Mundolimpio_Produccion -i pos_bank_statement_reconcile --stop-after-init --no-http

# Reconstruir vinculos
./odoo-bin shell -c odoo.conf -d Mundolimpio_Produccion --no-http < addons/pos_bank_statement_reconcile/scripts/rebuild_links.py

# Reiniciar servidor
pkill -f "odoo-bin -c odoo.conf"
cd /ruta/del/proyecto && nohup ./odoo/odoo-bin -c odoo.conf > /tmp/odoo_server.log 2>&1 & disown
```

## Verificación final

Después de la preparación, se debe verificar que:

1. No haya sesiones POS abiertas.
2. La suspense account de cada diario coincida con la outstanding account del método.
3. Los pagos agrupados pendientes estén todos en la cuenta transitoria correspondiente.
4. Todos los `pos.payment` tengan `account_payment_id`.
5. El servidor responda correctamente.

## Resultado esperado en `Mundolimpio_Produccion`

Después de la última preparación:

| Diario | Recibos pendientes | Suspense | Outstanding |
|--------|-------------------:|----------|-------------|
| Clover | 99 | `1.1.1.02.013` | `1.1.1.02.013` |
| Mercado Pago | 106 | `1.1.1.02.012` | `1.1.1.02.012` |
| Banco Macro | 53 | `1.1.1.02.011` | `1.1.1.02.011` |

Vínculos reconstruidos: **1.097 pagos POS** (454 Clover, 431 Mercado Pago, 212 Banco Macro).

## Notas importantes

### Clover y Mercado Pago

- No tenían extractos importados al momento de la preparación.
- Al importar extractos nuevos, las líneas irán automáticamente a la cuenta suspense del diario (`1.1.1.02.013` o `1.1.1.02.012`), que coincide con los pagos.
- El módulo debería poder conciliar automáticamente en la mayoría de los casos.

### Banco Macro

- A diferencia de Clover y Mercado Pago, Macro es un diario bancario general que se usa también para operaciones manuales (proveedores, clientes, transferencias).
- El extracto de Macro contiene muchas líneas que no corresponden a pagos POS (liquidaciones, comisiones, transferencias entre cuentas, etc.).
- Además, las transferencias de clientes pueden agrupar varios pagos POS o tener montos con pequeñas diferencias.
- Por eso, **el matching automático uno a uno puede no funcionar para todos los casos**. En esos casos se recomienda usar el módulo como herramienta de diagnóstico y completar la conciliación con el reconciliador nativo de Odoo.
- Si se desea automatizar más, se puede desarrollar matching por suma de líneas, referencia o CUIT.

## Alternativas no utilizadas

- **Volver todo a `1.1.1.02.003`**: descartada porque invalidaba los días recientes de producción con cuentas transitorias.
- **Asiento de clearing**: descartada porque el usuario prefirió ajustar las cuentas para que coincidan.
