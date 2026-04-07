from odoo import api, fields, models


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    acc_number_id = fields.Char(string='Monobank account id', unique=True)