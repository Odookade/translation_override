from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from odoo.tools.translate import code_translations


@tagged('post_install', '-at_install')
class TestTranslationOverride(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lang = cls.env['res.lang']._activate_lang('fr_FR')
        cls.en = cls.env.ref('base.lang_en')
        cls.Override = cls.env['translation.override']

    def setUp(self):
        super().setUp()
        # the code override cache is per registry: make every test start clean
        self.env.registry.clear_cache()

    # ------------------------------------------------------------------
    # Python code
    # ------------------------------------------------------------------
    def test_python_code_override(self):
        source = 'Translation Override Test String'
        self.assertEqual(self.env['res.partner'].with_context(lang='fr_FR').env._(source), source)
        override = self.Override.create({
            'category': 'code', 'lang_id': self.lang.id,
            'module': 'translation_override', 'name': source, 'value': 'Chaîne remplacée',
        })
        self.assertEqual(
            code_translations.get_python_translations('translation_override', 'fr_FR').get(source),
            'Chaîne remplacée')
        # module specific: not applied to another module
        self.assertNotEqual(
            code_translations.get_python_translations('base', 'fr_FR').get(source),
            'Chaîne remplacée')
        # global override (no module) applies everywhere, specific one wins
        self.Override.create({
            'category': 'code', 'lang_id': self.lang.id, 'name': source, 'value': 'Globale',
        })
        self.assertEqual(code_translations.get_python_translations('base', 'fr_FR').get(source), 'Globale')
        self.assertEqual(
            code_translations.get_python_translations('translation_override', 'fr_FR').get(source),
            'Chaîne remplacée')
        override.action_archive()
        self.assertEqual(
            code_translations.get_python_translations('translation_override', 'fr_FR').get(source),
            'Globale')

    def test_python_code_override_through_underscore(self):
        source = 'Another Translation Override Test String'
        self.Override.create({
            'category': 'code', 'lang_id': self.lang.id,
            'module': 'translation_override', 'name': source, 'value': 'Traduit',
        })
        env_fr = self.env(context=dict(self.env.context, lang='fr_FR'))
        self.assertEqual(env_fr._(source), 'Traduit')

    def test_python_code_english_forbidden(self):
        with self.assertRaises(ValidationError):
            self.Override.create({
                'category': 'code', 'lang_id': self.en.id, 'name': 'Save', 'value': 'Store',
            })

    def test_unique_active(self):
        vals = {'category': 'code', 'lang_id': self.lang.id, 'name': 'Dup', 'value': 'A'}
        override = self.Override.create(vals)
        copy = override.copy()
        self.assertFalse(copy.active, 'a copy is archived to respect the uniqueness')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.Override.create(dict(vals, value='B'))
            self.env.flush_all()

    # ------------------------------------------------------------------
    # Web client
    # ------------------------------------------------------------------
    def test_web_client_override(self):
        IrHttp = self.env['ir.http']
        hash_before = IrHttp._get_web_translations_hash(['web'], 'fr_FR')
        self.Override.create({
            'category': 'web', 'lang_id': self.lang.id, 'module': 'web',
            'name': 'Discard', 'value': 'Jeter',
        })
        self.Override.create({
            'category': 'web', 'lang_id': self.lang.id,
            'name': 'A brand new web string', 'value': 'Nouvelle',
        })
        translations, _params = IrHttp._get_translations_for_webclient(['web', 'base'], 'fr_FR')
        web = {m['id']: m['string'] for m in translations['web']['messages']}
        base = {m['id']: m['string'] for m in translations['base']['messages']}
        self.assertEqual(web['Discard'], 'Jeter')
        self.assertEqual(web['A brand new web string'], 'Nouvelle')
        self.assertEqual(base['A brand new web string'], 'Nouvelle')
        self.assertNotIn('Discard', base, 'module specific override must stay in its module')
        # the cached original translations are untouched
        original = code_translations.get_web_translations('web', 'fr_FR')['messages']
        self.assertFalse(any(m['string'] == 'Jeter' for m in original))
        self.assertNotEqual(hash_before, IrHttp._get_web_translations_hash(['web'], 'fr_FR'))

    # ------------------------------------------------------------------
    # Translated records
    # ------------------------------------------------------------------
    def test_field_label_apply_and_restore(self):
        field = self.env['ir.model.fields']._get('res.partner', 'website')
        before = field.with_context(lang='fr_FR').field_description
        override = self.Override.create({
            'category': 'field_label', 'lang_id': self.lang.id,
            'field_id': field.id, 'value': 'Site Internet Perso',
        })
        self.assertEqual(override.model_id, field.model_id)
        self.assertTrue(override.applied)
        self.assertEqual(field.with_context(lang='fr_FR').field_description, 'Site Internet Perso')
        self.assertEqual(
            self.env['res.partner'].with_context(lang='fr_FR').fields_get(['website'])['website']['string'],
            'Site Internet Perso')
        # English untouched
        self.assertEqual(field.with_context(lang='en_US').field_description, 'Website Link')

        override.value = 'Site Web 2'
        self.assertEqual(field.with_context(lang='fr_FR').field_description, 'Site Web 2')

        override.action_archive()
        self.assertFalse(override.applied)
        field.invalidate_recordset()
        self.assertEqual(field.with_context(lang='fr_FR').field_description, before)

    def test_selection_label(self):
        field = self.env['ir.model.fields']._get('res.partner', 'type')
        override = self.Override.create({
            'category': 'selection_label', 'lang_id': self.lang.id,
            'field_id': field.id, 'selection_value': 'invoice', 'value': 'Facturation XYZ',
        })
        selection = dict(self.env['res.partner'].with_context(lang='fr_FR')
                         .fields_get(['type'])['type']['selection'])
        self.assertEqual(selection['invoice'], 'Facturation XYZ')
        override.unlink()
        selection = dict(self.env['res.partner'].with_context(lang='fr_FR')
                         .fields_get(['type'])['type']['selection'])
        self.assertNotEqual(selection['invoice'], 'Facturation XYZ')

    def test_selection_label_unknown_key(self):
        field = self.env['ir.model.fields']._get('res.partner', 'type')
        with self.assertRaises(UserError):
            self.Override.create({
                'category': 'selection_label', 'lang_id': self.lang.id,
                'field_id': field.id, 'selection_value': 'does_not_exist', 'value': 'X',
            })

    def test_menu_and_action(self):
        menu = self.env.ref('base.menu_administration')
        action = self.env.ref('base.action_res_users')
        menu_before = menu.with_context(lang='fr_FR').name
        self.Override.create([{
            'category': 'menu_label', 'lang_id': self.lang.id,
            'menu_id': menu.id, 'value': 'Réglages XYZ',
        }, {
            'category': 'action_label', 'lang_id': self.lang.id,
            'action_id': action.id, 'value': 'Utilisateurs XYZ',
        }])
        self.assertEqual(menu.with_context(lang='fr_FR').name, 'Réglages XYZ')
        self.assertEqual(action.with_context(lang='fr_FR').name, 'Utilisateurs XYZ')
        self.assertNotEqual(menu.with_context(lang='en_US').name, 'Réglages XYZ')
        self.Override.search([('menu_id', '=', menu.id)]).unlink()
        menu.invalidate_recordset()
        self.assertEqual(menu.with_context(lang='fr_FR').name, menu_before)

    def test_reapply_after_terms_reload(self):
        menu = self.env.ref('base.menu_administration')
        override = self.Override.create({
            'category': 'menu_label', 'lang_id': self.lang.id,
            'menu_id': menu.id, 'value': 'Réglages XYZ',
        })
        # simulate a .po reload overwriting our value
        menu.update_field_translations('name', {'fr_FR': 'Écrasé'})
        self.env['ir.module.module']._load_module_terms(['base'], ['fr_FR'], overwrite=True)
        menu.invalidate_recordset()
        self.assertEqual(menu.with_context(lang='fr_FR').name, 'Réglages XYZ')
        self.assertTrue(override.applied)

    # ------------------------------------------------------------------
    # View text
    # ------------------------------------------------------------------
    def _make_view(self):
        view = self.env['ir.ui.view'].create({
            'name': 'translation.override.test',
            'model': 'res.partner',
            'type': 'form',
            'arch': '<form><sheet>'
                    '<button name="toggle_active" type="object" string="Archive Me"/>'
                    '<div>Hello &amp; welcome</div>'
                    '<p>Other text</p>'
                    '</sheet></form>',
        })
        view.update_field_translations('arch_db', {'fr_FR': {
            'Archive Me': 'Archiver moi',
            'Hello &amp; welcome': 'Bonjour &amp; bienvenue',
            'Other text': 'Autre texte',
        }})
        return view

    def test_view_text_other_lang(self):
        view = self._make_view()
        override = self.Override.create({
            'category': 'view_text', 'lang_id': self.lang.id, 'view_id': view.id,
            'name': 'Bonjour & bienvenue', 'value': 'Salut & bienvenue',
        })
        arch_fr = view.with_context(lang='fr_FR').arch_db
        arch_en = view.with_context(lang='en_US').arch_db
        self.assertIn('Salut &amp; bienvenue', arch_fr)
        self.assertIn('Autre texte', arch_fr, 'other terms keep their translation')
        self.assertIn('Hello &amp; welcome', arch_en, 'English must not be modified')
        self.assertNotIn('Salut', arch_en)

        # attribute term: stored raw, not escaped
        attr = self.Override.create({
            'category': 'view_text', 'lang_id': self.lang.id, 'view_id': view.id,
            'name': 'Archiver moi', 'value': 'Archiver & fermer',
        })
        self.assertIn('string="Archiver &amp; fermer"', view.with_context(lang='fr_FR').arch_db)

        (override | attr).action_archive()
        arch_fr = view.with_context(lang='fr_FR').arch_db
        self.assertIn('Bonjour &amp; bienvenue', arch_fr)
        self.assertIn('Archiver moi', arch_fr)

    def test_view_text_english(self):
        view = self._make_view()
        override = self.Override.create({
            'category': 'view_text', 'lang_id': self.en.id, 'view_id': view.id,
            'name': 'Other text', 'value': 'Different text',
        })
        self.assertIn('Different text', view.with_context(lang='en_US').arch_db)
        self.assertIn('Autre texte', view.with_context(lang='fr_FR').arch_db)
        override.unlink()
        self.assertIn('Other text', view.with_context(lang='en_US').arch_db)

    def test_view_text_not_found(self):
        view = self._make_view()
        with self.assertRaises(UserError):
            self.Override.create({
                'category': 'view_text', 'lang_id': self.lang.id, 'view_id': view.id,
                'name': 'Not in the view', 'value': 'X',
            })

    # ------------------------------------------------------------------
    # Finder
    # ------------------------------------------------------------------
    def test_finder(self):
        view = self._make_view()
        finder = self.env['translation.override.finder'].create({
            'search_text': 'Autre texte', 'lang_id': self.lang.id,
        })
        finder.action_search()
        line = finder.line_ids.filtered(lambda rec: rec.category == 'view_text' and rec.view_id == view)
        self.assertEqual(line.matched_text, 'Autre texte')
        action = line.action_create_override()
        self.assertEqual(action['context']['default_name'], 'Autre texte')
        self.Override.with_context(action['context']).create({'value': 'Texte X'})
        self.assertIn('Texte X', view.with_context(lang='fr_FR').arch_db)
