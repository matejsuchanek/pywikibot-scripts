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
        'bat_smg': 'sgs',
        'be_x_old': 'be-tarask',
        'bh': 'bho',
        'fiu_vro': 'vro',
        'no': 'nb',
        'roa_rup': 'rup',
        'simple': None,
        'zh_classical': 'lzh',
        'zh_min_nan': 'nan',
        'zh_yue': 'yue',
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

    def _move_alias_to_label(self, item, data):
        if data is None:
            return False
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
            data.setdefault('labels', {}).update(labels)
            data.setdefault('aliases', {}).update(aliases)
        return bool(labels) and bool(aliases)

    def normalize_lang(self, lang):
        lang = self.lang_map.get(lang, lang)
        if lang:
            return lang.replace('_', '-')
        else:
            return None

    def _get_missing_labels(self, item, skip):
        labels = {}
        dont = set(item.descriptions.keys()) | set(item.labels.keys())
        dont |= set(skip)
        for dbname, title in item.sitelinks.items():
            parts = dbname.partition('wik')
            if parts[0] in ('commons', 'wikidata', 'species', 'media', 'meta'):
                continue
            if set(title) & set(',:'):
                continue
            lang = self.normalize_lang(parts[0])
            if lang and lang not in dont:
                if lang in labels:
                    dont.add(lang)
                    labels.pop(lang)
                else:
                    labels[lang] = title.partition(' (')[0]
        return labels

    def _fix_languages(self, item, data):
        ret = False
##        if hasattr(item, 'labels'):
##            data.setdefault('labels', {})
##        if hasattr(item, 'descriptions'):
##            data.setdefault('descriptions', {})
        return ret

    def _add_missing_labels(self, item, data):
        if data is None:
            skip = set()
        else:
            skip = set(data.get('labels', {}).keys())
        labels = self._get_missing_labels(item, skip)
        if labels:
            #print(list(labels.keys()))
            if data is None:
                for lang, label in labels.items():
                    item.labels[lang] = label
            else:
                data.setdefault('labels', {}).update(labels)
        return bool(labels)

    def _fix_quantity(self, snak):
        if snak.type == 'quantity' and snak.snaktype == 'value':
            if snak.target.upperBound == snak.target.amount:
                snak.target.upperBound = None
                snak.target.lowerBound = None
                return True
        return False

    def _fix_quantities(self, item, data):
        if data is None:
            return False
        all_claims = set()
        for prop, claims in item.claims.items():
            for claim in claims:
                if self._fix_quantity(claim):
                    all_claims.add(claim)
                for qprop, snaks in claim.qualifiers.items():
                    for snak in snaks:
                        if self._fix_quantity(snak):
                            all_claims.add(claim)
        if all_claims:
            data.setdefault('claims', []).extend(
                cl.toJSON() for cl in all_claims)
        return bool(all_claims)

    def user_edit_entity(self, item, data=None, **kwargs):
        cleanup = False
        if self.cc:
            cleanup = self._fix_languages(item, data) or cleanup
        if self.cc and hasattr(item, 'labels'):
            cleanup = self._move_alias_to_label(item, data) or cleanup
        if self.cc and hasattr(item, 'sitelinks'):
            cleanup = self._add_missing_labels(item, data) or cleanup
        if self.cc and hasattr(item, 'claims'):
            cleanup = self._fix_quantities(item, data) or cleanup
        if cleanup and kwargs.get('summary'):
            kwargs['summary'] += '; cleanup'
        kwargs.setdefault('show_diff', False)
        return super(WikidataEntityBot, self).user_edit_entity(
            item, data, **kwargs)
