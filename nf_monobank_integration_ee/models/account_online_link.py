import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import requests
import logging

BANK_API_GET_STATEMENTS = 'personal/statement'
BANK_API_GET_CLIENT_INFO = 'personal/client-info'
BANK_STATEMENTS_MIN = 0
GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again later. " \
                        "If problem persists - please contact your system administrator."


_logger = logging.getLogger('Monobank Integration')

def logging_formatter(user_id=None, user_name=None):
    if user_id and user_name:
        return f"User: [{user_id}, {user_name}] - "
    return 'No user detected - '


class OnlineSyncMonobank(models.Model):
    _inherit = "account.online.link"
    monobank_token = fields.Char(string='Monobank token')
    provider = fields.Selection(selection_add=[('monobank', 'Monobank'),])

    def _pre_check_fetch_transactions(self):
        """
        Overrided this method to check if connection is established properly for Monobank API integration.
        & skip redundant proxy requests
        """
        self.ensure_one()
        if self.provider == 'monobank':
            return bool(self.account_online_account_ids.filtered('journal_ids'))
        return super()._pre_check_fetch_transactions()

    def _open_iframe(self, mode='link'):
        """
        Overridden parent method to display an informative notification if needed
        """
        if self.provider == 'monobank':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _("Monobank uses direct token. Configure and fetch via the Monobank wizard."),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        return super()._open_iframe(mode)

    def action_fetch_transactions(self):
        if self.provider == "monobank":
            self.account_online_account_ids.fetching_status = None
            self.with_context(cron=True)._fetch_transactions(refresh=True)
            return {"type": "ir.actions.client", "tag": "reload"}
        return super().action_fetch_transactions()

    # helpers

    def _read_config_values(self, key_name):
        param_value = self.env['ir.config_parameter'].sudo().get_param(key_name, None)
        if param_value:
            return param_value
        raise UserError(f"Make sure value for system parameter {key_name} is present in Settings")

    ##############
    # Monobank #
    ##############

    def get_client_information(self):
        try:
            url = f"{self._read_config_values('monobank_endpoint')}{BANK_API_GET_CLIENT_INFO}"
            header_params = {
                "X-Token": self.monobank_token
            }
            response = requests.get(url, headers=header_params, timeout=30)
            response_data = response.json()
            _logger.debug(f"response body: {response_data}")
        except ValueError as err:
            _logger.error(f"Failed to parse response body: {err}")
            return False
        if response.status_code == requests.codes.OK and not response_data.get('errorMessage'):
            bank = self.env['res.bank'].sudo().search([('name', '=', 'Monobank')], limit=1)
            if not bank:
                bank = self.env['res.bank'].sudo().create({'name': 'Monobank'})
            bank_accounts = self.env['res.partner.bank'].sudo()
            online_account_model = self.env['account.online.account'].sudo()
            for account in response_data.get('accounts', []):
                iban = account.get('iban')
                acc_id = account.get('id')
                currency = self.env['res.currency'].with_context(active_test=False).search([
                    ('numeric_code', '=', account.get('currencyCode'))
                ], limit=1)
                if not currency:
                    continue
                partner_bank = bank_accounts.search([
                    ('sanitized_acc_number', '=', iban),
                    ('partner_id', '=', self.company_id.partner_id.id),
                ], limit=1)
                vals_bank = {
                    'acc_holder_name': response_data.get('name'),
                    'bank_id': bank.id,
                    'currency_id': currency.id,
                    'partner_id': self.company_id.partner_id.id,
                    'acc_number_id': acc_id,
                }
                if partner_bank:
                    partner_bank.write(vals_bank)
                else:
                    vals_bank['acc_number'] = iban
                    partner_bank = bank_accounts.create(vals_bank)

                existing_online_account = online_account_model.search([
                    ('online_identifier', '=', acc_id),
                    ('account_online_link_id', '=', self.id),
                ], limit=1)

                if not existing_online_account:
                    online_account = online_account_model.create({
                        'name': account['iban'] or response_data['name'],
                        'online_identifier': account['id'],
                        'account_number': account['iban'],
                        'currency_id': currency.id,
                        'account_online_link_id': self.id,
                        'balance': account.get('balance', 0) / 100,
                    })
                    online_account._assign_journal()
                else:
                    existing_online_account._assign_journal()
                    online_account = existing_online_account

            self.write({
                'state': 'connected',
                'provider_data': json.dumps({'provider': 'monobank', 'v': 1})
            })

        return response_data
