"""Runtime patch giving Python code overrides priority over the .po files.

``odoo.tools.translate.get_translation`` (used by ``_()``, ``env._()`` and
``_lt()``) reads ``code_translations.get_python_translations(module, lang)``
and has no access to an environment. This patch wraps that method and merges
the active overrides of the current database on top of the original
translations.

Design notes:

* The patch is process wide, so it does nothing for databases where the module
  is not installed (the model is not in their registry) and nothing while the
  registry is loading.
* The overrides come from an ormcache'd model method. On a cache hit, the
  value is read straight from the registry cache, without any cursor; this
  is the case for virtually every call. On a miss, the cursor of the current
  HTTP request is used when there is one (it sees uncommitted changes and is
  rolled back consistently), otherwise a short lived read-only cursor.
* Web client strings are NOT handled here but in ``ir_http.py``, through a
  regular model override.

This relies on ``odoo.tools.translate.CodeTranslations``, which is internal to
Odoo: run the module tests after every Odoo update.
"""
import logging
import threading
from collections import ChainMap

from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import translate as translate_tools

_logger = logging.getLogger(__name__)

_MODEL = 'translation.override'
_PATCH_FLAG = '_translation_override_patched'
_local = threading.local()


def _request_env(dbname):
    """Environment of the current HTTP request on ``dbname``, if any."""
    try:
        from odoo.http import request  # noqa: PLC0415
        if request and request.db == dbname:
            env = request.env
            if env is not None and not env.cr.closed:
                return env
    except Exception:  # noqa: BLE001 - no usable request
        pass
    return None


def _lookup(category, module_name, lang):
    """Return the ``{source: value}`` overrides, or None."""
    if getattr(_local, 'busy', False):
        return None  # re-entrant call (e.g. a _() inside the lookup itself)
    dbname = getattr(threading.current_thread(), 'dbname', None)
    if not dbname:
        return None
    registry = Registry.registries.get(dbname)
    if registry is None or not registry.ready or _MODEL not in registry:
        return None

    _local.busy = True
    try:
        model_class = registry[_MODEL]
        # 1. fast path: read the ormcache directly, no cursor needed
        cache = getattr(model_class._get_code_overrides, '__cache__', None)
        if cache is not None:
            try:
                key = cache.key(model_class, category, module_name, lang)
                return registry._Registry__caches[cache.cache_name][key]
            except (KeyError, AttributeError, TypeError):
                pass
        # 2. cache miss: reuse the request transaction when possible
        env = _request_env(dbname)
        if env is not None:
            return env[_MODEL].sudo()._get_code_overrides(category, module_name, lang)
        # 3. no request (cron, queue job, shell, ...): short lived cursor
        with registry.cursor(readonly=True) as cr:
            env = api.Environment(cr, api.SUPERUSER_ID, {})
            return env[_MODEL]._get_code_overrides(category, module_name, lang)
    except Exception:  # noqa: BLE001 - a translation must never break the caller
        _logger.warning('Could not read the translation overrides (%s, %s, %s).',
                        category, module_name, lang, exc_info=True)
        return None
    finally:
        _local.busy = False


def _patch():
    CodeTranslations = translate_tools.CodeTranslations
    if getattr(CodeTranslations.get_python_translations, _PATCH_FLAG, False):
        return  # already patched (module imported twice)
    original = CodeTranslations.get_python_translations

    def get_python_translations(self, module_name, lang):
        translations = original(self, module_name, lang)
        overrides = _lookup('code', module_name, lang)
        if overrides:
            # cheap read-only merged view, the cached original stays untouched
            return ChainMap(overrides, translations)
        return translations

    setattr(get_python_translations, _PATCH_FLAG, True)
    get_python_translations.__wrapped__ = original
    CodeTranslations.get_python_translations = get_python_translations


_patch()
