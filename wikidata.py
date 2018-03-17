# -*- coding: utf-8 -*-
import pywikibot

from pywikibot.bot import NoRedirectPageBot, WikidataBot

class WikidataEntityBot(WikidataBot, NoRedirectPageBot):

    '''
    Bot editing Wikidata entities
    Features:
    * Caches properties so that iterating claims can be faster
    * Wraps around WikibataBot class.
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
            data.setdefault('aliases', {}).update(aliases)
        return bool(labels) and bool(aliases)

    def _add_missing_labels(self, item, data):
        labels = {}
        dont = set(item.descriptions.keys()) | set(item.labels.keys())
        dont |= set(data.get('labels', {}).keys())
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
            pywikibot.output(labels)
        return bool(labels)

    def _fix_quantities(self, item, data):
        all_claims = set()
        for prop, claims in item.claims.items():
            for claim in claims:
                if claim.type == 'quantity' and claim.snaktype == 'value':
                    if claim.target.upperBound == claim.target.amount:
                        claim.target.upperBound = None
                        claim.target.lowerBound = None
                        all_claims.add(claim)
                for qprop, snaks in claim.qualifiers.items():
                    for snak in snaks:
                        if snak.type == 'quantity' and snak.snaktype == 'value':
                            if snak.target.upperBound == snak.target.amount:
                                snak.target.upperBound = None
                                snak.target.lowerBound = None
                                all_claims.add(claim)
        if all_claims:
            data.setdefault('claims', []).extend(
                cl.toJSON() for cl in all_claims)
        return bool(all_claims)

    def user_edit_entity(self, item, data=None, **kwargs):
        if data:
            cleanup = False
            if self.cc and hasattr(item, 'labels'):
                cleanup = self._move_alias_to_label(item, data) or cleanup
            if self.cc and hasattr(item, 'sitelinks'):
                cleanup = self._add_missing_labels(item, data) or cleanup
            if self.cc and hasattr(item, 'claims'):
                cleanup = self._fix_quantities(item, data) or cleanup
            kwargs.setdefault('show_diff', False)
            if cleanup and kwargs.get('summary'):
                kwargs['summary'] += '; cleanup'
        return super(WikidataEntityBot, self).user_edit_entity(
            item, data, **kwargs)
