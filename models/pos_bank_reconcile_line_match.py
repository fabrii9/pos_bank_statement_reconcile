# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PosBankReconcileLineMatch(models.Model):
    _name = 'pos.bank.reconcile.line.match'
    _description = 'Detalle de match de conciliación POS'
    _order = 'line_id, pos_payment_id'

    line_id = fields.Many2one(
        comodel_name='pos.bank.reconcile.line',
        string='Línea de conciliación',
        required=True,
        ondelete='cascade',
    )
    session_id = fields.Many2one(
        comodel_name='pos.bank.reconcile.session',
        related='line_id.session_id',
        store=True,
        readonly=True,
    )
    pos_payment_id = fields.Many2one(
        comodel_name='pos.payment',
        string='Pago POS individual',
        required=True,
    )
    pos_order_id = fields.Many2one(
        comodel_name='pos.order',
        related='pos_payment_id.pos_order_id',
        string='Pedido POS',
    )
    payment_date = fields.Datetime(
        related='pos_payment_id.payment_date',
        string='Fecha pago',
    )
    payment_amount = fields.Monetary(
        string='Monto pago',
        currency_field='currency_id',
        compute='_compute_payment_amount',
    )
    selected_statement_line_id = fields.Many2one(
        comodel_name='account.bank.statement.line',
        string='Línea de extracto seleccionada',
        domain="[('id', 'in', candidate_statement_line_ids)]",
    )
    candidate_statement_line_ids = fields.Many2many(
        comodel_name='account.bank.statement.line',
        string='Líneas de extracto candidatas',
    )
    state = fields.Selection(
        selection=[
            ('matched', 'Emparejado'),
            ('ambiguous', 'Ambiguo'),
            ('missing', 'Sin match'),
            ('manual', 'Manual'),
        ],
        string='Estado',
        default='missing',
    )
    notes = fields.Char(
        string='Nota',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='line_id.currency_id',
        store=True,
        readonly=True,
    )

    @api.depends('pos_payment_id', 'pos_payment_id.amount')
    def _compute_payment_amount(self):
        for match in self:
            match.payment_amount = match.pos_payment_id.amount

    @api.onchange('selected_statement_line_id')
    def _onchange_selected_statement_line_id(self):
        for match in self:
            if match.selected_statement_line_id:
                match.state = 'manual'

    def action_use_candidate(self, statement_line_id):
        """Selecciona una línea candidata como definitiva."""
        self.ensure_one()
        line = self.env['account.bank.statement.line'].browse(statement_line_id)
        if line and line in self.candidate_statement_line_ids:
            self.selected_statement_line_id = line
            self.state = 'manual'
        return True

    def action_clear_selection(self):
        """Limpia la selección manual."""
        self.ensure_one()
        self.selected_statement_line_id = False
        if self.candidate_statement_line_ids:
            self.state = 'ambiguous'
        else:
            self.state = 'missing'
        return True
