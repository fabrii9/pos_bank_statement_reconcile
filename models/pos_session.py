# -*- coding: utf-8 -*-
from odoo import models, _


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _create_combine_account_payment(self, payment_method, amounts, diff_amount):
        """Crea el pago agrupado y vincula los pos.payment individuales."""
        res = super()._create_combine_account_payment(payment_method, amounts, diff_amount)
        # Un solo pago agrupado por sesión/método: no hay ambigüedad posible.
        account_payment = self._resolve_account_payment(res, payment_method)
        if account_payment:
            pos_payments = self.env['pos.payment'].search([
                ('session_id', '=', self.id),
                ('payment_method_id', '=', payment_method.id),
                ('payment_method_id.split_transactions', '=', False),
            ])
            if pos_payments:
                pos_payments.write({'account_payment_id': account_payment.id})
        return res

    def _resolve_account_payment(self, res, payment_method, amount=None):
        """Obtiene el account.payment recién creado por el método nativo.

        El método padre devuelve las líneas contables del pago, así que el
        camino confiable es subir del move a su payment. La búsqueda por
        (sesión, método, monto) queda solo como último recurso: con dos pagos
        del mismo monto en la misma sesión devuelve siempre el mismo registro
        y dejaría un pos.payment mal vinculado.
        """
        account_payment = self.env['account.payment']

        # res suele ser un account.move.line del asiento del pago.
        if res is not None and hasattr(res, '_name'):
            if 'payment_id' in res._fields:
                account_payment = res.payment_id
            if not account_payment and 'move_id' in res._fields:
                move = res.move_id
                if 'payment_id' in move._fields:
                    account_payment = move.payment_id

        if account_payment:
            return account_payment[:1]

        domain = [
            ('pos_session_id', '=', self.id),
            ('pos_payment_method_id', '=', payment_method.id),
        ]
        if amount is not None:
            domain.append(('amount', '=', abs(amount)))
        return self.env['account.payment'].search(domain, limit=1, order='id desc')

    def _create_split_account_payment(self, payment, amounts):
        """Crea el pago individual y vincula el pos.payment."""
        res = super()._create_split_account_payment(payment, amounts)
        account_payment = self._resolve_account_payment(
            res, payment.payment_method_id, amounts.get('amount')
        )
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
                    # Método split: un account.payment por cada pos.payment.
                    # Emparejamos por monto, pero solo sobre los pos.payment que
                    # todavía no tienen vínculo, para no pisar uno ya asignado
                    # cuando hay varios pagos del mismo importe en la sesión.
                    payment_amount = payment.currency_id.round(abs(payment.amount))
                    candidates = pos_payments.filtered(
                        lambda p: not p.account_payment_id
                        and abs(payment.currency_id.round(abs(p.amount)) - payment_amount) < 0.01
                    )
                    if candidates:
                        candidates[0].write({'account_payment_id': payment.id})
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
