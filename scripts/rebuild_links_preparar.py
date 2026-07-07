# -*- coding: utf-8 -*-
"""
Reconstruye vinculos pos.payment -> account.payment en Mundolimpio_Produccion_PREPARAR.
"""
import odoo
from odoo import api, SUPERUSER_ID

DB_NAME = 'Mundolimpio_Produccion_PREPARAR'

env = api.Environment(odoo.sql_db.db_connect(DB_NAME).cursor(), SUPERUSER_ID, {})
company = env.company
print(f"=== RECONSTRUCCION DE VINCULOS {DB_NAME} - {company.name} ===")

closed_sessions = env['pos.session'].search([
    ('company_id', '=', company.id),
    ('state', '=', 'closed'),
])
print(f"\nSesiones cerradas encontradas: {len(closed_sessions)}")

closed_sessions.action_rebuild_pos_payment_links()
env.cr.commit()

# Verificar vinculos
print("\n=== VERIFICACION DE VINCULOS ===")
methods = ['Qr Clover', 'Qr MP', 'Transferencia Macro']
for method_name in methods:
    method = env['pos.payment.method'].search([
        ('name', 'ilike', method_name),
        ('company_id', '=', company.id),
    ], limit=1)
    if not method:
        print(f"{method_name}: metodo no encontrado")
        continue
    pos_payments = env['pos.payment'].search([
        ('payment_method_id', '=', method.id),
        ('session_id.state', '=', 'closed'),
    ])
    linked = pos_payments.filtered(lambda p: p.account_payment_id)
    unlinked = pos_payments.filtered(lambda p: not p.account_payment_id)
    print(f"{method_name}: {len(linked)} vinculados, {len(unlinked)} sin vincular")

print("\n=== FINALIZADO ===")
