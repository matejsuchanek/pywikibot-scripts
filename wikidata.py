# -*- coding: utf-8  -*-
import pywikibot

from pywikibot.bot import (
    ExistingPageBot,
    NoRedirectPageBot,
    SkipPageError,
    SingleSiteBot,
    WikidataBot,
)

class WikidataEntityBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):

    '''
    Bot editing Wikidata entities
    Features:
    * Works around [[phab:T86074]]
    * Caches properties so that iterating claims can be faster
    * Hacks into WikidataBot and fetches sources

    Planned:
    * Item cleanup like missing and wrong labels etc.
    '''

    def __init__(self, **kwargs):
        pywikibot.output("Please help fix [[phab:T86074]] to make Wikidata scripts simpler")
        self.bad_cache = set(kwargs.pop('bad_cache', []))
        self.good_cache = set(kwargs.pop('good_cache', []))
        super(WikidataEntityBot, self).__init__(**kwargs)
        self.repo = self.site.data_repository()

    def init_page(self, item): # fixme: neccessary (cf. superclasses)?
        try:
            item.get()
        except pywikibot.IsRedirectPage:
            raise SkipPageError(
                item,
                "Redirect item"
            )
        except pywikibot.NoPage:
            raise SkipPageError(
                item,
                "Item doesn't exist"
            )

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
            "%s.filterProperty needs overriding in a subclass" % self.__class__
        )

    def _save_entity(self, func, *args, **kwargs):
        if 'async' in kwargs:
            kwargs.pop('async') # fixme: T86074
        func(*args, **kwargs)

    def getSource(self):
        if not hasattr(self, 'source'):
            self.source = WikidataBot().getSource(self.site)
        return self.source
