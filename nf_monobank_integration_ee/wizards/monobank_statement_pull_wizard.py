from odoo import models, fields, api, _

from datetime import datetime


class MonobankStatementPullWizard(models.TransientModel):
    _name = 'monobank.statement.pull.wizard'
    _description = 'Monobank Statement Pull Wizard'

    account_id = fields.Many2one('account.online.account',
                                 domain="[('account_online_link_id.provider', '=', 'monobank')]")
    date_from = fields.Date(string='From', required=True, default=fields.Date.today)
    date_to = fields.Date(string='To', required=True, default=fields.Date.today)

    def action_sync(self):
        self.ensure_one()
        ctx = dict(self.env.context or {})
        ctx.update({
            'monobank_date_from': self.date_from,
            'monobank_date_to': self.date_to,
        })
        link = self.account_id.account_online_link_id
        account_ctx = self.account_id.with_context(ctx)
        action = link.with_context(ctx)._fetch_transactions(
            refresh=False,
            accounts=account_ctx,
        )
        return action or self.env['ir.actions.act_window']._for_xml_id(
            'account.open_account_journal_dashboard_kanban'
        )