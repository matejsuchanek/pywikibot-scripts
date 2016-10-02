# -*- coding: utf-8  -*-
import pywikibot

from pywikibot.bot import (
    SkipPageError, SingleSiteBot, ExistingPageBot, NoRedirectPageBot, WikidataBot
)

class WikidataEntityBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):

    '''
    Bot editing Wikidata entities
    Features:
    * Works around [[phab:T86074]]
    * Caches properties so that iterating claims is faster
    * Hacks into WikidataBot and gets sources

    Planned:
    * Item cleanup like missing and wrong labels etc.
    '''

    def __init__(self, site, **kwargs):
        pywikibot.output("Please help fix [[phab:T86074]] to make Wikidata scripts simpler")
        self.bad_cache = kwargs.pop('bad_cache', [])
        self.good_cache = kwargs.pop('good_cache', [])
        super(WikidataEntityBot, self).__init__(site, **kwargs)
        self.repo = site.data_repository()

    def init_page(self, item):
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
            self.good_cache.append(prop)
        else:
            self.bad_cache.append(prop)

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
            wd_bot = WikidataBot()
            self.source = wd_bot.getSource(self.site)
        return self.source
