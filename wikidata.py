# -*- coding: utf-8 -*-
import pywikibot

from pywikibot.bot import Bot, NoRedirectPageBot, WikidataBot

class WikidataEntityBot(WikidataBot, NoRedirectPageBot):

    '''
    Bot editing Wikidata entities
    Features:
    * Caches properties so that iterating claims can be faster
    * Wraps around WikibataBot class.

    Planned:
    * Item cleanup like missing and wrong labels etc.
    '''

    cc = True
    lang_map = {
        'als': 'gsw',
        'be-x-old': 'be-tarask',
        'bh': 'bho',
        'no': 'nb',
        'simple': None,
        'zh-classical': 'lzh',
        'zh-min-nan': 'nan',
        'zh-yue': 'yue',
    }

    def __init__(self, **kwargs):
        self.bad_cache = set(kwargs.pop('bad_cache', []))
        self.good_cache = set(kwargs.pop('good_cache', []))
        super(WikidataEntityBot, self).__init__(**kwargs)

    def init_page(self, item):
        super(WikidataEntityBot, self).init_page(item)
        try:
            item.get()
        except (pywikibot.NoPage, pywikibot.IsRedirectPage):
            pass

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

    def _save_entity(self, func, *args, **kwargs):
        if not kwargs.pop('async_force', False) and 'asynchronous' in kwargs:
            kwargs.pop('asynchronous')
        func(*args, **kwargs)

    def _move_alias_to_label(self, item, data):
        labels = {}
        aliases = {}
        keys = set(item.aliases.keys())
        keys -= set(item.labels.keys())
        keys -= set(item.descriptions.keys())
        keys -= set(data.get('labels', {}).keys())
        for lang in keys:
            if len(item.aliases[lang]) == 1:
                labels[lang] = item.aliases[lang][0]
                aliases[lang] = {'language': lang, 'remove': '',
                                 'value': item.aliases[lang][0]}
        if labels and aliases:
            data['labels'].update(labels)
            data['aliases'].update(aliases)

    def _add_missing_labels(self, item, data):
        labels = {}
        dont = set(item.descriptions.keys()) | set(data.get('labels', {}).keys())
        for dbname, title in item.sitelinks.items():
            parts = dbname.partition('wiki')
            if parts[0] in ('commons', 'wikidata', 'species', 'media', 'meta'):
                continue
            lang = self.lang_map.get(parts[0], parts[0])
            if lang and lang not in dont:
                if lang in labels:
                    dont.add(lang)
                    labels.pop(lang)
                else:
                    labels[lang] = title.partition(' (')[0]
        if labels:
            data.setdefault('labels', {}).update(labels)

    def _fix_quantities(self, item, data):
        for prop, claims in item.claims.items():
            for claim in claims:
                if claim.type != 'quantity':
                    break
                target = claim.getTarget()
                if not target:
                    continue
        #TODO

    def user_edit_entity(self, item, data, **kwargs):
        if self.cc and hasattr(item, 'labels'):
            self._move_alias_to_label(item, data)
        if self.cc and hasattr(item, 'sitelinks'):
            self._add_missing_labels(item, data)
        if self.cc and hasattr(item, 'claim'):
            self._fix_quantities(item, data)
        kwargs.setdefault('show_diff', False)
        return super(WikidataEntityBot, self).user_edit_entity(
            item, data, **kwargs)

    def treat(self, page):
        self.current_page = page
        self.treat_page()

    def run(self):
        Bot.run(self)
