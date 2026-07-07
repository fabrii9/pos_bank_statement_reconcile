# Conciliación Bancaria POS

Módulo Odoo 18 para conciliar automáticamente líneas de extracto bancario con los pagos POS agrupados que genera el cierre de sesión POS.

## Problema que resuelve

Odoo cierra la sesión POS creando un único `account.payment` por método de pago/sesión. El extracto bancario, en cambio, trae una línea por cada transacción/acreditación. Como los montos no coinciden y no existe trazabilidad de los pagos individuales, Odoo no sugiere contrapartidas para conciliar.

## Solución

El módulo:

1. Guarda la relación entre cada `pos.payment` individual y el `account.payment` agrupado generado al cerrar la sesión.
2. Permite ejecutar un wizard que, para cada línea de extracto no conciliada, busca qué pagos POS individuales (dentro de un pago agrupado) suman ese monto.
3. Clasifica los resultados como:
   - `matched`: match exacto único.
   - `partial`: match dentro de la tolerancia configurada.
   - `ambiguous`: más de una combinación posible.
   - `unmatched`: sin combinación posible.
4. Permite revisar y confirmar la conciliación, documentando todo en modelos persistentes.

## Requisito previo de configuración contable

Para que la conciliación contable funcione, la **cuenta puente** de los pagos POS debe coincidir con la **cuenta suspense** del diario bancario. Es decir:

- La `outstanding_account_id` del método de pago POS debe ser la misma que la `suspense_account_id` del diario bancario; o
- Cambiar la `suspense_account_id` del diario para que coincida con la `outstanding_account_id` del método de pago POS.

Sin esta configuración, el wizard podrá encontrar los matches por monto, pero la reconciliación contable fallará porque no habrá líneas en la misma cuenta para emparejar.

## Uso

1. Cerrar sesiones POS normalmente. El módulo vincula automáticamente los pagos individuales con el pago agrupado.
2. Importar el extracto bancario de cada diario (Mercado Pago, Macro, Clover).
3. Ir a **Contabilidad → Banco → Conciliación POS → Nueva conciliación**.
4. Seleccionar el diario bancario y el rango de fechas.
5. Click en **Previsualizar conciliación**.
6. Revisar las líneas propuestas, marcar/desmarcar según corresponda.
7. Click en **Confirmar conciliación**.
8. Revisar la sesión creada con el detalle de cada línea conciliada.

## Estructura del módulo

```
pos_bank_statement_reconcile/
├── __manifest__.py
├── models/
│   ├── pos_payment.py          # campo account_payment_id en pos.payment
│   ├── account_payment.py      # campo pos_payment_ids en account.payment
│   ├── pos_session.py          # vinculación al cerrar sesión
│   ├── pos_bank_reconcile_session.py
│   └── pos_bank_reconcile_line.py
├── wizards/
│   ├── pos_bank_reconcile_wizard.py
│   └── pos_bank_reconcile_wizard_views.xml
├── views/
│   ├── pos_bank_reconcile_session_views.xml
│   ├── pos_bank_reconcile_line_views.xml
│   └── pos_bank_statement_reconcile_menus.xml
├── security/
│   └── ir.model.access.csv
└── i18n/
    └── es.po
```

## Notas

- El módulo no modifica el cierre POS nativo: sigue generando un recibo agrupado por sesión/método.
- Los reembolsos y montos negativos quedarán como `unmatched` hasta una futura mejora.
- Se recomienda probar en un entorno de testing antes de usar en producción.
