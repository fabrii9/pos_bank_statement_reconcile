# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PosBankReconcileLine(models.Model):
    _name = 'pos.bank.reconcile.line'
    _description = 'Línea de conciliación bancaria POS'
    _order = 'session_id, state, amount_payment desc'

    session_id = fields.Many2one(
        comodel_name='pos.bank.reconcile.session',
        string='Sesión',
        required=True,
        ondelete='cascade',
    )
    selected = fields.Boolean(
        string='Incluir',
        default=True,
    )
    statement_line_ids = fields.Many2many(
        comodel_name='account.bank.statement.line',
        string='Líneas de extracto',
    )
    statement_line_count = fields.Integer(
        string='Líneas extracto',
        compute='_compute_counts',
    )
    reconciled_statement_line_ids = fields.Many2many(
        comodel_name='account.bank.statement.line',
        string='Líneas de extracto ya reconciliadas',
    )
    reconciled_statement_line_count = fields.Integer(
        string='Líneas extracto ya reconciliadas',
        compute='_compute_counts',
    )
    payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Pago POS agrupado',
    )
    pos_session_id = fields.Many2one(
        comodel_name='pos.session',
        string='Sesión POS',
    )
    pos_payment_method_id = fields.Many2one(
        comodel_name='pos.payment.method',
        string='Método de pago POS',
    )
    pos_payment_ids = fields.Many2many(
        comodel_name='pos.payment',
        string='Pagos POS individuales',
    )
    pos_payment_count = fields.Integer(
        string='Pagos POS',
        compute='_compute_counts',
    )
    pos_payment_matched_count = fields.Integer(
        string='Pagos POS con match',
        compute='_compute_counts',
    )
    pos_payment_missing_count = fields.Integer(
        string='Cantidad sin match',
        compute='_compute_counts',
    )
    pos_payment_ambiguous_count = fields.Integer(
        string='Pagos POS ambiguos',
        compute='_compute_counts',
    )
    pos_payment_missing_ids = fields.Many2many(
        comodel_name='pos.payment',
        string='Pagos POS sin match',
        compute='_compute_counts',
    )
    missing_amounts = fields.Char(
        string='Montos faltantes',
        compute='_compute_counts',
    )
    amount_payment = fields.Monetary(
        string='Monto pago agrupado',
        currency_field='currency_id',
    )
    amount_matched = fields.Monetary(
        string='Monto emparejado',
        currency_field='currency_id',
    )
    amount_residual = fields.Monetary(
        string='Diferencia',
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('matched', 'Con contraparte'),
            ('partial', 'Parcial'),
            ('ambiguous', 'Ambiguo'),
            ('unmatched', 'Sin match'),
            ('reconciled', 'Reconciliado contablemente'),
        ],
        string='Estado',
        default='unmatched',
    )
    notes = fields.Text(
        string='Notas',
    )
    match_detail_ids = fields.One2many(
        comodel_name='pos.bank.reconcile.line.match',
        inverse_name='line_id',
        string='Detalle de matches',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='session_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='session_id.currency_id',
        store=True,
        readonly=True,
    )

    def _compute_counts(self):
        for line in self:
            line.pos_payment_count = len(line.pos_payment_ids)
            line.statement_line_count = len(line.statement_line_ids)
            line.reconciled_statement_line_count = len(line.reconciled_statement_line_ids)

            matched = line.env['pos.payment']
            missing = line.env['pos.payment']
            ambiguous = line.env['pos.payment']
            missing_amounts_list = []

            for detail in line.match_detail_ids:
                pos_payment = detail.pos_payment_id
                if detail.state in ('matched', 'manual', 'already_reconciled'):
                    matched |= pos_payment
                elif detail.state == 'ambiguous':
                    ambiguous |= pos_payment
                else:
                    missing |= pos_payment
                    missing_amounts_list.append(line.currency_id.format(abs(pos_payment.amount)))

            # Fallback si no hay match details aun (compatibilidad)
            if not line.match_detail_ids:
                currency = line.currency_id
                tolerance = line.session_id.tolerance or 0.01
                statement_amounts = [
                    currency.round(abs(sl.amount))
                    for sl in line.statement_line_ids | line.reconciled_statement_line_ids
                ]
                for pos_payment in line.pos_payment_ids:
                    pos_amount = currency.round(abs(pos_payment.amount))
                    if any(abs(pos_amount - sa) <= tolerance for sa in statement_amounts):
                        matched |= pos_payment
                    else:
                        missing |= pos_payment
                        missing_amounts_list.append(currency.format(pos_amount))

            line.pos_payment_matched_count = len(matched)
            line.pos_payment_missing_count = len(missing)
            line.pos_payment_ambiguous_count = len(ambiguous)
            line.pos_payment_missing_ids = missing
            line.missing_amounts = ', '.join(missing_amounts_list) if missing_amounts_list else False

    def action_recompute_from_matches(self):
        """Recalcula estado y líneas de extracto desde los match details."""
        for line in self:
            if not line.match_detail_ids:
                continue

            currency = line.currency_id
            tolerance = line.session_id.tolerance or 0.01
            selected_lines = line.env['account.bank.statement.line']
            reconciled_lines = line.env['account.bank.statement.line']
            amount_matched = 0.0
            has_missing = False
            has_ambiguous = False
            missing_amounts_list = []

            for detail in line.match_detail_ids:
                if detail.state == 'already_reconciled' and detail.selected_statement_line_id:
                    reconciled_lines |= detail.selected_statement_line_id
                    amount_matched += currency.round(abs(detail.selected_statement_line_id.amount))
                elif detail.state in ('matched', 'manual') and detail.selected_statement_line_id:
                    selected_lines |= detail.selected_statement_line_id
                    amount_matched += currency.round(abs(detail.selected_statement_line_id.amount))
                elif detail.state == 'ambiguous':
                    has_ambiguous = True
                elif detail.state == 'missing':
                    has_missing = True
                    missing_amounts_list.append(currency.format(abs(detail.pos_payment_id.amount)))

            target_total = currency.round(abs(line.amount_payment))
            residual = currency.round(target_total - amount_matched)

            if has_ambiguous:
                state = 'ambiguous'
                notes = _('Hay pagos POS individuales con múltiples candidatos. Seleccioná la contraparte en el detalle de matches.')
            elif has_missing and not selected_lines and not reconciled_lines:
                state = 'unmatched'
                notes = _('No se encontró contraparte para ningún pago individual.')
            elif has_missing:
                state = 'partial'
                notes = _('Faltan pagos individuales por emparejar. Montos pendientes: %s') % ', '.join(missing_amounts_list)
            elif abs(residual) <= tolerance and residual != 0:
                state = 'partial'
                notes = _('Todos los pagos individuales tienen match, pero hay una diferencia de %s.') % residual
            elif residual == 0:
                state = 'matched'
                notes = _('Todos los pagos individuales tienen contraparte en el extracto.')
            else:
                state = 'partial'
                notes = _('Diferencia no explicada de %s a pesar de emparejar todos los pagos.') % residual

            line.write({
                'statement_line_ids': [(6, 0, selected_lines.ids)],
                'reconciled_statement_line_ids': [(6, 0, reconciled_lines.ids)],
                'amount_matched': amount_matched if line.amount_payment >= 0 else -amount_matched,
                'amount_residual': residual if line.amount_payment >= 0 else -residual,
                'state': state,
                'notes': notes,
            })
        return True

    def action_reset_to_auto(self):
        """Vuelve a ejecutar el matching automático para esta línea."""
        for line in self:
            line.match_detail_ids.unlink()
            result = line.session_id._find_match_for_payment(
                line.payment_id,
                line.env['account.bank.statement.line'].search([
                    ('journal_id', '=', line.session_id.journal_id.id),
                    ('is_reconciled', '=', False),
                    ('date', '>=', line.session_id.date_from),
                    ('date', '<=', line.session_id.date_to),
                ]),
                set(),
                line.currency_id,
            )
            line.write({
                'statement_line_ids': [(6, 0, result['statement_line_ids'])],
                'reconciled_statement_line_ids': [(6, 0, result['reconciled_statement_line_ids'])],
                'amount_matched': result['amount_matched'],
                'amount_residual': result['amount_residual'],
                'state': result['state'],
                'notes': result['notes'],
            })
        return True
