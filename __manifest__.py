{
    'name': 'Translation Override',
    'version': '19.0.1.1.0',
    'category': 'Hidden/Tools',
    'summary': 'Override any Odoo translation (Python code, web client, field labels, '
               'selection values, view texts, menus and actions) without editing .po files',
    'description': """
Translation Override
====================

Lets administrators fix wrong or conflicting translations directly from the
user interface, without touching any ``.po`` file.

* **Python code / Web client** strings (``_()``, ``_t()``): applied at runtime
  with a higher priority than the ``.po`` files, instantly and on all workers.
* **Field labels, selection values, view texts, menus and window actions**:
  written into the translation of the target record through the standard
  ``update_field_translations`` API. The previous value is backed up and
  restored when the override is archived or deleted, and the override is
  re-applied automatically whenever translations are (re)loaded.
""",
    'author': 'Erfan Meraati',
    'website': 'https://meraati.net',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/translation_override_views.xml',
        'wizard/translation_override_finder_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
