from contextlib import suppress

import pywikibot

from pywikibot.bot import NoRedirectPageBot, WikidataBot

from .wikidata_cleanup_toolkit import WikidataCleanupToolkit


class WikidataEntityBot(WikidataBot, NoRedirectPageBot):

    '''
    Bot editing Wikidata entities
    Features:
    * Caches properties so that iterating claims can be faster
    * Wraps around WikibataBot class.
    * Item cleanup like missing labels, redundant data etc.
    '''

    def __init__(self, **kwargs):
        self.available_options.update({
            'nocleanup': False,
        })
        self.bad_cache = set(kwargs.pop('bad_cache', []))
        self.good_cache = set(kwargs.pop('good_cache', []))
        self.kit = WikidataCleanupToolkit()
        super().__init__(**kwargs)

    def init_page(self, item):
        with suppress(pywikibot.NoPage, pywikibot.IsRedirectPage):
            item.get()
        return super().init_page(item)

    def checkProperty(self, prop):
        if prop in self.good_cache:
            return True
        if prop in self.bad_cache:
            return False

        self.cacheProperty(prop)
        return self.checkProperty(prop)

    def cacheProperty(self, prop):
        prop_page = pywikibot.PropertyPage(self.repo, prop)
        if self.filterProperty(prop_page):
            self.good_cache.add(prop)
        else:
            self.bad_cache.add(prop)

    def filterProperty(self, prop_page):
        raise NotImplementedError(
            '%s.filterProperty needs overriding in a subclass' % self.__class__
        )

    def user_edit_entity(self, item, data=None, *, cleanup=None, **kwargs):
        # todo: support stub items
        if item.exists() and not (cleanup is False or (
                self.opt['nocleanup'] and cleanup is not True)):
            if self.kit.cleanup(item, data):
                if kwargs.get('summary'):
                    kwargs['summary'] += '; cleanup'
                else:
                    kwargs['summary'] = 'cleanup'
        kwargs.setdefault('show_diff', not self.opt['always'])
        return super().user_edit_entity(item, data, **kwargs)
