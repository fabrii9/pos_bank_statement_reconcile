# -*- coding: utf-8 -*-
from odoo import models, _


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _create_combine_account_payment(self, payment_method, amounts, diff_amount):
        """Crea el pago agrupado y vincula los pos.payment individuales."""
        res = super()._create_combine_account_payment(payment_method, amounts, diff_amount)
        # El método padre devuelve un account.move.line; el account.payment
        # creado se identifica por sesión + método de pago POS.
        account_payment = self.env['account.payment'].search([
            ('pos_session_id', '=', self.id),
            ('pos_payment_method_id', '=', payment_method.id),
        ], limit=1, order='id desc')
        if account_payment:
            pos_payments = self.env['pos.payment'].search([
                ('session_id', '=', self.id),
                ('payment_method_id', '=', payment_method.id),
                ('payment_method_id.split_transactions', '=', False),
            ])
            if pos_payments:
                pos_payments.write({'account_payment_id': account_payment.id})
        return res

    def _create_split_account_payment(self, payment, amounts):
        """Crea el pago individual y vincula el pos.payment."""
        res = super()._create_split_account_payment(payment, amounts)
        # El método padre devuelve un account.move.line; buscamos el payment
        # recién creado por sesión + método + monto.
        account_payment = self.env['account.payment'].search([
            ('pos_session_id', '=', self.id),
            ('pos_payment_method_id', '=', payment.payment_method_id.id),
            ('amount', '=', abs(amounts['amount'])),
        ], limit=1, order='id desc')
        if account_payment:
            payment.write({'account_payment_id': account_payment.id})
        return res

    def action_rebuild_pos_payment_links(self):
        """Reconstruye los vínculos entre pos.payment y account.payment.

        Útil para sesiones cerradas antes de instalar el módulo.
        """
        linked_count = 0
        for session in self:
            account_payments = self.env['account.payment'].search([
                ('pos_session_id', '=', session.id),
            ], order='id asc')

            for payment in account_payments:
                method = payment.pos_payment_method_id
                if not method:
                    continue

                # Pagos POS de esta sesión/método que aún no tienen vínculo.
                domain = [
                    ('session_id', '=', session.id),
                    ('payment_method_id', '=', method.id),
                    '|', ('account_payment_id', '=', False), ('account_payment_id', '=', payment.id),
                ]
                pos_payments = self.env['pos.payment'].search(domain, order='id asc')
                if not pos_payments:
                    continue

                if method.split_transactions:
                    # Método split: intentar emparejar por monto.
                    payment_amount = currency_rounded = payment.currency_id.round(abs(payment.amount))
                    candidates = pos_payments.filtered(
                        lambda p: abs(payment.currency_id.round(abs(p.amount)) - payment_amount) < 0.01
                    )
                    if candidates:
                        # En caso de múltiples candidatos con el mismo monto, tomar solo uno.
                        candidate = candidates[0]
                        if not candidate.account_payment_id:
                            candidate.write({'account_payment_id': payment.id})
                            linked_count += 1
                else:
                    # Método combinado: todos los pos.payment del método pertenecen a este recibo.
                    to_link = pos_payments.filtered(lambda p: not p.account_payment_id)
                    if to_link:
                        to_link.write({'account_payment_id': payment.id})
                        linked_count += len(to_link)

        if len(self) == 1:
            return {'type': 'ir.actions.act_window_close'}

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Vínculos reconstruidos'),
                'message': _('%s pagos POS fueron vinculados con sus pagos contables.') % linked_count,
                'type': 'success',
                'sticky': False,
            }
        }
