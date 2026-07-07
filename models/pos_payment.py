# -*- coding: utf-8 -*-
from odoo import fields, models


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    account_payment_id = fields.Many2one(
        comodel_name='account.payment',
        string='Pago contable agrupado',
        readonly=True,
        copy=False,
        index=True,
        help='Pago contable (account.payment) generado al cerrar la sesión POS '
             'que agrupa este pago individual.',
    )
