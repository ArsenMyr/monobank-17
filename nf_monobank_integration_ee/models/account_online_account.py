import json
import logging
import math
from zoneinfo import ZoneInfo
from datetime import datetime, date, time as dtime, timedelta
import requests
from odoo.exceptions import UserError

from odoo import api, fields, models, _

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


class AccountOnlineAccountMonobank(models.Model):
    _inherit = 'account.online.account'

    def _retrieve_transactions(self, date=None, include_pendings=False):
        if self.account_online_link_id.provider == 'monobank':
            ctx = self.env.context or {}
            ctx_from = ctx.get('monobank_date_from')
            ctx_to = ctx.get('monobank_date_to')

            if ctx.get('cron') or not (ctx_from and ctx_to):
                date_since = date or self.last_sync or fields.Date.today()
                date_until = fields.Date.today()
            else:
                date_since = ctx_from
                date_until = ctx_to

            transactions, metadata = self._monobank_obtain_statement_data(date_since, date_until)
            self.balance = metadata.get('balance', self.balance)
            return {'transactions': transactions, 'pendings': []}
        return super()._retrieve_transactions(date, include_pendings)

    def _monobank_obtain_transactions(self, date_since, date_until):
        self.ensure_one()
        if date_since and date_until:
            date_since, date_until = self._to_unix_ms(date_since), self._to_unix_ms(date_until)
            _logger.debug(f"After formatting. date since: {date_since}, date until: {date_until}")
        else:
            raise UserError("Please fill in Date from and Date To")
        transactions = []
        current_page = 1
        try:
            max_value = self.account_online_link_id._read_config_values('monobank_max_statements')
            MAX_STATEMENTS_VALUE = int(max_value)
        except ValueError:
            raise UserError(f"System parameter 'monobank_max_statements' should be integer, "
                            f"{type(max_value).__name__} provided instead")
        step = MAX_STATEMENTS_VALUE - BANK_STATEMENTS_MIN
        total_pages, max_result = 1, None
        first_result, max_result = BANK_STATEMENTS_MIN, MAX_STATEMENTS_VALUE
        while current_page <= total_pages:
            bank_response, first_result = self._monobank_get_transactions(
                f"{self.account_online_link_id._read_config_values('monobank_endpoint')}"
                f"{BANK_API_GET_STATEMENTS}",
                date_since,
                date_until
            )

            if isinstance(bank_response, dict):
                transactions = bank_response
            else:
                transactions.extend(bank_response.json())
            max_result = first_result + step
            if not max_result:
                max_result = bank_response.get("total", None)
                total_pages = math.ceil(max_result / step)
            current_page += 1
        return transactions

    def _monobank_get_transactions(self, url, date_since, date_until):
        user_id, user_name = self.__get_user_for_logging()
        _logger.debug(f" concat acc number -> {self.account_number}_{self.currency_id.name}")
        if not self.currency_id:
            raise UserError("Currency is not specified.")
        body = {
            'accounts': f"{self.online_identifier}",
            'dateFrom': date_since,
            'dateTo': date_until,
        }
        try:
            header_params = {
                "X-Token": self.account_online_link_id.monobank_token,
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        except ValueError as err:
            _logger.error(err)
            raise UserError(
                f"Can't use RSA key without passphrase. Please make sure you entered one in Configuration ->"
                f" Online Bank Statement Providers -> {self.name}")

        url = f'{url}/{self.online_identifier}/{date_since}'
        if date_until:
            url += f'/{date_until}'
        bank_response = requests.get(url,
                                     data=json.dumps(body),
                                     headers=header_params)
        _logger.debug(f"Request: {bank_response.request.url}\n"
                      f"{bank_response.request.headers}\n"
                      f"{bank_response.request.body}")
        _logger.debug(f"response: {bank_response.status_code}")
        if bank_response.status_code == requests.codes.OK:
            _logger.debug(bank_response.text)
            _logger.info(f"{logging_formatter(user_id, user_name)}"
                         f"Bank statements successfully received.")
        elif bank_response.status_code == requests.codes.UNAUTHORIZED:
            message = "Access token has expired. Please get new pair of tokens from Configuration -> " \
                      f"Online Bank Statement Providers -> '{self.name}' -> New token." \
                      f"Or try to Connect again"
            _logger.info(f"{logging_formatter(user_id, user_name)}{message.split('. ')[0]}")
            self.message_post(subject="Get transaction", body=message)
        elif bank_response.status_code in (requests.codes.BAD_REQUEST,
                                           requests.codes.FORBIDDEN):
            _logger.error(f"{logging_formatter(user_id, user_name)}"
                          f"{bank_response.status_code}: {bank_response.json().get('errorMessage')}.")
            raise UserError(bank_response.json().get('errorMessage'))
        elif bank_response.status_code == 429:
            return {}, 0
        return bank_response, len(bank_response.json())

    def _monobank_prepare_statement_line(self, transaction, sequence, journal_currency, currencies_code2id, journal):
        unix_time_seconds = int(transaction["time"])
        payment_date = datetime.utcfromtimestamp(unix_time_seconds).date()  # Конвертуємо в date
        amount = (transaction.get("amount", 0) + transaction.get("commissionRate", 0)) / 100
        payment_purpose = ' '.join(
            [val for val in (transaction.get("counterName"), transaction.get("description")) if val])
        res_bank = self.journal_ids.mapped('bank_id')
        res_bank = res_bank[0] if res_bank else False
        correspondent_ref = self._partner_for_bank_statement_line(
            transaction.get("counterName"),
            transaction.get("counterEdrpou"),
            transaction.get("counterIban"),
            journal_currency, res_bank
        )

        vals_line = {
            'id': transaction.get("id"),
            'date': payment_date,
            'amount': amount,
            'unique_import_id': transaction.get("id"),
            'payment_ref': payment_purpose,
            'account_number': transaction.get("counterIban") or self.journal_ids.bank_acc_number,
            'partner_id': correspondent_ref.id if correspondent_ref else False,
            'online_transaction_identifier': transaction.get("id"),
            'journal_id': journal.id,
        }
        return vals_line

    def _monobank_obtain_statement_data(self, date_since, date_until):
        self.ensure_one()
        journal = self.journal_ids
        transactions = self._monobank_obtain_transactions(date_since, date_until)
        journal_currency = journal.currency_id or journal.company_id.currency_id
        all_currencies = self.env["res.currency"].search_read(
            [('active', '=', True)],
            ["numeric_code"]
        )
        currencies_code2id = {x["numeric_code"]: x["id"] for x in all_currencies}
        new_transactions = []
        sequence = 0
        for transaction in transactions:
            sequence += 1
            vals_line = self._monobank_prepare_statement_line(
                transaction, sequence, journal_currency, currencies_code2id, journal
            )
            new_transactions.append(vals_line)

        return new_transactions, {}

    def _to_unix_ms(self, value):
        """
        Приймає datetime/date/int/float/str і повертає unix time у мс (UTC).
        """
        if value is None:
            raise UserError("Date value is not set")

        if isinstance(value, (int, float)):
            return int(value * 1000 if value < 10 ** 12 else value)

        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    value = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    pass
            else:
                try:
                    num = float(value)
                    return self._to_unix_ms(num)
                except Exception:
                    raise UserError(f"Unsupported date format: {value}")

        tzname = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        if isinstance(value, date) and not isinstance(value, datetime):
            value = datetime.combine(value, dtime.min)

        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo(tzname))
        value_utc = value.astimezone(ZoneInfo('UTC'))

        return int(value_utc.timestamp() * 1000)

    def __get_user_for_logging(self):
        user_id = self.env.user.id or self.env.context.get('uid', None)
        user_name = self.env.user.name or self.env['res.partner'].browse([user_id]).exists().name
        return user_id, user_name

    def _partner_for_bank_statement_line(self, correspondent_name, correspondent_code, correspondent_acc_num,
                                          acc_currency, bank,
                                          custom_correspondent_domain=False, custom_acc_num_domain=False):
        partner = self.env['res.partner']
        bank_partner = self.env['res.partner.bank']
        correspondent_domain = [('is_company', '=', True), '|', ('name', 'ilike', correspondent_name),
                                ('company_registry', '=', correspondent_code)]
        correspondent_acc_num_domain = [('sanitized_acc_number', '=', correspondent_acc_num),
                                        ('currency_id', '=', acc_currency.id)]

        # add check for none correspondent vars
        if any([not field for field in (correspondent_name, correspondent_code, correspondent_acc_num)]):
            return None

        if custom_correspondent_domain:
            correspondent_domain = custom_correspondent_domain
        if custom_acc_num_domain:
            correspondent_acc_num_domain = custom_acc_num_domain
        # search by acc_num
        correspondent_acc_ref = bank_partner.search(correspondent_acc_num_domain, limit=1)
        if correspondent_acc_ref:
            return correspondent_acc_ref.partner_id
        # search by company params
        else:
            correspondent_ref = partner.search(correspondent_domain, limit=1)
            # partner exists
            if not correspondent_ref:
                new_corresp_partner = partner.create({
                    'company_type': 'company',
                    'name': correspondent_name,
                    'company_registry': correspondent_code,
                })
            else:
                new_corresp_partner = correspondent_ref
            if not custom_acc_num_domain:
                correspondent_acc_num_domain.append(('partner_id', '=', new_corresp_partner.id))
            correspondent_acc_num_ref = self.env['res.partner.bank'].search(correspondent_acc_num_domain, limit=1)
            if not correspondent_acc_num_ref:
                new_acc_num = bank_partner.create({
                    'acc_number': correspondent_acc_num,
                    'bank_id': bank.id if bank else False,
                    'partner_id': new_corresp_partner.id,
                    'currency_id': acc_currency.id if acc_currency else False
                })
            return new_corresp_partner

    def _assign_journal(self):
        """
        Links an online account to a journal. Uses parent logic for non-Monobank providers.
        For Monobank, implements custom logic to skip _get_consent_expiring_date.
        Logs journal assignment for debugging.
        """
        self.ensure_one()
        _logger.debug(f"Assign_journal called for online account ID: {self.id}, online_identifier: {self.online_identifier}, account_number: {self.account_number}, provider: {self.account_online_link_id.provider}, context: {self.env.context}")

        # calling a parent method for non-Monobank providers
        if self.account_online_link_id.provider != 'monobank':
            _logger.debug("Using parent _assign_journal for non-Monobank provider")
            journal = super()._assign_journal()
        else:
            _logger.debug("Using Monobank-specific logic for journal assignment")
            ctx = self.env.context
            active_id = ctx.get('active_id')
            if ctx.get('active_model') == 'account.journal' and active_id:
                journal = self.env['account.journal'].browse(active_id)
                _logger.debug(f"Linking to existing journal ID: {journal.id}, name: {journal.name}")
                if journal.account_online_link_id:
                    _logger.warning(f"Unlinking previous online link ID: {journal.account_online_link_id.id} from journal {journal.id}")
                    journal.account_online_link_id.unlink()
                if self.currency_id and self.currency_id != journal.currency_id:
                    existing_entries = self.env['account.bank.statement.line'].search([('journal_id', '=', journal.id)])
                    if not existing_entries:
                        _logger.debug(f"Updating journal currency from {journal.currency_id.name} to {self.currency_id.name}")
                        journal.currency_id = self.currency_id.id
                    else:
                        _logger.warning(f"Cannot update currency for journal {journal.id} because it has existing entries")
            else:
                new_journal_code = self.env['account.journal'].get_next_bank_cash_default_code('bank', self.env.company)
                journal_name = f"Monobank {self.account_number or self.name or 'Account'}"
                _logger.debug(f"Creating new journal with code {new_journal_code}, name {journal_name}")
                bank = self.env['res.bank'].search([('name', '=', 'Monobank')])
                journal = self.env['account.journal'].create({
                    'name': journal_name,
                    'code': new_journal_code,
                    'type': 'bank',
                    'company_id': self.env.company.id,
                    'currency_id': self.currency_id.id if self.currency_id != self.env.company.currency_id else False,
                    'bank_acc_number': self.account_number
                })
                _logger.debug(f"Created new journal: ID {journal.id}, name {journal.name}")

            self.journal_ids = [(6, 0, [journal.id])]
            _logger.debug(f"Linked journal IDs to online account: {self.journal_ids.ids}")

            journal_vals = {
                'bank_statements_source': 'online_sync',
                'account_online_account_id': self.id,
            }
            if self.account_number and not journal.bank_acc_number:
                journal_vals['bank_acc_number'] = self.account_number
            journal.write(journal_vals)
            _logger.debug(f"Updated journal ID: {journal.id} with vals: {journal_vals}")

            last_sync = self.last_sync
            if not last_sync:
                today = fields.Date.today()
                last_sync = today - timedelta(days=30)
            bnk_stmt_line = self.env['account.bank.statement.line'].search(
                [('journal_id', 'in', self.journal_ids.ids)], order="date desc", limit=1
            )
            if bnk_stmt_line:
                last_sync = bnk_stmt_line.date
            self.last_sync = last_sync
            _logger.debug(f"last_sync set to: {self.last_sync}")

        journal_vals = {}
        if not journal.name.startswith('Monobank'):
            journal_vals['name'] = f"Monobank {self.account_number or self.name or 'Account'}"
            _logger.debug(f"Updating journal name to: {journal_vals['name']}")
        if journal_vals:
            journal.write(journal_vals)
            _logger.debug(f"Updated journal ID: {journal.id} with vals: {journal_vals}")

        _logger.debug(f"Journal assigned: ID {journal.id}, name {journal.name}, linked to online account {self.id}, bank_acc_number: {journal.bank_acc_number}, currency: {journal.currency_id.name}")

        return journal

    def _refresh(self):
        """ Override this method to skip redundant proxy requests for Monobank API integration. """
        if self.account_online_link_id.provider == 'monobank':
            return True
        return super()._refresh()