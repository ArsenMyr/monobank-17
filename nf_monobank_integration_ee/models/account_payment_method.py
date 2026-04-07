# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountPaymentMethod(models.Model):
    _inherit = "account.payment.method"

    @api.model
    def _get_payment_method_information(self):
        """
        override the default method to add monobank online
        """
        res = super()._get_payment_method_information()
        res |= {
            'monobank_online': {'mode': 'multi', 'domain': [('type', 'in', ('bank',))]}
        }
        return res
