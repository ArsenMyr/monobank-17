{
    'name': "NF Banks Core",
    'version': '17.0.0.1',
    'summary': 'Core improvements & dependencies for Netframe Bank Integrations.',
    'license': 'LGPL-3',
    'author': 'Netframe',
    'support': 'odoo@netframe.org',
    'website': 'https://www.netframe.org/',
    'depends': [
        'account_online_synchronization',
    ],
    'data': [
        'data/menu_access.xml',
        'views/account_online_link_views.xml',
        'views/account_online_account_views.xml',
        'views/account_journal_form.xml',
    ],
    'images': [
        'static/description/banner.gif'
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
