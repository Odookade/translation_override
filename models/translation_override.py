import logging
from xml.sax.saxutils import escape as xml_escape

from lxml import etree

from odoo import api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL, frozendict

_logger = logging.getLogger(__name__)

# Strings served from the in-memory code translations (.po files)
CODE_CATEGORIES = ('code', 'web')
# Strings stored as translations on a database record
TARGET_CATEGORIES = ('field_label', 'selection_label', 'view_text', 'menu_label', 'action_label')

# Fields defining *what* is overridden: when one of them changes, the previous
# target must be restored before the new one is applied.
_TARGET_KEYS = frozenset({
    'category', 'lang_id', 'name', 'model_id', 'field_id', 'selection_value',
    'view_id', 'menu_id', 'action_id', 'active',
})
# Fields whose modification requires a synchronisation (cache / target)
_SYNC_KEYS = _TARGET_KEYS | {'value', 'module'}


class TranslationOverride(models.Model):
    _name = 'translation.override'
    _description = 'Translation Override'
    _order = 'category, lang_code, id desc'

    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------
    category = fields.Selection(
        selection=[
            ('code', 'Python Code'),
            ('web', 'Web Client (JavaScript)'),
            ('field_label', 'Field Label'),
            ('selection_label', 'Selection Value'),
            ('view_text', 'View Text'),
            ('menu_label', 'Menu Name'),
            ('action_label', 'Window Action Name'),
        ],
        string='Type', required=True, default='code', index=True)
    lang_id = fields.Many2one(
        'res.lang', string='Language', required=True, ondelete='cascade',
        domain=[('active', '=', True)],
        default=lambda self: self._default_lang_id(),
        help='The override is only applied for this language.')
    lang_code = fields.Char(
        related='lang_id.code', string='Language Code', store=True, index=True,
        help='Code of the language (e.g. fa_IR), used for fast lookups.')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Internal Note')

    # ------------------------------------------------------------------
    # Python code / web client
    # ------------------------------------------------------------------
    module = fields.Char(
        string='Module',
        help='Technical name of the module the string belongs to (e.g. sale, stock). '
             'Leave empty to apply the override to every module.')
    name = fields.Char(
        string='Source Text',
        help='Python code / Web client: the exact English source string, as written '
             'in _() / _t() (case sensitive).\n'
             'View text: the text exactly as it is currently displayed in the '
             'selected language.')
    value = fields.Text(string='Translation', required=True)

    # ------------------------------------------------------------------
    # Field label / selection value
    # ------------------------------------------------------------------
    model_id = fields.Many2one('ir.model', string='Model', ondelete='cascade')
    field_id = fields.Many2one(
        'ir.model.fields', string='Field', ondelete='cascade',
        domain="[('model_id', '=', model_id)] + "
               "([('ttype', 'in', ['selection', 'reference'])] "
               "if category == 'selection_label' else [])")
    selection_value = fields.Char(
        string='Selection Key',
        help='Technical key of the selection option (e.g. draft, done), not its label.')

    # ------------------------------------------------------------------
    # View text / menu / window action
    # ------------------------------------------------------------------
    view_id = fields.Many2one('ir.ui.view', string='View', ondelete='cascade')
    menu_id = fields.Many2one('ir.ui.menu', string='Menu', ondelete='cascade')
    action_id = fields.Many2one('ir.actions.act_window', string='Window Action', ondelete='cascade')

    # ------------------------------------------------------------------
    # Technical state
    # ------------------------------------------------------------------
    applied = fields.Boolean(
        string='Applied', readonly=True, copy=False,
        help='The value is currently written on the target record. '
             'Its previous value is kept and restored when the override is '
             'archived or deleted.')
    backup_data = fields.Json(string='Previous Value', readonly=True, copy=False)

    # ------------------------------------------------------------------
    # SQL constraints: one active override per target and language
    # ------------------------------------------------------------------
    _code_uniq = models.UniqueIndex(
        "(category, lang_id, COALESCE(module, ''), md5(name)) "
        "WHERE active IS TRUE AND category IN ('code', 'web')",
        lambda env, diag=None: env._(
            'An active override already exists for this source text, module and language.'),
    )
    _field_label_uniq = models.UniqueIndex(
        "(lang_id, field_id) WHERE active IS TRUE AND category = 'field_label'",
        lambda env, diag=None: env._(
            'An active override already exists for this field and language.'),
    )
    _selection_label_uniq = models.UniqueIndex(
        "(lang_id, field_id, selection_value) "
        "WHERE active IS TRUE AND category = 'selection_label'",
        lambda env, diag=None: env._(
            'An active override already exists for this selection value and language.'),
    )
    _view_text_uniq = models.UniqueIndex(
        "(lang_id, view_id, md5(name)) WHERE active IS TRUE AND category = 'view_text'",
        lambda env, diag=None: env._(
            'An active override already exists for this text, view and language.'),
    )
    _menu_label_uniq = models.UniqueIndex(
        "(lang_id, menu_id) WHERE active IS TRUE AND category = 'menu_label'",
        lambda env, diag=None: env._(
            'An active override already exists for this menu and language.'),
    )
    _action_label_uniq = models.UniqueIndex(
        "(lang_id, action_id) WHERE active IS TRUE AND category = 'action_label'",
        lambda env, diag=None: env._(
            'An active override already exists for this window action and language.'),
    )

    # ==================================================================
    # Defaults / compute / onchange
    # ==================================================================
    @api.model
    def _default_lang_id(self):
        return self.env['res.lang'].search([('code', '=', self.env.lang or 'en_US')], limit=1)

    @api.depends('category', 'name', 'lang_code', 'field_id', 'selection_value',
                 'view_id', 'menu_id', 'action_id')
    def _compute_display_name(self):
        for rec in self:
            if rec.category == 'field_label':
                target = rec.field_id.display_name
            elif rec.category == 'selection_label':
                target = f'{rec.field_id.display_name} = {rec.selection_value or ""}'
            elif rec.category == 'view_text':
                target = f'{rec.view_id.name or ""}: {rec.name or ""}'
            elif rec.category == 'menu_label':
                target = rec.menu_id.display_name
            elif rec.category == 'action_label':
                target = rec.action_id.display_name
            else:
                target = rec.name
            target = target or self.env._('New')
            rec.display_name = f'[{rec.lang_code}] {target}' if rec.lang_code else target

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if self.field_id and self.field_id.model_id != self.model_id:
            self.field_id = False

    @api.onchange('field_id')
    def _onchange_field_id(self):
        if self.field_id:
            self.model_id = self.field_id.model_id

    # ==================================================================
    # Constraints
    # ==================================================================
    @api.constrains('category', 'name', 'lang_id', 'model_id', 'field_id',
                    'selection_value', 'view_id', 'menu_id', 'action_id')
    def _check_target(self):
        for rec in self:
            category = rec.category
            if category in CODE_CATEGORIES:
                if not rec.name:
                    raise ValidationError(self.env._(
                        'A source text is required for Python code and web client overrides.'))
                if category == 'code' and rec.lang_code == 'en_US':
                    raise ValidationError(self.env._(
                        'Odoo never translates Python strings into English (en_US): the source '
                        'text is always returned as is. Choose another language, or use another '
                        'override type (field label, view text, menu, ...).'))
            elif category == 'field_label':
                if not rec.field_id:
                    raise ValidationError(self.env._('A field is required for a field label override.'))
            elif category == 'selection_label':
                if not (rec.field_id and rec.selection_value):
                    raise ValidationError(self.env._(
                        'A field and a selection key are required for a selection value override.'))
                if rec.field_id.ttype not in ('selection', 'reference'):
                    raise ValidationError(self.env._(
                        'The field "%(field)s" is not a selection field.',
                        field=rec.field_id.display_name))
            elif category == 'view_text':
                if not (rec.view_id and (rec.name or '').strip()):
                    raise ValidationError(self.env._(
                        'A view and a source text are required for a view text override.'))
            elif category == 'menu_label':
                if not rec.menu_id:
                    raise ValidationError(self.env._('A menu is required for a menu name override.'))
            elif category == 'action_label':
                if not rec.action_id:
                    raise ValidationError(self.env._(
                        'A window action is required for a window action name override.'))
            if rec.field_id and rec.model_id and rec.field_id.model_id != rec.model_id:
                raise ValidationError(self.env._(
                    'The field "%(field)s" does not belong to the model "%(model)s".',
                    field=rec.field_id.display_name, model=rec.model_id.display_name))

    # ==================================================================
    # CRUD
    # ==================================================================
    @api.model
    def _normalize_vals(self, vals):
        if 'module' in vals:
            vals['module'] = (vals['module'] or '').strip() or False
        if vals.get('field_id') and not vals.get('model_id'):
            vals['model_id'] = self.env['ir.model.fields'].browse(vals['field_id']).model_id.id
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normalize_vals(vals)
        records = super().create(vals_list)
        records._sync(clear_code_cache=any(r.category in CODE_CATEGORIES for r in records))
        return records

    def write(self, vals):
        self._normalize_vals(vals)
        if not _SYNC_KEYS.intersection(vals):
            # e.g. note, or the technical state written by this model itself
            return super().write(vals)
        clear_code_cache = (
            vals.get('category') in CODE_CATEGORIES
            or any(rec.category in CODE_CATEGORIES for rec in self)
        )
        if _TARGET_KEYS.intersection(vals):
            self.filtered('applied')._revert_targets()
        res = super().write(vals)
        self._sync(clear_code_cache=clear_code_cache)
        return res

    def unlink(self):
        clear_code_cache = any(rec.category in CODE_CATEGORIES for rec in self)
        self.filtered('applied')._revert_targets()
        res = super().unlink()
        if clear_code_cache:
            self._clear_code_cache()
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if not (default and 'active' in default):
            # a copy would violate the uniqueness constraints while active
            for vals in vals_list:
                vals['active'] = False
        return vals_list

    def _sync(self, clear_code_cache=True):
        if clear_code_cache:
            self._clear_code_cache()
        self._apply_targets(raise_on_error=True)

    # ==================================================================
    # Python code / web client: cached lookup
    # (used by code_translations_patch.py and ir_http.py)
    # ==================================================================
    def _clear_code_cache(self):
        # Clears the 'default' ormcache (our lookups and the web client
        # translations hash) and signals the other workers.
        self.env.registry.clear_cache()
        # Warm the cache up with the current transaction: lookups done without
        # a request (cron, script) use a separate cursor that can not see the
        # uncommitted changes yet. On rollback, Odoo clears the invalidated
        # caches again, so a rolled back value can not survive.
        self.sudo()._get_code_override_map()

    @api.model
    @tools.ormcache()
    def _get_code_override_map(self):
        """Return ``{(category, lang): {module or '': {source: value}}}`` for all
        active Python code / web client overrides (single query)."""
        self.flush_model(['category', 'lang_code', 'module', 'name', 'value', 'active'])
        self.env.cr.execute(SQL(
            """
            SELECT category, lang_code, COALESCE(module, ''), name, value
              FROM %s
             WHERE active IS TRUE
               AND category IN %s
               AND name IS NOT NULL
               AND value IS NOT NULL
               AND lang_code IS NOT NULL
             ORDER BY id
            """,
            SQL.identifier(self._table), CODE_CATEGORIES,
        ))
        result = {}
        for category, lang, module, source, value in self.env.cr.fetchall():
            result.setdefault((category, lang), {}).setdefault(module, {})[source] = value
        return frozendict({
            key: frozendict({module: frozendict(terms) for module, terms in per_module.items()})
            for key, per_module in result.items()
        })

    @api.model
    @tools.ormcache('category', 'module_name', 'lang')
    def _get_code_overrides(self, category, module_name, lang):
        """Return ``{source: value}`` for one module and language. Overrides
        without module apply to every module; module specific ones win."""
        per_module = self._get_code_override_map().get((category, lang))
        if not per_module:
            return frozendict()
        result = dict(per_module.get('', {}))
        if module_name:
            result.update(per_module.get(module_name, {}))
        return frozendict(result)

    # ==================================================================
    # Database targets: apply / revert
    # ==================================================================
    def _apply_targets(self, raise_on_error=True):
        clear_stable = False
        for rec in self:
            if not rec.active or rec.category not in TARGET_CATEGORIES:
                continue
            try:
                with self.env.cr.savepoint():
                    if rec.category == 'view_text':
                        rec._apply_view_text()
                    else:
                        rec._apply_translated_value()
            except Exception:
                if raise_on_error:
                    raise
                _logger.warning('Translation override %s (%s) could not be applied.',
                                rec.id, rec.display_name, exc_info=True)
                continue
            clear_stable = clear_stable or rec.category in ('field_label', 'selection_label')
        if clear_stable:
            self._clear_field_caches()

    def _revert_targets(self):
        """Restore the previous value of the targets. Never raises: archiving or
        deleting an override must always be possible."""
        clear_stable = False
        for rec in self:
            if not rec.applied:
                continue
            try:
                with self.env.cr.savepoint():
                    if rec.category == 'view_text':
                        rec._revert_view_text()
                    elif rec.category in TARGET_CATEGORIES:
                        rec._revert_translated_value()
            except Exception:
                _logger.warning('Previous value of translation override %s (%s) could not be '
                                'restored.', rec.id, rec.display_name, exc_info=True)
            rec.write({'applied': False, 'backup_data': False})
            clear_stable = clear_stable or rec.category in ('field_label', 'selection_label')
        if clear_stable:
            self._clear_field_caches()

    def _clear_field_caches(self):
        # ir.model.fields._get_fields_cached (labels/selections shown in the UI)
        # lives in the 'stable' cache; clearing it also signals the other workers.
        self.env.registry.clear_cache('stable')

    # ------------------------------------------------------------------
    # Targets having a "translate=True" field (one value per language)
    # ------------------------------------------------------------------
    def _get_translated_target(self, raise_if_missing=True):
        self.ensure_one()
        if self.category == 'field_label':
            return self.field_id.sudo(), 'field_description'
        if self.category == 'selection_label':
            selection = self.env['ir.model.fields.selection'].sudo().search([
                ('field_id', '=', self.field_id.id),
                ('value', '=', self.selection_value),
            ], limit=1)
            if not selection and raise_if_missing:
                raise UserError(self.env._(
                    'No selection option with the key "%(key)s" exists on the field %(field)s.',
                    key=self.selection_value, field=self.field_id.display_name))
            return selection, 'name'
        if self.category == 'menu_label':
            return self.menu_id.sudo(), 'name'
        if self.category == 'action_label':
            return self.action_id.sudo(), 'name'
        raise UserError(self.env._('This override type has no translated target.'))

    @api.model
    def _read_stored_translation(self, record, fname, lang):
        """Raw stored value of ``fname`` for ``lang`` (no fallback), or None."""
        record.flush_recordset([fname])
        self.env.cr.execute(SQL(
            "SELECT %s ->> %s FROM %s WHERE id = %s",
            SQL.identifier(fname), lang, SQL.identifier(record._table), record.id,
        ))
        row = self.env.cr.fetchone()
        return row[0] if row else None

    def _apply_translated_value(self):
        self.ensure_one()
        record, fname = self._get_translated_target()
        if not record:
            raise UserError(self.env._('The target of the override "%s" no longer exists.',
                                       self.display_name))
        vals = {'applied': True}
        if not self.applied:
            # keep the original value; when re-applying, the backup stays untouched
            vals['backup_data'] = {
                'value': self._read_stored_translation(record, fname, self.lang_code),
            }
        record.update_field_translations(fname, {self.lang_code: self.value})
        self.write(vals)

    def _revert_translated_value(self):
        self.ensure_one()
        record, fname = self._get_translated_target(raise_if_missing=False)
        if not record:
            return
        previous = (self.backup_data or {}).get('value')
        if self.lang_code == 'en_US' and not previous:
            return  # the source value can not be removed
        record.update_field_translations(fname, {self.lang_code: previous or False})

    # ------------------------------------------------------------------
    # View text (arch_db is translated term by term: xml_translate)
    # ------------------------------------------------------------------
    @api.model
    def _view_terms(self, view, lang):
        """Return ``{en_US term: term displayed in lang}`` for the view."""
        field = view._fields['arch_db']
        arch_en = view.with_context(lang='en_US').arch_db or ''
        if lang == 'en_US':
            return {term: term for term in field.get_trans_terms(arch_en)}
        arch_lang = view.with_context(lang=lang).arch_db or ''
        dictionary = field.get_translation_dictionary(arch_en, {lang: arch_lang})
        return {term_en: values.get(lang) or term_en for term_en, values in dictionary.items()}

    @api.model
    def _term_text(self, view, term):
        """Plain text of a term, whitespace normalized (as seen on screen)."""
        try:
            text = view._fields['arch_db'].get_text_content(term)
        except Exception:  # noqa: BLE001 - malformed fragment: compare raw text
            text = term
        return ' '.join((text or '').split())

    @api.model
    def _term_matches(self, view, term, wanted):
        wanted = (wanted or '').strip()
        if not term or not wanted:
            return False
        return term.strip() == wanted or self._term_text(view, term) == ' '.join(wanted.split())

    @api.model
    def _xml_attribute_values(self, arch):
        """Values of all attributes of the arch (attribute terms are not escaped)."""
        if not arch:
            return set()
        try:
            parser = etree.XMLParser(recover=True, resolve_entities=False)
            root = etree.fromstring(arch.encode(), parser=parser)
        except (etree.LxmlError, ValueError):
            return set()
        if root is None:
            return set()
        return {
            value.strip()
            for node in root.iter() if isinstance(node.tag, str)
            for value in node.attrib.values() if value.strip()
        }

    def _view_new_term(self, displayed, attribute_values):
        value = self.value.strip()
        if displayed in attribute_values or '<' in displayed:
            # attribute values are stored raw; a term containing markup is
            # replaced by the value as an XML fragment
            return value
        return xml_escape(value)

    def _apply_view_text(self):
        self.ensure_one()
        view = self.view_id.sudo()
        lang = self.lang_code
        if self.applied:
            # start again from the original texts (also covers the case where
            # translations were reloaded or the value was modified)
            self._revert_view_text()
            self.write({'applied': False, 'backup_data': False})

        terms = self._view_terms(view, lang)
        matches = {key: shown for key, shown in terms.items()
                   if self._term_matches(view, shown, self.name)}
        if not matches:
            raise UserError(self.env._(
                'The text "%(text)s" was not found in the view "%(view)s" for the language '
                '%(lang)s. Copy it exactly as it is displayed on screen (case sensitive), or '
                'use the "Find Source Text" tool.',
                text=self.name, view=view.display_name, lang=self.lang_id.name))

        attribute_values = self._xml_attribute_values(view.with_context(lang=lang).arch_db)
        translations = {}
        backup = []
        for key, shown in matches.items():
            new_term = self._view_new_term(shown, attribute_values)
            translations[key] = new_term
            # en_US: the term itself changes, so it is identified by its new value
            backup.append([new_term, key] if lang == 'en_US' else [key, shown])
        view.update_field_translations('arch_db', {lang: translations})
        self.write({'applied': True, 'backup_data': {'terms': backup}})

    def _revert_view_text(self):
        self.ensure_one()
        view = self.view_id.sudo()
        pairs = (self.backup_data or {}).get('terms') or []
        if not view or not pairs:
            return
        lang = self.lang_code
        current = self._view_terms(view, lang)
        translations = {}
        for key, previous in pairs:
            if key not in current:
                continue  # the source changed in the meantime (e.g. module update)
            if lang == 'en_US':
                translations[key] = previous
            else:
                # False removes the translation (the English term is shown again)
                translations[key] = previous if previous != key else False
        if translations:
            view.update_field_translations('arch_db', {lang: translations})

    # ==================================================================
    # Actions / hooks
    # ==================================================================
    def action_reapply(self):
        records = self.filtered('active')
        if any(rec.category in CODE_CATEGORIES for rec in records):
            self._clear_code_cache()
        records._apply_targets(raise_on_error=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._('%s override(s) applied.', len(records)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    @api.model
    def _reapply_after_terms_loaded(self, langs):
        """Called after .po files were (re)loaded: they may have overwritten our values."""
        langs = set(langs or []) | {'en_US'}  # module updates also reset en_US values
        overrides = self.sudo().search([
            ('category', 'in', TARGET_CATEGORIES),
            ('lang_code', 'in', list(langs)),
        ])
        if overrides:
            _logger.info('Re-applying %s translation override(s).', len(overrides))
            overrides._apply_targets(raise_on_error=False)
