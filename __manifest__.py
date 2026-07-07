# -*- coding: utf-8 -*-
{
    'name': 'Conciliación Bancaria POS',
    'version': '18.0.1.1.0',
    'category': 'Accounting/Accounting',
    'summary': 'Concilia extractos bancarios con pagos POS agrupados por sesión',
    'description': """
Conciliación Bancaria POS
=========================

Este módulo permite conciliar automáticamente las líneas de extracto bancario
(Mercado Pago, Banco Macro, Clover, etc.) contra los pagos POS que Odoo agrupa
en un único `account.payment` al cerrar la sesión POS.

Características principales:
----------------------------
* Guarda la relación entre cada `pos.payment` individual y el `account.payment`
  agrupado generado al cerrar sesión.
* Permite importar/previsualizar líneas de extracto bancario y buscar qué pagos
  POS individuales componen cada depósito/acreditación.
* Motor de emparejamiento por monto con tolerancia (subset-sum) que detecta
  combinaciones de pagos POS que suman el monto de una línea de extracto.
* Wizard de previsualización y confirmación con estados:
  `matched`, `partial`, `ambiguous`, `unmatched`, `reconciled`.
* Reconocimiento de conciliaciones parciales previas: detecta líneas de extracto
  ya reconciliadas con el recibo y permite continuar conciliando el saldo
  residual sin desconciliar lo ya registrado.
* Bloqueo preventivo: solo se confirman líneas en estado `matched`, evitando
  que una conciliación parcial deje el pago con saldo pendiente.
* Documentación persistente de cada ejecución de conciliación.
* Reporte de líneas sin match y pagos POS no conciliados.

El módulo no modifica el cierre POS nativo: sigue generando un recibo agrupado
por sesión/método, pero agrega la trazabilidad necesaria para conciliar contra
el extracto bancario línea a línea.
    """,
    'author': 'Mundo Limpio',
    'website': 'https://www.mundolimpio.com',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/pos_bank_reconcile_sequence.xml',
        'views/pos_session_views.xml',
        'views/pos_bank_reconcile_session_views.xml',
        'views/pos_bank_reconcile_line_views.xml',
        'views/pos_bank_statement_reconcile_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
