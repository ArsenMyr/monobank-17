{
    'name': 'NetFrame Monobank Integration Enterprise',
    'version': '17.0.2.4',
    'summary': 'Integration of Monobank with  Odoo Enterprise',
    'description': """
        Integration of Monobank with  Odoo Enterprise.
        """,
    'support': 'https://netframe.odoo.com/',
    'author': "Netframe",
    'license': 'OPL-1',
    'price': 100.0,
    'currency': 'EUR',
    'category': 'Accounting',
    'depends': [
        'account_accountant',
        'account_online_synchronization',
        'nf_banks_core',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/system_params.xml',
        'data/monobank_payment_method.xml',
        'data/res_currency_data.xml',
        'data/res_bank.xml',
        'wizards/monobank_statement_pull_wizard_view.xml',
        'view/nf_monobank_online_account_journal_form.xml',
        'view/res_currency_views.xml',
        'view/account_online_link_views.xml',
    ],
    'images': [
        'static/description/banner.gif'
    ],
    'application': True,
    'installable': True,
}
# -*- coding: utf-8 -*-
