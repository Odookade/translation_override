from odoo import api, models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @api.model
    def _get_translations_for_webclient(self, modules, lang):
        """Inject the web client overrides into the translations sent to the
        browser. The result feeds ``_get_web_translations_hash`` (ormcache in
        the 'default' cache), which is cleared whenever an override changes, so
        browsers download the new translations on their next page load."""
        translations_per_module, lang_params = super()._get_translations_for_webclient(modules, lang)
        lang_code = (lang_params or {}).get('code') or lang or self.env.context.get('lang')
        if not lang_code or not translations_per_module:
            return translations_per_module, lang_params

        Override = self.env['translation.override'].sudo()
        if not Override._get_code_override_map().get(('web', lang_code)):
            return translations_per_module, lang_params

        result = {}
        for module, data in translations_per_module.items():
            overrides = Override._get_code_overrides('web', module, lang_code)
            if not overrides:
                result[module] = data
                continue
            # never mutate ``data``: it is the read-only cached object of
            # odoo.tools.translate.code_translations
            messages = []
            seen = set()
            for message in (data or {}).get('messages', ()):
                source = message['id']
                seen.add(source)
                messages.append({'id': source, 'string': overrides.get(source, message['string'])})
            messages.extend(
                {'id': source, 'string': value}
                for source, value in overrides.items() if source not in seen
            )
            result[module] = {**(data or {}), 'messages': messages}
        return result, lang_params
