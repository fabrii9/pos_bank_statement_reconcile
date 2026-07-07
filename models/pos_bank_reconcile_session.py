# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosBankReconcileSession(models.Model):
    _name = 'pos.bank.reconcile.session'
    _description = 'Sesión de conciliación bancaria POS'
    _order = 'create_date desc'

    name = fields.Char(
        string='Nombre',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nueva'),
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Diario bancario',
        required=True,
        domain=[('type', '=', 'bank')],
    )
    date_from = fields.Date(
        string='Desde',
        required=True,
        default=lambda self: fields.Date.start_of(fields.Date.today(), 'month'),
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        default=lambda self: fields.Date.end_of(fields.Date.today(), 'month'),
    )
    filter_payment_by_date = fields.Boolean(
        string='Filtrar recibos por fecha',
        default=False,
        help='Si está activo, solo se buscarán recibos agrupados cuya fecha de pago esté dentro del rango indicado.',
    )
    payment_date_from = fields.Date(
        string='Fecha pago desde',
    )
    payment_date_to = fields.Date(
        string='Fecha pago hasta',
    )
    tolerance = fields.Float(
        string='Tolerancia (±)',
        required=True,
        default=0.01,
        help='Diferencia máxima absoluta permitida entre el monto de cada pago POS individual '
             'y el monto de su línea de extracto bancario correspondiente. '
             'Aplica tanto por exceso como por defecto (positiva y negativa).',
    )

    # Configuración de matching
    use_date_match = fields.Boolean(
        string='Usar ventana de fechas',
        default=False,
        help='Si está activo, solo se considerarán líneas de extracto dentro de la ventana de días respecto a la fecha del pago POS.',
    )
    date_tolerance_days = fields.Integer(
        string='Días de tolerancia',
        default=3,
        help='Cantidad de días antes y después de la fecha del pago POS para buscar líneas de extracto.',
    )
    prefer_closest_date = fields.Boolean(
        string='Preferir fecha más cercana',
        default=True,
        help='Entre varias líneas candidatas con el mismo monto, preferir la de fecha más cercana al pago POS.',
    )
    use_reference_match = fields.Boolean(
        string='Usar referencia',
        default=False,
        help='Si está activo, se intentará coincidir por referencia del pago POS o pedido.',
    )
    resolve_globally = fields.Boolean(
        string='Resolver recibo completo',
        default=False,
        help='Resuelve la asignación de líneas de extracto para todo el recibo de forma global, evitando que un pago le robe la contraparte a otro.',
    )
    auto_resolve_ambiguous = fields.Boolean(
        string='Auto-resolver ambigüedades',
        default=False,
        help='Si hay ambigüedades pero existe una combinación única que completa el recibo, se asigna automáticamente.',
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('preview', 'Previsualización'),
            ('done', 'Confirmado'),
            ('error', 'Con errores'),
        ],
        string='Estado',
        default='draft',
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name='pos.bank.reconcile.line',
        inverse_name='session_id',
        string='Pagos POS agrupados',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        related='journal_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda',
        compute='_compute_currency_id',
        readonly=True,
    )
    notes = fields.Text(
        string='Notas',
        readonly=True,
    )

    matched_count = fields.Integer(
        string='Con contraparte',
        compute='_compute_counts',
    )
    partial_count = fields.Integer(
        string='Parciales',
        compute='_compute_counts',
    )
    ambiguous_count = fields.Integer(
        string='Ambiguos',
        compute='_compute_counts',
    )
    unmatched_count = fields.Integer(
        string='Sin match',
        compute='_compute_counts',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nueva')) == _('Nueva'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pos.bank.reconcile.session'
                ) or _('Nueva')
        return super().create(vals_list)

    @api.depends('journal_id.currency_id', 'company_id.currency_id')
    def _compute_currency_id(self):
        for session in self:
            session.currency_id = session.journal_id.currency_id or session.company_id.currency_id

    @api.depends('line_ids.state')
    def _compute_counts(self):
        for session in self:
            lines = session.line_ids
            session.matched_count = len(lines.filtered(lambda l: l.state == 'matched'))
            session.partial_count = len(lines.filtered(lambda l: l.state == 'partial'))
            session.ambiguous_count = len(lines.filtered(lambda l: l.state == 'ambiguous'))
            session.unmatched_count = len(lines.filtered(lambda l: l.state == 'unmatched'))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for session in self:
            if session.date_from and session.date_to and session.date_from > session.date_to:
                raise UserError(_('La fecha "Desde" no puede ser mayor que la fecha "Hasta".'))

    @api.constrains('tolerance')
    def _check_tolerance(self):
        for session in self:
            if session.tolerance < 0:
                raise UserError(_('La tolerancia no puede ser negativa.'))

    @api.constrains('filter_payment_by_date', 'payment_date_from', 'payment_date_to')
    def _check_payment_dates(self):
        for session in self:
            if session.filter_payment_by_date and session.payment_date_from and session.payment_date_to:
                if session.payment_date_from > session.payment_date_to:
                    raise UserError(_('La fecha de pago "Desde" no puede ser mayor que la fecha de pago "Hasta".'))

    @api.onchange('date_from', 'date_to')
    def _onchange_dates(self):
        if not self.filter_payment_by_date:
            self.payment_date_from = self.date_from
            self.payment_date_to = self.date_to

    def _get_currency(self):
        return self.currency_id or self.company_id.currency_id or self.env.company.currency_id

    def action_preview(self):
        self.ensure_one()
        if self.state not in ('draft', 'preview'):
            raise UserError(_('Solo se pueden buscar contrapartes en sesiones en borrador o previsualización.'))

        self.line_ids.unlink()

        payment_domain = [
            ('journal_id', '=', self.journal_id.id),
            ('pos_session_id', '!=', False),
            ('pos_payment_method_id', '!=', False),
            ('pos_payment_ids', '!=', False),
            ('state', '!=', 'cancel'),
        ]
        if self.filter_payment_by_date and self.payment_date_from and self.payment_date_to:
            payment_domain += [
                ('date', '>=', self.payment_date_from),
                ('date', '<=', self.payment_date_to),
            ]
        all_grouped_payments = self.env['account.payment'].search(payment_domain)

        grouped_payments = all_grouped_payments.filtered(lambda p: not p.is_matched)
        skipped_count = len(all_grouped_payments) - len(grouped_payments)

        if not grouped_payments:
            message = _('No se encontraron pagos POS agrupados pendientes de conciliar para este diario.')
            if skipped_count:
                message += _(' Se omitieron %s recibos ya conciliados con extracto.') % skipped_count
            raise UserError(message)

        statement_lines = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', self.journal_id.id),
            ('is_reconciled', '=', False),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ], order='date, amount')

        if not statement_lines:
            raise UserError(_('No se encontraron líneas de extracto no conciliadas en el rango seleccionado.'))

        line_vals = []
        used_statement_line_ids = set()
        currency = self._get_currency()

        for payment in grouped_payments:
            result = self._find_match_for_payment(
                payment,
                statement_lines,
                used_statement_line_ids,
                currency,
            )
            match_detail_vals = []
            for md in result.get('match_details', []):
                match_detail_vals.append((0, 0, {
                    'pos_payment_id': md['pos_payment_id'],
                    'selected_statement_line_id': md.get('selected_statement_line_id'),
                    'candidate_statement_line_ids': [(6, 0, md.get('candidate_statement_line_ids', []))],
                    'state': md['state'],
                    'notes': md.get('notes', ''),
                }))

            line_vals.append((0, 0, {
                'selected': result['selected'],
                'payment_id': payment.id,
                'pos_session_id': payment.pos_session_id.id if payment.pos_session_id else False,
                'pos_payment_method_id': payment.pos_payment_method_id.id if payment.pos_payment_method_id else False,
                'pos_payment_ids': [(6, 0, payment.pos_payment_ids.ids)],
                'statement_line_ids': [(6, 0, result['statement_line_ids'])],
                'reconciled_statement_line_ids': [(6, 0, result['reconciled_statement_line_ids'])],
                'amount_payment': result['amount_payment'],
                'amount_matched': result['amount_matched'],
                'amount_residual': result['amount_residual'],
                'state': result['state'],
                'notes': result['notes'],
                'match_detail_ids': match_detail_vals,
            }))
            used_statement_line_ids.update(result['statement_line_ids'])

        notes = False
        if skipped_count:
            notes = _('Se omitieron %s recibos agrupados ya conciliados con extracto.') % skipped_count

        self.write({
            'state': 'preview',
            'notes': notes,
        })
        self.line_ids = line_vals
        return True

    def _get_candidates_for_pos_payment(self, pos_payment, available, currency):
        """Devuelve las líneas de extracto candidatas para un pago POS individual.

        Aplica filtros por monto, fecha y referencia según la configuración de la sesión.
        """
        pos_amount = currency.round(abs(pos_payment.amount))
        if pos_amount == 0:
            return self.env['account.bank.statement.line']

        candidates = available.filtered(
            lambda l: abs(currency.round(abs(l.amount)) - pos_amount) <= self.tolerance
        )

        if self.use_date_match and pos_payment.payment_date:
            payment_date = pos_payment.payment_date.date()
            candidates = candidates.filtered(
                lambda l: abs((l.date - payment_date).days) <= self.date_tolerance_days
            )

        if self.use_reference_match:
            ref_terms = []
            if pos_payment.pos_order_id and pos_payment.pos_order_id.name:
                ref_terms.append(pos_payment.pos_order_id.name)
            if pos_payment.session_id and pos_payment.session_id.name:
                ref_terms.append(pos_payment.session_id.name)
            if pos_payment.name:
                ref_terms.append(pos_payment.name)
            ref_terms = [term for term in ref_terms if term]
            if ref_terms:
                candidates = candidates.filtered(
                    lambda l: any(
                        term in (l.payment_ref or '') or term in (l.ref or '')
                        for term in ref_terms
                    )
                )

        if self.prefer_closest_date and len(candidates) > 1 and pos_payment.payment_date:
            payment_date = pos_payment.payment_date.date()
            candidates = candidates.sorted(
                key=lambda l: (abs((l.date - payment_date).days), abs(currency.round(abs(l.amount)) - pos_amount))
            )

        return candidates

    def _resolve_assignment(self, pos_payments, available, currency):
        """Resuelve la asignación de líneas de extracto a pagos POS individuales.

        Devuelve un diccionario {pos_payment_id: statement_line_id} con las asignaciones
        definitivas, o False si no puede resolver completamente.
        """
        assignments = {}
        used_ids = set()

        # Primero asignar los pagos con un solo candidato
        pending = []
        for pos_payment in pos_payments:
            candidates = self._get_candidates_for_pos_payment(pos_payment, available, currency)
            free_candidates = candidates.filtered(lambda l: l.id not in used_ids)
            if len(free_candidates) == 1:
                line = free_candidates[0]
                assignments[pos_payment.id] = line.id
                used_ids.add(line.id)
            elif not free_candidates:
                if len(candidates) == 1:
                    # El único candidato ya fue usado por otro pago
                    pass
                pending.append((pos_payment, candidates, False))
            else:
                pending.append((pos_payment, candidates, True))

        # Si no hay ambigüedades pendientes, devolvemos lo que tenemos
        if not any(has_amb for _, _, has_amb in pending):
            return assignments

        if not self.resolve_globally:
            return assignments

        # Resolución simple: asignar por cercanía de fecha sin repetir
        pending_sorted = sorted(
            pending,
            key=lambda item: min(
                abs((c.date - item[0].payment_date.date()).days)
                for c in item[1] if c.id not in used_ids
            ) if item[1] else 9999
        )
        for pos_payment, candidates, _ in pending_sorted:
            free_candidates = candidates.filtered(lambda l: l.id not in used_ids)
            if free_candidates:
                line = free_candidates[0]
                assignments[pos_payment.id] = line.id
                used_ids.add(line.id)

        return assignments

    def _get_already_reconciled_statement_lines(self, payment, currency):
        """Busca líneas de extracto ya reconciliadas con el pago a nivel contable.

        Algunas conciliaciones previas se realizaron directamente sobre
        account.move.line sin poblar payment.reconciled_statement_line_ids.
        Esta función detecta esos casos a través de account.partial.reconcile
        y account.full.reconcile.

        Devuelve un recordset con las líneas de extracto y una lista de montos
        (valor absoluto) de esas líneas.
        """
        statement_line_obj = self.env['account.bank.statement.line']
        if not payment.move_id:
            return statement_line_obj, []

        reconcile_account = payment.outstanding_account_id or payment.destination_account_id
        if not reconcile_account:
            return statement_line_obj, []

        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == reconcile_account
        )
        if not payment_lines:
            return statement_line_obj, []

        reconciled_move_lines = self.env['account.move.line']
        for p_line in payment_lines:
            # Reconciliaciones parciales
            partials = self.env['account.partial.reconcile'].search([
                '|',
                ('debit_move_id', '=', p_line.id),
                ('credit_move_id', '=', p_line.id),
            ])
            for partial in partials:
                other_line = partial.credit_move_id if partial.debit_move_id == p_line else partial.debit_move_id
                reconciled_move_lines |= other_line

            # Reconciliaciones totales
            if p_line.full_reconcile_id:
                for other_line in p_line.full_reconcile_id.reconciled_line_ids:
                    if other_line != p_line:
                        reconciled_move_lines |= other_line

        if not reconciled_move_lines:
            return statement_line_obj, []

        statement_lines = statement_line_obj.search([
            ('move_id', 'in', reconciled_move_lines.move_id.ids),
        ])

        amounts = [
            currency.round(abs(st_line.amount))
            for st_line in statement_lines
            if currency.round(abs(st_line.amount))
        ]
        return statement_lines, amounts

    def _find_match_for_payment(self, payment, statement_lines, used_statement_line_ids, currency):
        """Busca una línea de extracto para cada pago POS individual del recibo agrupado.

        Solo se considera que el recibo agrupado tiene contraparte completa cuando
        **todos** sus pagos POS individuales encontraron una línea de extracto con el
        mismo monto dentro de la tolerancia configurada.

        Se reconocen las líneas de extracto que ya fueron reconciliadas con este pago
        en sesiones anteriores, de modo que se pueda continuar la conciliación del
        saldo residual sin desconciliar lo ya registrado.

        El resultado incluye un listado de match_details para que el usuario pueda
        revisar y corregir asignaciones ambiguas manualmente.
        """
        pos_payments = payment.pos_payment_ids
        if not pos_payments:
            return {
                'selected': False,
                'statement_line_ids': [],
                'reconciled_statement_line_ids': [],
                'amount_payment': payment.amount,
                'amount_matched': 0.0,
                'amount_residual': payment.amount,
                'state': 'unmatched',
                'notes': _('El recibo agrupado no tiene pagos POS individuales vinculados. '
                           'Reconstruí los vínculos desde la sesión POS antes de conciliar.'),
                'match_details': [],
            }

        target_total = currency.round(abs(payment.amount))
        available = statement_lines.filtered(lambda l: l.id not in used_statement_line_ids)

        # ------------------------------------------------------------------
        # 1. Detectar líneas de extracto ya reconciliadas con este pago
        # ------------------------------------------------------------------
        # Usamos la fuente contable de verdad: reconciliaciones parciales y
        # totales de las líneas del pago en la cuenta outstanding/destino.
        # El campo nativo payment.reconciled_statement_line_ids puede no estar
        # poblado o estar incompleto cuando la conciliación se hizo directamente
        # sobre account.move.line.
        already_reconciled_st_lines, reconciled_amounts = self._get_already_reconciled_statement_lines(
            payment, currency
        )

        # El monto ya conciliado es la suma real de las líneas de extracto
        # reconciliadas con el pago, aunque no encontremos un pos.payment
        # individual que explique cada una (puede haber ajustes/comisiones).
        amount_already_reconciled = currency.round(sum(reconciled_amounts))
        reconciled_line_ids = list(dict.fromkeys(already_reconciled_st_lines.ids))
        already_covered_payment_ids = set()

        # Orden determinístico: primero los pagos más antiguos
        sorted_pos_payments = pos_payments.sorted(lambda p: p.id)
        remaining_amounts = list(reconciled_amounts)
        for pos_payment in sorted_pos_payments:
            pos_amount = currency.round(abs(pos_payment.amount))
            for idx, rec_amount in enumerate(remaining_amounts):
                if rec_amount and abs(rec_amount - pos_amount) <= self.tolerance:
                    already_covered_payment_ids.add(pos_payment.id)
                    remaining_amounts[idx] = 0.0
                    break

        # ------------------------------------------------------------------
        # 2. Buscar matches solo para los pagos individuales no cubiertos
        # ------------------------------------------------------------------
        pending_pos_payments = pos_payments.filtered(
            lambda p: p.id not in already_covered_payment_ids
        )

        assignments = {}
        if pending_pos_payments:
            assignments = self._resolve_assignment(pending_pos_payments, available, currency)

        matched_line_ids = []
        match_details = []
        amount_matched = amount_already_reconciled
        missing_payments = []
        ambiguous_payments = []

        for pos_payment in sorted_pos_payments:
            # Pago individual ya conciliado en una sesión anterior
            if pos_payment.id in already_covered_payment_ids:
                selected_st_line = False
                pos_amount = currency.round(abs(pos_payment.amount))
                for st_line in already_reconciled_st_lines:
                    st_amount = currency.round(abs(st_line.amount))
                    if abs(st_amount - pos_amount) <= self.tolerance:
                        selected_st_line = st_line
                        break
                match_details.append({
                    'pos_payment_id': pos_payment.id,
                    'selected_statement_line_id': selected_st_line.id if selected_st_line else False,
                    'candidate_statement_line_ids': [],
                    'state': 'already_reconciled',
                    'notes': _('Este pago ya fue conciliado con una línea de extracto en una sesión anterior.'),
                })
                continue

            pos_amount = currency.round(abs(pos_payment.amount))
            candidates = self._get_candidates_for_pos_payment(pos_payment, available, currency)
            free_candidates = candidates.filtered(
                lambda l: l.id not in matched_line_ids and l.id not in reconciled_line_ids
            )

            if pos_payment.id in assignments and assignments[pos_payment.id] not in matched_line_ids:
                line_id = assignments[pos_payment.id]
                line = available.filtered(lambda l: l.id == line_id)
                matched_line_ids.append(line_id)
                amount_matched += currency.round(abs(line.amount))
                match_details.append({
                    'pos_payment_id': pos_payment.id,
                    'selected_statement_line_id': line_id,
                    'candidate_statement_line_ids': free_candidates.ids,
                    'state': 'matched',
                    'notes': '',
                })
            elif len(free_candidates) == 1:
                line = free_candidates[0]
                matched_line_ids.append(line.id)
                amount_matched += currency.round(abs(line.amount))
                match_details.append({
                    'pos_payment_id': pos_payment.id,
                    'selected_statement_line_id': line.id,
                    'candidate_statement_line_ids': free_candidates.ids,
                    'state': 'matched',
                    'notes': '',
                })
            elif free_candidates:
                ambiguous_payments.append(pos_payment)
                match_details.append({
                    'pos_payment_id': pos_payment.id,
                    'selected_statement_line_id': False,
                    'candidate_statement_line_ids': free_candidates.ids,
                    'state': 'ambiguous',
                    'notes': _('Múltiples contrapartes posibles'),
                })
            else:
                missing_payments.append(pos_payment)
                match_details.append({
                    'pos_payment_id': pos_payment.id,
                    'selected_statement_line_id': False,
                    'candidate_statement_line_ids': candidates.ids,
                    'state': 'missing',
                    'notes': _('No se encontró línea de extracto disponible'),
                })

        # Auto-resolución de ambigüedades si está activada y ayuda a completar
        auto_resolved_ids = []
        if self.auto_resolve_ambiguous and ambiguous_payments:
            for pos_payment in ambiguous_payments:
                detail = next((md for md in match_details if md['pos_payment_id'] == pos_payment.id), None)
                if not detail:
                    continue
                for cid in detail['candidate_statement_line_ids']:
                    if cid in matched_line_ids or cid in auto_resolved_ids or cid in reconciled_line_ids:
                        continue
                    line = available.filtered(lambda l: l.id == cid)
                    if line:
                        auto_resolved_ids.append(cid)
                        detail['selected_statement_line_id'] = cid
                        detail['state'] = 'matched'
                        amount_matched += currency.round(abs(line.amount))
                        break
                if detail['state'] == 'ambiguous':
                    detail['notes'] = _('Múltiples contrapartes posibles')
            matched_line_ids.extend(auto_resolved_ids)
            ambiguous_payments = [
                pp for pp in ambiguous_payments
                if next((md for md in match_details if md['pos_payment_id'] == pp.id), {}).get('state') == 'ambiguous'
            ]

        is_negative = payment.amount < 0
        amount_matched_signed = -amount_matched if is_negative else amount_matched
        residual = currency.round(target_total - amount_matched)
        residual_signed = -residual if is_negative else residual

        missing_amounts_str = ', '.join(
            currency.format(currency.round(abs(pp.amount))) for pp in missing_payments
        )

        already_reconciled_count = len(already_covered_payment_ids)

        if already_reconciled_count and not matched_line_ids and not missing_payments and not ambiguous_payments:
            state = 'matched' if residual == 0 else 'partial'
            notes = _('El recibo ya tiene %s pago(s) conciliado(s) en sesiones anteriores por un total de %s.') % (
                already_reconciled_count, currency.format(amount_already_reconciled)
            )
            if residual != 0:
                notes += ' ' + _('Falta conciliar %s.') % currency.format(residual)
            else:
                notes += ' ' + _('No queda saldo pendiente.')
        elif missing_payments and not matched_line_ids and not already_reconciled_count:
            state = 'unmatched'
            notes = _('No se encontró contraparte para ningún pago individual (%s pagos). Faltan montos: %s') % (
                len(pos_payments), missing_amounts_str
            )
        elif missing_payments:
            state = 'partial'
            notes = _('Faltan %s de %s pagos individuales por emparejar. Montos pendientes: %s') % (
                len(missing_payments), len(pos_payments), missing_amounts_str
            )
            if already_reconciled_count:
                notes += ' ' + _('(Ya conciliados previamente: %s)') % currency.format(amount_already_reconciled)
        elif ambiguous_payments:
            state = 'ambiguous'
            notes = _('Hay %s pago(s) individual(es) con múltiples contrapartes posibles en el extracto.') % (
                len(ambiguous_payments)
            )
        elif abs(residual) <= self.tolerance and residual != 0:
            state = 'partial'
            notes = _('Todos los pagos individuales tienen match, pero hay una diferencia de %s.') % residual
        elif residual == 0:
            state = 'matched'
            notes = _('Todos los pagos individuales (%s) tienen contraparte en el extracto.') % len(pos_payments)
        else:
            state = 'partial'
            notes = _('Diferencia no explicada de %s a pesar de emparejar todos los pagos.') % residual

        # Solo se preselecciona para confirmar si hay líneas de extracto nuevas
        # por reconciliar en esta sesión. Las líneas completamente reconciliadas
        # previamente no deben generar un intento de confirmación vacío.
        return {
            'selected': state == 'matched' and bool(matched_line_ids),
            'statement_line_ids': matched_line_ids,
            'reconciled_statement_line_ids': reconciled_line_ids,
            'amount_payment': payment.amount,
            'amount_matched': amount_matched_signed,
            'amount_residual': residual_signed,
            'state': state,
            'notes': notes,
            'match_details': match_details,
        }

    def action_confirm(self):
        for session in self:
            if session.state not in ('draft', 'preview'):
                raise UserError(_('Solo se pueden confirmar sesiones en borrador o previsualización.'))

            selected_lines = session.line_ids.filtered(lambda l: l.selected and l.state == 'matched')
            if not selected_lines:
                raise UserError(_('No hay líneas seleccionadas para conciliar. Solo se pueden confirmar líneas en estado "Con contraparte" (matched).'))

            errors = []
            for line in selected_lines:
                try:
                    session._reconcile_line(line)
                except Exception as e:
                    payment_ref = line.payment_id.display_name or line.payment_id.id
                    errors.append(_('Pago %s: %s') % (payment_ref, str(e)))
                    _logger.exception('Error conciliando pago agrupado %s', line.payment_id.id)

            if errors:
                session.write({
                    'state': 'error',
                    'notes': '\n'.join(errors),
                })
            else:
                session.write({'state': 'done'})

        return True

    def _reconcile_line(self, line):
        """Ejecuta la conciliación contable para un pago agrupado."""
        payment = line.payment_id
        # Solo reconciliar líneas de extracto que aún no estén reconciliadas.
        # Las líneas ya reconciliadas en sesiones anteriores se mantienen intactas.
        st_lines = line.statement_line_ids.filtered(lambda l: not l.is_reconciled)
        pos_payments = line.pos_payment_ids

        if not payment:
            raise UserError(_('Faltan datos para conciliar el pago.'))

        if not st_lines:
            raise UserError(_(
                'Todas las líneas de extracto asignadas al recibo %s ya están reconciliadas. '
                'No queda saldo pendiente por conciliar en esta sesión.'
            ) % payment.display_name)

        if payment.is_matched:
            raise UserError(_(
                'El pago agrupado %s ya fue conciliado con una línea de extracto. '
                'No se puede conciliar dos veces.'
            ) % payment.display_name)

        already_reconciled = self.env['pos.bank.reconcile.line'].search([
            ('statement_line_ids', 'in', st_lines.ids),
            ('state', '=', 'reconciled'),
            ('id', '!=', line.id),
        ], limit=1)
        if already_reconciled:
            raise UserError(_(
                'Alguna de las líneas de extracto seleccionadas ya fue conciliada en la sesión %s.'
            ) % already_reconciled.session_id.name)

        st_moves = st_lines.move_id
        payment_move = payment.move_id
        if not st_moves or not payment_move:
            raise UserError(_('El pago o las líneas de extracto no tienen asiento contable.'))

        reconcile_account = payment.outstanding_account_id or payment.destination_account_id
        if not reconcile_account:
            raise UserError(_('El pago agrupado no tiene cuenta contable destino definida.'))

        st_line_accounts = st_moves.line_ids.filtered(
            lambda l: l.account_id == reconcile_account and not l.reconciled
        )
        payment_line_accounts = payment_move.line_ids.filtered(
            lambda l: l.account_id == reconcile_account and not l.reconciled
        )

        # Fallback: si no se encuentran líneas en la cuenta esperada, buscar por
        # monto pero siempre asegurando que extracto y pago compartan la misma
        # cuenta. Nunca se mezclan líneas de cuentas distintas.
        if not st_line_accounts or not payment_line_accounts:
            st_candidates = st_moves.line_ids.filtered(
                lambda l: not l.reconciled and abs(l.balance - payment.amount) <= self.tolerance
            )
            payment_candidates = payment_move.line_ids.filtered(
                lambda l: not l.reconciled and abs(l.balance - payment.amount) <= self.tolerance
            )

            # Buscar una cuenta común entre candidatos del extracto y del pago.
            st_accounts = set(st_candidates.mapped('account_id.id'))
            payment_accounts = set(payment_candidates.mapped('account_id.id'))
            common_accounts = st_accounts & payment_accounts

            if not common_accounts:
                raise UserError(_(
                    'No se encontraron líneas contables compatibles para conciliar. '
                    'Cuenta esperada: %(account)s. '
                    'Cuentas del extracto: %(st_accounts)s. '
                    'Cuentas del pago: %(payment_accounts)s. '
                    'Verificá que la cuenta puente del método de pago POS coincida con '
                    'la cuenta suspense del diario bancario.',
                    account=reconcile_account.code,
                    st_accounts=', '.join(sorted(st_candidates.mapped('account_id.code'))) or _('ninguna'),
                    payment_accounts=', '.join(sorted(payment_candidates.mapped('account_id.code'))) or _('ninguna'),
                ))

            # Preferir la cuenta esperada si está entre las comunes; si no, usar
            # la primera cuenta común (generalmente la del pago POS).
            common_account_id = next(
                (aid for aid in common_accounts if aid == reconcile_account.id),
                next(iter(common_accounts))
            )
            common_account = self.env['account.account'].browse(common_account_id)

            st_line_accounts = st_candidates.filtered(lambda l: l.account_id.id == common_account_id)
            payment_line_accounts = payment_candidates.filtered(lambda l: l.account_id.id == common_account_id)

            _logger.info(
                'Conciliación fallback para pago %s: usando cuenta %s en lugar de %s',
                payment.id, common_account.code, reconcile_account.code
            )

        if not st_line_accounts or not payment_line_accounts:
            raise UserError(_(
                'No se encontraron líneas contables compatibles para conciliar. '
                'Verificá que la cuenta puente del método de pago POS coincida con '
                'la cuenta suspense del diario bancario.'
            ))

        # Validación final: todas las líneas deben pertenecer a la misma cuenta.
        all_accounts = set((st_line_accounts + payment_line_accounts).mapped('account_id.id'))
        if len(all_accounts) > 1:
            account_names = ', '.join(
                sorted((st_line_accounts + payment_line_accounts).mapped('account_id.code'))
            )
            raise UserError(_(
                'Las líneas seleccionadas pertenecen a cuentas contables distintas (%s). '
                'No se pueden conciliar juntas. Revisá las líneas de extracto seleccionadas.',
                account_names
            ))

        (st_line_accounts + payment_line_accounts).reconcile()

        # Forzar la relación nativa entre el pago y las líneas de extracto para
        # que futuras sesiones puedan detectar rápidamente las conciliaciones.
        try:
            current_reconciled = payment.reconciled_statement_line_ids
            new_st_lines = st_lines.filtered(lambda l: l.id not in current_reconciled.ids)
            if new_st_lines:
                payment.reconciled_statement_line_ids = [(4, st_line.id) for st_line in new_st_lines]
        except Exception:
            _logger.warning(
                'No se pudo actualizar reconciled_statement_line_ids del pago %s',
                payment.id, exc_info=True
            )

        line.write({
            'state': 'reconciled',
            'notes': line.notes or _('Conciliado correctamente.'),
        })

    def action_refresh_preview(self):
        """Vuelve a ejecutar la búsqueda de contrapartes manteniendo la configuración actual."""
        self.ensure_one()
        if self.state not in ('draft', 'preview'):
            raise UserError(_('Solo se puede actualizar en borrador o previsualización.'))
        self.line_ids.unlink()
        return self.action_preview()

    def action_reset_to_draft(self):
        for session in self:
            if session.state == 'done':
                raise UserError(_('No se puede volver a borrador una sesión ya confirmada.'))
            session.line_ids.unlink()
            session.write({'state': 'draft', 'notes': False})
        return True
