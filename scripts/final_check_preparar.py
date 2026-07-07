# -*- coding: utf-8 -*-
import odoo
from odoo import api, SUPERUSER_ID

env = api.Environment(odoo.sql_db.db_connect('Mundolimpio_Produccion_PREPARAR').cursor(), SUPERUSER_ID, {})
company = env.company

print("=== VERIFICACION FINAL Mundolimpio_Produccion_PREPARAR ===")
print(f"Compania: {company.name}")
print()

configs = [
    ('Clover', '1.1.1.02.013', '1.1.1.02.009'),
    ('Mercado Pago', '1.1.1.02.012', '1.1.1.02.008'),
    ('Banco Macro', '1.1.1.02.011', '1.1.1.02.007'),
]

for journal_name, suspense_code, bank_code in configs:
    journal = env['account.journal'].search([
        ('name', 'ilike', journal_name),
        ('type', '=', 'bank'),
        ('company_id', '=', company.id)
    ], limit=1)
    if not journal:
        continue
    
    print(f"### {journal_name}")
    print(f"  Suspense account: {journal.suspense_account_id.code} - {journal.suspense_account_id.name}")
    print(f"  Default account: {journal.default_account_id.code} - {journal.default_account_id.name}")
    
    # Pagos POS
    payments = env['account.payment'].search([
        ('journal_id', '=', journal.id),
        ('state', '!=', 'cancel'),
        ('pos_session_id', '!=', False),
    ])
    print(f"  Pagos POS: {len(payments)}")
    
    # Verificar outstanding_account_id
    wrong = payments.filtered(lambda p: p.outstanding_account_id.code != suspense_code)
    print(f"  Pagos con outstanding incorrecto: {len(wrong)}")
    if wrong:
        print(f"    Cuentas incorrectas: {list(set(wrong.mapped('outstanding_account_id.code')))}")
    
    # Lineas de extracto
    st_lines = env['account.bank.statement.line'].search([('journal_id', '=', journal.id)])
    print(f"  Lineas de extracto: {len(st_lines)}")
    
    # Saldos
    suspense_account = env['account.account'].search([('code', '=', suspense_code), ('company_ids', 'in', company.id)], limit=1)
    bank_account = env['account.account'].search([('code', '=', bank_code), ('company_ids', 'in', company.id)], limit=1)
    if suspense_account:
        print(f"  Saldo cuenta transitoria {suspense_code}: {suspense_account.current_balance:,.2f}")
    if bank_account:
        print(f"  Saldo cuenta bancaria {bank_code}: {bank_account.current_balance:,.2f}")
    print()

# Modulo instalado
module = env['ir.module.module'].search([('name', '=', 'pos_bank_statement_reconcile')])
print(f"Modulo pos_bank_statement_reconcile: {module.state}")

env.cr.rollback()
