# -*- coding: utf-8 -*-
import odoo
from odoo import api, SUPERUSER_ID

env = api.Environment(odoo.sql_db.db_connect('Mundolimpio_Produccion_PREPARAR').cursor(), SUPERUSER_ID, {})
company = env.company

print(f"Compania: {company.name}")
print(f"ID: {company.id}")
print()

configs = [
    ('Qr Clover', 'Clover', '1.1.1.02.013', '1.1.1.02.009'),
    ('Qr MP', 'Mercado Pago', '1.1.1.02.012', '1.1.1.02.008'),
    ('Transferencia Macro', 'Banco Macro', '1.1.1.02.011', '1.1.1.02.007'),
]

for method_name, journal_name, suspense_code, bank_code in configs:
    journal = env['account.journal'].search([
        ('name', 'ilike', journal_name),
        ('type', '=', 'bank'),
        ('company_id', '=', company.id)
    ], limit=1)
    if not journal:
        print(f"{journal_name}: NO ENCONTRADO")
        continue
    
    print(f"{journal_name}:")
    print(f"  Diario: {journal.name}")
    print(f"  Cuenta bancaria: {journal.default_account_id.code} - {journal.default_account_id.name}")
    print(f"  Suspense account: {journal.suspense_account_id.code} - {journal.suspense_account_id.name}")
    
    # Buscar cuenta objetivo
    target_account = env['account.account'].search([
        ('code', '=', suspense_code),
        ('company_ids', 'in', company.id)
    ], limit=1)
    print(f"  Cuenta objetivo {suspense_code}: {'ENCONTRADA' if target_account else 'NO ENCONTRADA'}")
    
    # Pagos del diario
    payments = env['account.payment'].search([
        ('journal_id', '=', journal.id),
        ('state', '!=', 'cancel'),
        ('pos_session_id', '!=', False),
    ])
    print(f"  Pagos POS: {len(payments)}")
    if payments:
        sample_accounts = payments[:5].mapped('outstanding_account_id.code')
        print(f"  outstanding_account_id de muestra: {sample_accounts}")
    
    # Lineas de extracto
    st_lines = env['account.bank.statement.line'].search([('journal_id', '=', journal.id)])
    print(f"  Lineas de extracto: {len(st_lines)}")
    print()

env.cr.rollback()
