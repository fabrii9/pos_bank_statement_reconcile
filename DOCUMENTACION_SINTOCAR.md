# Análisis: conciliación sin cambiar cuentas en `Mundolimpio_Produccion_sintocar`

## 1. Estado actual de la base

Base analizada: `Mundolimpio_Produccion_sintocar`  
Módulo `pos_bank_statement_reconcile`: **no instalado**.

### Configuración contable (sin tocar)

| Método / Diario               | Cuenta outstanding del método | Cuenta suspense del diario |
|-------------------------------|------------------------------|----------------------------|
| `Qr Clover` / Clover          | `1.1.1.02.013 CT - Clover`   | `1.1.1.02.002 Bank Suspense Account` |
| `Qr MP` / Mercado Pago        | `1.1.1.02.012 CT - Mercado Pago` | `1.1.1.02.002 Bank Suspense Account` |
| `Transferencia Macro` / Banco Macro | `1.1.1.02.011 CT - Banco Macro` | `1.1.1.02.002 Bank Suspense Account` |

### Pagos agrupados pendientes

| Diario        | Recibos pendientes | Cuentas donde quedaron los asientos |
|---------------|-------------------:|-------------------------------------|
| Clover        | 97                 | 92 en `1.1.1.02.003 Outstanding Receipts`, 5 en `1.1.1.02.013 CT - Clover` |
| Mercado Pago  | 104                | 97 en `1.1.1.02.003 Outstanding Receipts`, 7 en `1.1.1.02.012 CT - Mercado Pago` |
| Banco Macro   | 52                 | 53 en `1.1.1.02.003 Outstanding Receipts`, 3 en `1.1.1.02.011 CT - Banco Macro` |

### Extractos importados

| Diario        | Líneas importadas | No reconciliadas | Observación |
|---------------|------------------:|-----------------:|-------------|
| Clover        | 0                 | 0                | Aún no se importó extracto. |
| Mercado Pago  | 0                 | 0                | Aún no se importó extracto. |
| Banco Macro   | 885               | 647              | Las líneas están en varias cuentas: `1.1.1.02.007 Banco Macro`, `1.1.1.02.003 Outstanding Receipts`, `1.1.1.02.011 CT - Banco Macro`, `1.1.1.02.002 Bank Suspense Account`. |

### Sesiones POS

Hay sesiones POS abiertas:
- `POS/00121`, `POS/00120`, `POS/00119`, `POS/00115`, `POS/00114`.

## 2. Por qué el módulo actual no puede conciliar "sin tocar" cuentas

El reconciliador funciona en dos etapas:

1. **Matching**: empareja cada `pos.payment` individual con una línea de extracto por monto (± tolerancia), fecha y, opcionalmente, referencia.
2. **Conciliación contable**: busca líneas del asiento del pago y del asiento de la línea de extracto que estén en la **misma cuenta contable** y las reconcilia.

Si las cuentas no coinciden, el paso 2 falla.

En `Mundolimpio_Produccion_sintocar`:
- Los pagos POS (métodos) terminan mayormente en `1.1.1.02.003` o en las cuentas transitorias específicas (`...013`, `...012`, `...011`).
- El diario bancario tiene configurada la suspense account `1.1.1.02.002`. Al importar un extracto nuevo, las líneas irían a `1.1.1.02.002`.
- Para Banco Macro, además, las líneas ya importadas están en múltiples cuentas (`1.1.1.02.007`, `1.1.1.02.003`, `1.1.1.02.011`, `1.1.1.02.002`).

**Conclusión**: con la configuración actual, la cuenta del pago raramente coincidirá con la cuenta de la línea de extracto, por lo que la conciliación contable no se podrá completar sin un mecanismo adicional.

## 3. Opciones para resolver

### Opción A: crear un asiento de clearing al confirmar (recomendada)

Cambiar el módulo para que, cuando las cuentas no coincidan, genere un asiento contable puente entre la cuenta de la línea de extracto y la cuenta del pago, y reconcilie cada parte con ese asiento.

**Ventajas:**
- No se modifican las cuentas configuradas en diarios ni métodos de pago.
- No se tocan asientos históricos.
- La conciliación es contablemente válida.

**Desventajas:**
- Mayor complejidad en el código.
- Se generan asientos adicionales.
- Hay que manejar bien los signos (débito/crédito) y las monedas.

### Opción B: reclasificar las líneas de extracto a la cuenta del pago al confirmar

Antes de reconciliar, cambiar la cuenta contable de la línea de extracto (o del pago) para que ambas coincidan.

**Ventajas:**
- Más simple de implementar.

**Desventajas:**
- Modifica asientos contables publicados, lo cual no es deseable y puede estar bloqueado por fechas de cierre o hashes.
- Cambia la naturaleza contable de la línea de extracto.

### Opción C: usar el reconciliador nativo de Odoo

No usar este módulo y seguir conciliando con el widget nativo.

**Ventajas:**
- No requiere desarrollo.

**Desventajas:**
- No aprovecha el matching automático por pago POS individual.
- Para Macro sigue siendo muy manual porque las transferencias no aparecen línea a línea.

## 4. Problemas adicionales por diario

### Clover y Mercado Pago

- No tienen extractos importados aún.
- Al importarlos, las líneas irán a la cuenta suspense del diario (`1.1.1.02.002`).
- Los pagos POS están mayormente en `1.1.1.02.003` o en las cuentas transitorias del método.
- **Requiere**: implementar clearing (Opción A) para poder conciliar sin cambiar cuentas.

### Banco Macro

- Tiene 647 líneas de extracto no reconciliadas.
- **No hay coincidencias exactas de monto** con los 52 recibos agrupados pendientes.
- Las transferencias aparecen como líneas individuales con referencias como `ING TRANSF:NOMBRE-CUIT`, pero cada transferencia puede agrupar varios recibos POS.
- Ejemplo de montos de extracto: `8150.0`, `12000.0`, `45636.42`, `332334.43`.
- Ejemplo de montos de recibos: `8151.31`, `9867.55`, `11999.99`, etc.
- **Requiere**: además del clearing, desarrollar criterios de matching por **suma de recibos**, **lotes** o **referencia/CUIT**.

## 5. Plan de trabajo recomendado

1. **Instalar el módulo** `pos_bank_statement_reconcile` en `Mundolimpio_Produccion_sintocar`.
2. **Cerrar las sesiones POS abiertas** para que se generen los `account.payment` agrupados.
3. **Reconstruir los vínculos** `pos.payment` → `account.payment`.
4. **Adaptar el módulo** para soportar conciliación con clearing cuando las cuentas no coincidan.
5. **Desarrollar matching por lote/referencia** para Banco Macro.
6. **Probar**:
   - Importar extracto Clover y conciliar.
   - Importar extracto Mercado Pago y conciliar.
   - Conciliar Banco Macro con los nuevos criterios.

## 6. Nota importante

Si al final se opta por **no** desarrollar el clearing, la única forma estándar de que el módulo funcione es **cambiar la cuenta suspense de cada diario** para que coincida con la cuenta outstanding del método de pago POS correspondiente (y reclasificar los asientos históricos que estén en cuentas distintas). Esto es justamente lo que se hizo en `Mundolimpio_Produccion` y es lo que el usuario quiere evitar en `Mundolimpio_Produccion_sintocar`.
