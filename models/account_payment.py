# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    pos_payment_ids = fields.One2many(
        comodel_name='pos.payment',
        inverse_name='account_payment_id',
        string='Pagos POS individuales',
        readonly=True,
        help='Pagos individuales del POS que fueron agrupados en este pago contable.',
    )
    pos_payment_count = fields.Integer(
        string='Cantidad de pagos POS',
        compute='_compute_pos_payment_count',
    )

    def _compute_pos_payment_count(self):
        for payment in self:
            payment.pos_payment_count = len(payment.pos_payment_ids)
