# -*- coding: utf-8 -*-
"""
Prepara Mundolimpio_Produccion_PREPARAR para usar pos_bank_statement_reconcile.
Version Opcion B: no toca extractos historicos de Banco Macro.
"""
import odoo
from odoo import api, SUPERUSER_ID

DB_NAME = 'Mundolimpio_Produccion_PREPARAR'

ACCOUNT_MAP = {
    'Clover': '1.1.1.02.013',
    'Mercado Pago': '1.1.1.02.012',
    'Banco Macro': '1.1.1.02.011',
}

OLD_ACCOUNT_CODE = '1.1.1.02.003'

env = api.Environment(odoo.sql_db.db_connect(DB_NAME).cursor(), SUPERUSER_ID, {})
company = env.company
print(f"=== PREPARACION BASE {DB_NAME} - {company.name} ===")

# 1. Cerrar sesiones POS abiertas
open_sessions = env['pos.session'].search([
    ('company_id', '=', company.id),
    ('state', '!=', 'closed'),
])
print(f"\n1. Sesiones POS abiertas: {len(open_sessions)}")
for session in open_sessions:
    print(f"   - {session.name}: {session.state}")
    try:
        session.action_pos_session_closing_control()
        print(f"     Cerrada OK")
    except Exception as e:
        print(f"     ERROR cerrando: {e}")
env.cr.commit()

# 2. Cambiar suspense accounts de los diarios bancarios
print("\n2. Actualizando suspense accounts de diarios bancarios")
for journal_name, account_code in ACCOUNT_MAP.items():
    journal = env['account.journal'].search([
        ('name', 'ilike', journal_name),
        ('type', '=', 'bank'),
        ('company_id', '=', company.id),
    ], limit=1)
    if not journal:
        print(f"   - {journal_name}: diario no encontrado")
        continue
    account = env['account.account'].search([
        ('code', '=', account_code),
        ('company_ids', 'in', company.id),
    ], limit=1)
    if not account:
        print(f"   - {journal_name}: cuenta {account_code} no encontrada")
        continue
    if journal.suspense_account_id != account:
        journal.suspense_account_id = account
        print(f"   - {journal_name}: suspense -> {account.code} ({account.name})")
    else:
        print(f"   - {journal_name}: suspense ya era {account.code}")
env.cr.commit()

# 3. Reclasificar pagos agrupados historicos (solo lineas no reconciliadas)
print("\n3. Reclasificando pagos agrupados historicos")
old_account = env['account.account'].search([
    ('code', '=', OLD_ACCOUNT_CODE),
    ('company_ids', 'in', company.id),
], limit=1)
if not old_account:
    print(f"   - Cuenta {OLD_ACCOUNT_CODE} no encontrada, se omite este paso")
else:
    configs = [
        ('Qr Clover', 'Clover'),
        ('Qr MP', 'Mercado Pago'),
        ('Transferencia Macro', 'Banco Macro'),
    ]
    for method_name, journal_name in configs:
        method = env['pos.payment.method'].search([
            ('name', 'ilike', method_name),
            ('company_id', '=', company.id),
        ], limit=1)
        journal = env['account.journal'].search([
            ('name', 'ilike', journal_name),
            ('type', '=', 'bank'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not method or not journal:
            print(f"   - {journal_name}: metodo o diario no encontrado")
            continue
        target_account = env['account.account'].search([
            ('code', '=', ACCOUNT_MAP[journal_name]),
            ('company_ids', 'in', company.id),
        ], limit=1)
        if not target_account:
            print(f"   - {journal_name}: cuenta {ACCOUNT_MAP[journal_name]} no encontrada")
            continue

        payments = env['account.payment'].search([
            ('journal_id', '=', journal.id),
            ('pos_payment_method_id', '=', method.id),
            ('state', '!=', 'cancel'),
        ])
        moved = 0
        for payment in payments:
            move = payment.move_id
            for line in move.line_ids.filtered(lambda l: l.account_id == old_account and not l.reconciled):
                line.account_id = target_account
                moved += 1
        print(f"   - {journal_name}: {moved} lineas reclasificadas de {old_account.code} a {target_account.code}")
    env.cr.commit()

# 4. OPCION B: NO se reclasifican lineas de extracto historicas de Macro
print("\n4. OPCION B: se omite reclasificacion de extractos historicos de Banco Macro")

# 5. Actualizar outstanding_account_id de pagos historicos
print("\n5. Actualizando outstanding_account_id de pagos historicos")
for journal_name in ACCOUNT_MAP.keys():
    journal = env['account.journal'].search([
        ('name', 'ilike', journal_name),
        ('type', '=', 'bank'),
        ('company_id', '=', company.id),
    ], limit=1)
    if not journal:
        continue
    payments = env['account.payment'].search([
        ('journal_id', '=', journal.id),
        ('state', '!=', 'cancel'),
    ])
    if payments:
        payments._compute_outstanding_account_id()
        print(f"   - {journal_name}: {len(payments)} pagos actualizados")
        env.cr.commit()

print("\n=== PREPARACION FINALIZADA ===")
