from odoo import models, fields


class AccountOnlineLink(models.Model):
    _inherit = 'account.online.link'

    provider = fields.Selection(
        selection=[],
        string='Bank Provider',
        help='Selection to choose Bank Provider'
    )