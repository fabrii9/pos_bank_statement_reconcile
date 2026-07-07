# -*- coding: utf-8 -*-
"""
Reconstruye los vinculos pos.payment -> account.payment.

Debe ejecutarse despues de instalar el modulo pos_bank_statement_reconcile.

Uso:
    ./odoo-bin shell -c odoo.conf -d NOMBRE_BASE --no-http < rebuild_links.py
"""
import odoo
from odoo import api, SUPERUSER_ID
from collections import defaultdict

env = api.Environment(odoo.sql_db.db_connect('Mundolimpio_Produccion').cursor(), SUPERUSER_ID, {})

company = env.company
print(f"=== RECONSTRUCCION DE VINCULOS - {company.name} ===")

all_sessions = env['pos.session'].search([
    ('company_id', '=', company.id),
    ('state', '=', 'closed'),
])
print(f"Sesiones cerradas: {len(all_sessions)}")

res = all_sessions.action_rebuild_pos_payment_links()
print(f"Resultado: {res['params']['message']}")

# Verificar vinculos por metodo
configs = [
    ('Qr Clover', 'Clover'),
    ('Qr MP', 'Mercado Pago'),
    ('Transferencia Macro', 'Banco Macro'),
]
for mname, jname in configs:
    method = env['pos.payment.method'].search([
        ('name', 'ilike', mname),
        ('company_id', '=', company.id),
    ], limit=1)
    if not method:
        continue
    pos_payments = env['pos.payment'].search([('payment_method_id', '=', method.id)])
    linked = len(pos_payments.filtered(lambda p: p.account_payment_id))
    print(f"{jname}: pos.payments={len(pos_payments)}, "
          f"vinculados={linked}, sin={len(pos_payments)-linked}")

# Verificar pagos pendientes
print('\n=== PAGOS PENDIENTES FINALES ===')
for mname, jname in configs:
    method = env['pos.payment.method'].search([
        ('name', 'ilike', mname),
        ('company_id', '=', company.id),
    ], limit=1)
    journal = env['account.journal'].search([
        ('name', 'ilike', jname),
        ('type', '=', 'bank'),
        ('company_id', '=', company.id),
    ], limit=1)
    if not method or not journal:
        continue
    payments = env['account.payment'].search([
        ('journal_id', '=', journal.id),
        ('pos_payment_method_id', '=', method.id),
        ('pos_session_id', '!=', False),
        ('state', '!=', 'cancel'),
        ('is_matched', '=', False),
    ])
    print(f"{jname}: {len(payments)} recibos pendientes, "
          f"suspense={journal.suspense_account_id.code}, "
          f"outstanding={method.outstanding_account_id.code}")

env.cr.commit()
print('\nVinculos reconstruidos y guardados.')
