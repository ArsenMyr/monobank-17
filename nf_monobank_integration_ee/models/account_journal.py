# -*- coding: utf-8 -*-

from odoo import api, models, fields, _


class AccountJournal(models.Model):
    _inherit = "account.journal"

    has_monobank_online_payments_method = fields.Boolean(compute="_compute_has_monobank_online_payments_method")

    @api.depends('outbound_payment_method_line_ids.payment_method_id.code')
    def _compute_has_monobank_online_payments_method(self):
        """
        method to check whether monobank online payments can be added to dedicated journal (based on Bank feeds)
        """
        for rec in self:
            rec.has_monobank_online_payments_method = any(
                payment_method.payment_method_id.code == 'monobank_online'
                for payment_method in rec.outbound_payment_method_line_ids
            )

    def action_monobank_open_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Monobank Transactions'),
            'res_model': 'monobank.statement.pull.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_account_id': self.account_online_account_id.id,
            }
        }
