from odoo import api, fields, models
from odoo.tools.translate import code_translations

# Maximum number of results per category (keeps the search on arch_db cheap)
_LIMIT = 20

_CATEGORIES = [
    ('code', 'Python Code'),
    ('web', 'Web Client (JavaScript)'),
    ('field_label', 'Field Label'),
    ('selection_label', 'Selection Value'),
    ('view_text', 'View Text'),
    ('menu_label', 'Menu Name'),
    ('action_label', 'Window Action Name'),
]


class TranslationOverrideFinder(models.TransientModel):
    _name = 'translation.override.finder'
    _description = 'Translation Override: Find Source Text'

    search_text = fields.Char(string='Displayed Text', required=True)
    lang_id = fields.Many2one(
        'res.lang', string='Language', required=True, domain=[('active', '=', True)],
        default=lambda self: self.env['translation.override']._default_lang_id())
    include_code = fields.Boolean(
        string='Search Python/JavaScript Strings', default=True,
        help='Also search the translations loaded from the .po files of the installed '
             'modules (not available for English).')
    searched = fields.Boolean(readonly=True)
    line_ids = fields.One2many('translation.override.finder.line', 'wizard_id', string='Results')

    def action_search(self):
        self.ensure_one()
        self.line_ids.unlink()
        text = ' '.join((self.search_text or '').split())
        if text:
            vals_list = []
            for method in (self._find_menus, self._find_actions, self._find_field_labels,
                           self._find_selections, self._find_view_texts, self._find_code):
                vals_list += method(text, self.lang_id.code)
            self.env['translation.override.finder.line'].create(
                [dict(vals, wizard_id=self.id) for vals in vals_list])
        self.searched = True
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Find Source Text'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Searches. Each returns a list of line values.
    # ------------------------------------------------------------------
    def _find_menus(self, text, lang):
        menus = self.env['ir.ui.menu'].sudo().with_context(lang=lang).search(
            [('name', 'ilike', text)], limit=_LIMIT)
        return [{
            'category': 'menu_label',
            'label': menu.complete_name or menu.name,
            'matched_text': menu.name,
            'menu_id': menu.id,
        } for menu in menus]

    def _find_actions(self, text, lang):
        actions = self.env['ir.actions.act_window'].sudo().with_context(lang=lang).search(
            [('name', 'ilike', text)], limit=_LIMIT)
        return [{
            'category': 'action_label',
            'label': f'{action.name} ({action.res_model})',
            'matched_text': action.name,
            'action_id': action.id,
        } for action in actions]

    def _find_field_labels(self, text, lang):
        mfields = self.env['ir.model.fields'].sudo().with_context(lang=lang).search(
            [('field_description', 'ilike', text)], limit=_LIMIT)
        return [{
            'category': 'field_label',
            'label': f'{field.model_id.name} › {field.field_description} ({field.model}.{field.name})',
            'matched_text': field.field_description,
            'model_id': field.model_id.id,
            'field_id': field.id,
        } for field in mfields]

    def _find_selections(self, text, lang):
        selections = self.env['ir.model.fields.selection'].sudo().with_context(lang=lang).search(
            [('name', 'ilike', text)], limit=_LIMIT)
        return [{
            'category': 'selection_label',
            'label': f'{sel.field_id.model_id.name} › {sel.field_id.field_description} = {sel.value}',
            'matched_text': sel.name,
            'model_id': sel.field_id.model_id.id,
            'field_id': sel.field_id.id,
            'selection_value': sel.value,
        } for sel in selections]

    def _find_view_texts(self, text, lang):
        Override = self.env['translation.override']
        views = self.env['ir.ui.view'].sudo().with_context(lang=lang).search(
            [('arch_db', 'ilike', text)], limit=_LIMIT)
        wanted = text.casefold()
        results = []
        for view in views:
            seen = set()
            for shown in Override._view_terms(view, lang).values():
                plain = Override._term_text(view, shown)
                if wanted in plain.casefold() and plain not in seen:
                    seen.add(plain)
                    results.append({
                        'category': 'view_text',
                        'label': f'{view.name} ({view.model or view.type})',
                        'matched_text': plain,
                        'view_id': view.id,
                    })
            if len(results) >= _LIMIT * 2:
                break
        return results

    def _find_code(self, text, lang):
        if not self.include_code or lang == 'en_US':
            return []
        wanted = text.casefold()
        modules = self.env['ir.module.module'].sudo().search(
            [('state', '=', 'installed')]).mapped('name')
        results = {'code': [], 'web': []}
        for module in sorted(modules):
            if len(results['code']) < _LIMIT:
                for source, value in code_translations.get_python_translations(module, lang).items():
                    if wanted in (value or '').casefold() or wanted in source.casefold():
                        results['code'].append(self._code_line('code', module, source, value))
                        if len(results['code']) >= _LIMIT:
                            break
            if len(results['web']) < _LIMIT:
                messages = code_translations.get_web_translations(module, lang).get('messages', ())
                for message in messages:
                    source, value = message['id'], message['string']
                    if wanted in (value or '').casefold() or wanted in source.casefold():
                        results['web'].append(self._code_line('web', module, source, value))
                        if len(results['web']) >= _LIMIT:
                            break
        return results['code'] + results['web']

    @api.model
    def _code_line(self, category, module, source, value):
        return {
            'category': category,
            'label': f'[{module}] {source}',
            'matched_text': value,
            'module': module,
            'source_text': source,
        }


class TranslationOverrideFinderLine(models.TransientModel):
    _name = 'translation.override.finder.line'
    _description = 'Translation Override: Search Result'
    _order = 'category, id'

    wizard_id = fields.Many2one('translation.override.finder', required=True, ondelete='cascade')
    category = fields.Selection(_CATEGORIES, string='Type')
    label = fields.Char(string='Result')
    matched_text = fields.Char(string='Displayed Text')
    module = fields.Char()
    source_text = fields.Char(string='Source Text')
    model_id = fields.Many2one('ir.model')
    field_id = fields.Many2one('ir.model.fields')
    selection_value = fields.Char()
    view_id = fields.Many2one('ir.ui.view')
    menu_id = fields.Many2one('ir.ui.menu')
    action_id = fields.Many2one('ir.actions.act_window')

    def action_create_override(self):
        self.ensure_one()
        context = {
            'default_category': self.category,
            'default_lang_id': self.wizard_id.lang_id.id,
            'default_value': self.matched_text,
        }
        if self.category in ('code', 'web'):
            context.update(default_module=self.module, default_name=self.source_text)
        elif self.category in ('field_label', 'selection_label'):
            context.update(default_model_id=self.model_id.id, default_field_id=self.field_id.id)
            if self.category == 'selection_label':
                context['default_selection_value'] = self.selection_value
        elif self.category == 'view_text':
            context.update(default_view_id=self.view_id.id, default_name=self.matched_text)
        elif self.category == 'menu_label':
            context['default_menu_id'] = self.menu_id.id
        elif self.category == 'action_label':
            context['default_action_id'] = self.action_id.id
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('New Translation Override'),
            'res_model': 'translation.override',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': context,
        }
