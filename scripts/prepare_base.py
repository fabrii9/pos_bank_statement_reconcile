# -*- coding: utf-8 -*-
"""
Prepara la base para usar el modulo pos_bank_statement_reconcile.

Realiza los siguientes pasos:
1. Cierra sesiones POS abiertas.
2. Cambia la suspense_account de los diarios bancarios para que coincida
   con la outstanding_account_id de los metodos de pago POS.
3. Reclasifica pagos agrupados historicos de la cuenta vieja (1.1.1.02.003)
   a las cuentas transitorias especificas por medio de pago.
4. Reclasifica lineas de extracto ya importadas (Banco Macro) a la cuenta
   transitoria correspondiente.

Uso:
    ./odoo-bin shell -c odoo.conf -d NOMBRE_BASE --no-http < prepare_base.py
"""
import odoo
from odoo import api, SUPERUSER_ID
from collections import defaultdict

# Reemplazar por el nombre real de la base de datos
DB_NAME = 'Mundolimpio_Produccion'

# Cuentas transitorias por medio de pago / diario
ACCOUNT_MAP = {
    'Clover': '1.1.1.02.013',
    'Mercado Pago': '1.1.1.02.012',
    'Banco Macro': '1.1.1.02.011',
}

# Cuenta vieja a reclasificar para pagos historicos
OLD_ACCOUNT_CODE = '1.1.1.02.003'

env = api.Environment(odoo.sql_db.db_connect(DB_NAME).cursor(), SUPERUSER_ID, {})
company = env.company
print(f"=== PREPARACION BASE {DB_NAME} - {company.name} ===")

# ------------------------------------------------------------------
# 1. Cerrar sesiones POS abiertas
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# 2. Cambiar suspense accounts de los diarios bancarios
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# 3. Reclasificar pagos agrupados historicos
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# 4. Reclasificar lineas de extracto Macro ya importadas
# ------------------------------------------------------------------
print("\n4. Reclasificando lineas de extracto Macro")
macro_journal = env['account.journal'].search([
    ('name', 'ilike', 'Banco Macro'),
    ('type', '=', 'bank'),
    ('company_id', '=', company.id),
], limit=1)
macro_account = env['account.account'].search([
    ('code', '=', ACCOUNT_MAP['Banco Macro']),
    ('company_ids', 'in', company.id),
], limit=1)
real_bank_account = env['account.account'].search([
    ('code', '=', '1.1.1.02.007'),
    ('company_ids', 'in', company.id),
], limit=1)

if not macro_journal or not macro_account:
    print(f"   - Banco Macro: diario o cuenta transitoria no encontrados")
else:
    # Lineas de extracto no reconciliadas que esten en cuentas viejas
    statement_lines = env['account.bank.statement.line'].search([
        ('journal_id', '=', macro_journal.id),
    ])
    lines_changed = 0
    for st_line in statement_lines:
        for aml in st_line.move_id.line_ids.filtered(lambda l: not l.reconciled):
            if aml.account_id == real_bank_account:
                continue
            if aml.account_id != macro_account:
                aml.account_id = macro_account
                lines_changed += 1
    print(f"   - Banco Macro: {lines_changed} lineas de extracto reclasificadas a {macro_account.code}")
    env.cr.commit()

# ------------------------------------------------------------------
# 5. Actualizar outstanding_account_id de pagos historicos
# ------------------------------------------------------------------
print("\n5. Actualizando outstanding_account_id de pagos historicos")
# Al cambiar las cuentas outstanding de los metodos de pago, los pagos ya
# creados conservan el outstanding_account_id anterior. Es necesario forzar
# su recomputacion para que apunten a la cuenta transitoria correcta.
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
