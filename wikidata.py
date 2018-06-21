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
        'commons': None,
        'fiu_vro': 'vro',
        'media': None,
        'meta': 'en',
        'no': 'nb',
        'roa_rup': 'rup',
        'simple': None,
        'species': 'en',
        'wikidata': None,
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
            return False  # fixme: T194512
        labels = {}
        aliases = {}
        keys = set(item.aliases.keys())
        keys -= set(item.labels.keys())
        keys -= set(item.descriptions.keys())
        keys -= set(data.get('labels', {}).keys())
        for lang in keys:
            if len(item.aliases[lang]) == 1:
                labels[lang] = item.aliases[lang][0]
                aliases[lang] = {
                    'language': lang, 'remove': '',
                    'value': item.aliases[lang][0]}  # fixme: T194512
        if labels and aliases:
            data.setdefault('labels', {}).update(labels)
            data.setdefault('aliases', {}).update(aliases)
        return bool(labels) and bool(aliases)

    @classmethod
    def normalize_lang(cls, lang):
        lang = cls.lang_map.get(lang, lang)
        if lang:
            return lang.replace('_', '-')
        else:
            return None

    def _get_missing_labels(self, item, skip):
        labels = {}
        dont = set(item.labels.keys()) | set(skip)
        for dbname, title in item.sitelinks.items():
            has_colon = ':' in title
            if not has_colon and '/' in title:
                continue
            parts = dbname.partition('wik')
            lang = self.normalize_lang(parts[0])
            if lang and lang not in dont:
                if lang in labels:
                    dont.add(lang)
                    labels.pop(lang)
                    continue
                if not has_colon:  # todo: refact. with _get_labels_to_update
                    if title.endswith(')'):
                        left, sep, right = title.rpartition(' (')
                        if left and not (set(left) & set('(:)')):
                            title = left
                labels[lang] = title
        return labels

    def _fix_languages(self, item, data):
        ret = False
        terms = {'labels': {}, 'descriptions': {}, 'aliases': {}}
        if hasattr(item, 'labels'):
            for lang, norm in self.lang_map.items():
                label = item.labels.get(lang)
                if not label:
                    continue
                if norm in item.labels:
                    terms['aliases'].setdefault(norm, []).append(label)
                else:
                    terms['labels'][norm] = label
                terms['labels'][lang] = ''
                ret = True
        if hasattr(item, 'descriptions'):
            for lang, norm in self.lang_map.items():
                description = item.descriptions.get(lang)
                if description:
                    if norm not in item.descriptions:
                        terms['descriptions'][norm] = description
                    terms['descriptions'][lang] = ''
                    ret = True
##        if hasattr(item, 'aliases'):  # fixme: T194512
##            for lang, norm in self.lang_map.items():
##                aliases = item.aliases.get(lang)
##                if aliases:
##                    terms['aliases'].setdefault(norm, []).extend(aliases)
##                    ret = True
        if data is None:
            cur_labels = item.labels
            cur_descriptions = item.descriptions
            cur_aliases = item.aliases
        else:
            cur_labels = data.setdefault('labels', {})
            cur_descriptions = data.setdefault('descriptions', {})
            cur_aliases = data.setdefault('aliases', {})
        cur_labels.update(terms['labels'])
        cur_descriptions.update(terms['descriptions'])
        for lang, aliases in terms['aliases'].items():
            for alias in aliases:
                if alias not in cur_aliases.get(lang, []):
                    cur_aliases.setdefault(lang, []).append(alias)
        return ret

    def _add_missing_labels(self, item, data):
        if data is None:
            skip = set()
        else:
            skip = set(data.get('labels', {}).keys())
        labels = self._get_missing_labels(item, skip)
        if labels:
            if data is None:
                for lang, label in labels.items():
                    item.labels[lang] = label
            else:
                data.setdefault('labels', {}).update(labels)
        return bool(labels)

    @staticmethod
    def can_strip(part, description):
        if part not in description:  # todo: word to word, not just substring
            for sub in part.split(', '):
                if sub not in description:
                    return False
        return True

    def _get_labels_to_update(self, item, skip):
        labels = {}
        for lang, label in item.labels.items():
            if lang in skip:
                continue
            description = item.descriptions.get(lang)
            if not description:
                continue
            left, sep, right = label.rstrip(')').rpartition(' (')
            if not sep:
                left, sep, right = label.partition(', ')
            if sep and not (set(left) & set('(:)')):
                if self.can_strip(right, description):
                    labels[lang] = left.strip()
        return labels

    def _clean_up_labels(self, item, data):
        if data is None:
            skip = set()
        else:
            skip = set(data.get('labels', {}).keys())
        labels = self._get_labels_to_update(item, skip)
        if labels:
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
        all_claims = set()
        for prop, claims in item.claims.items():
            for claim in claims:
                if self._fix_quantity(claim):
                    all_claims.add(claim)
                for qprop, snaks in claim.qualifiers.items():
                    for snak in snaks:
                        if self._fix_quantity(snak):
                            all_claims.add(claim)
        if data is not None and all_claims:
            data.setdefault('claims', []).extend(
                cl.toJSON() for cl in all_claims)
        return bool(all_claims)

    def user_edit_entity(self, item, data=None, **kwargs):
        cleanup = False
        if self.cc:
            cleanup = self._fix_languages(item, data) or cleanup
        if self.cc and hasattr(item, 'labels'):
            pass  # cleanup = self._move_alias_to_label(item, data) or cleanup
        if self.cc and hasattr(item, 'sitelinks'):
            cleanup = self._add_missing_labels(item, data) or cleanup
        if self.cc and hasattr(item, 'labels'):
            cleanup = self._clean_up_labels(item, data) or cleanup
        if self.cc and hasattr(item, 'claims'):
            cleanup = self._fix_quantities(item, data) or cleanup
        if cleanup and kwargs.get('summary'):
            kwargs['summary'] += '; cleanup'
        kwargs.setdefault('show_diff', False)
        return super(WikidataEntityBot, self).user_edit_entity(
            item, data, **kwargs)
