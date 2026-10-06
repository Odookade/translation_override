import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    @api.model
    def _load_module_terms(self, modules, langs, overwrite=False):
        """Loading .po files (module install/upgrade, language activation,
        "Load a Translation"...) may overwrite the values written by the
        overrides: re-apply them afterwards."""
        res = super()._load_module_terms(modules, langs, overwrite=overwrite)
        if 'translation.override' in self.env:
            try:
                with self.env.cr.savepoint():
                    self.env['translation.override']._reapply_after_terms_loaded(langs)
            except Exception:
                _logger.exception('Translation overrides could not be re-applied.')
        return res
