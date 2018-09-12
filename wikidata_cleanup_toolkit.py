# -*- coding: utf-8 -*-
import pywikibot

from pywikibot import html2unicode
from pywikibot.tools import first_lower
from pywikibot.tools.chars import invisible_regex


class WikidataCleanupToolkit(object):

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

    def __init__(self, fixes=[]):
        self.fixes = set(fixes)

    def cleanup(self, item, data=None):
        if data is not None:
            return self.cleanup_data(item, data)
        else:
            return self.cleanup_entity(item)

    def exec_fix(self, fix, *args, **kwargs):
        ret = False
        if not self.fixes or fix in self.fixes:
            handler = getattr(self, fix)
            ret = handler(*args, **kwargs)
        return ret

    def _get_terms(self, item):
        return {'labels': item.labels,
                'descriptions': item.descriptions,
                'aliases': item.aliases}

    def cleanup_data(self, item, data):
        terms = {}
        all_terms = self._get_terms(item)
        for key in ['labels', 'descriptions', 'aliases']:
            data.setdefault(key, {})
            terms[key] = data[key]
            all_terms[key].update(data[key])
        ret = False
        ret = self.exec_fix('fix_languages', terms) or ret
        #ret = self.exec_fix('move_alias_to_label') or ret
        ret = self.exec_fix('add_missing_labels', item, data['labels'],
                            set(item.labels)) or ret
        ret = self.exec_fix('cleanup_labels', item, data['labels'],
                            set(data['labels'])) or ret
        ret = self.exec_fix('fix_HTML', terms, all_terms) or ret
        #ret = self.exec_fix('replace_invisible', terms, all_terms) or ret
        ret = self.exec_fix('fix_quantities', item.claims,
                            data.setdefault('claims', [])) or ret
        return ret

    def cleanup_entity(self, item):
        terms = self._get_terms(item)
        ret = False
        ret = self.exec_fix('fix_languages', terms) or ret
        #ret = self.exec_fix('move_alias_to_label') or ret
        ret = self.exec_fix('add_missing_labels', item, item.labels) or ret
        ret = self.exec_fix('cleanup_labels', item, item.labels) or ret
        ret = self.exec_fix('fix_HTML', terms, terms) or ret
        #ret = self.exec_fix('replace_invisible', terms, terms) or ret
        ret = self.exec_fix('fix_quantities', item.claims, []) or ret  # dummy
        return ret

    def move_alias_to_label(self, item, data):  # todo
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
                    'language': lang, 'value': item.aliases[lang][0],
                    'remove': ''}  # fixme: T194512
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

    def fix_languages(self, terms):
        ret = False
        for lang, norm in self.lang_map.items():
            label = terms['labels'].get(lang)
            if not label:
                continue
            if norm in terms['labels']:
                terms['aliases'].setdefault(norm, []).append(label)
            else:
                terms['labels'][norm] = label
            terms['labels'][lang] = ''
            ret = True
        for lang, norm in self.lang_map.items():
            description = terms['descriptions'].get(lang)
            if description:
                if norm not in terms['descriptions']:
                    terms['descriptions'][norm] = description
                terms['descriptions'][lang] = ''
                ret = True
##        for lang, norm in self.lang_map.items():  # fixme: T194512
##            aliases = terms['aliases'].get(lang)
##            if aliases:
##                terms['aliases'].setdefault(norm, []).extend(aliases)
##                ret = True
        for lang, aliases in terms['aliases'].items():
            for alias in aliases:
                if alias not in terms['aliases'].get(lang, []):
                    terms['aliases'].setdefault(lang, []).append(alias)
        return ret

    def get_missing_labels(self, item, dont):
        labels = {}
        for dbname, title in item.sitelinks.items():  # todo: impr. dependency
            has_colon = ':' in title
            if not has_colon and '/' in title:
                continue
            parts = dbname.partition('wik')
            lang = self.normalize_lang(parts[0])
            if lang and lang not in dont:
                if lang in labels:
                    labels.pop(lang)  # todo: better handling
                    dont.add(lang)
                    continue
                if not has_colon:  # todo: refact. with get_labels_to_update
                    if title.endswith(')'):
                        left, sep, right = title.rpartition(' (')
                        if left and not (set(left) & set('(:)')):
                            title = left
                # [[d:Topic:Uhdjlv9aae6iijuc]]
                # todo: create a lib for this
                if lang == 'fr' and title.startswith(
                        ('Abbaye ', 'Cathédrale ', 'Chapelle ', 'Cloître ',
                         'Couvent ', 'Monastère ', 'Église ')):
                    title = first_lower(title)
                labels[lang] = title
        return labels

    def add_missing_labels(self, item, data, skip=set()):
        labels = self.get_missing_labels(item, skip | set(data.keys()))
        data.update(labels)
        return bool(labels)

    @staticmethod
    def can_strip(part, description):
        if part not in description:  # todo: word to word, not just substring
            for sub in part.split(', '):
                if sub not in description:
                    return False
        return True

    def get_labels_to_update(self, item, skip):
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
                if right.isdigit():
                    sep = False
            if sep and not (set(left) & set('(:)')):
                if self.can_strip(right, description):
                    labels[lang] = left.strip()
        return labels

    def cleanup_labels(self, item, data, skip=set()):
        labels = self.get_labels_to_update(item, skip)
        data.update(labels)
        return bool(labels)

    def fix_HTML(self, data, terms):
        ret = False
        for key in ['labels', 'descriptions']:
            for lang, value in terms[key].items():
                new = html2unicode(value)
                if new != value:
                    terms[key][lang] = data[key][lang] = new
                    ret = True
        return ret

    def replace_invisible(self, data, terms):
        ret = False
        for key in ['labels', 'descriptions']:
            for lang, value in terms[key].items():
                new = invisible_regex.sub('', value)
                if new != value:
                    terms[key][lang] = data[key][lang] = new
                    ret = True
        return ret

    def fix_quantity(self, snak):
        if snak.type == 'quantity' and snak.snaktype == 'value':
            if snak.target.upperBound == snak.target.amount:
                snak.target.upperBound = None
                snak.target.lowerBound = None
                return True
        return False

    def iter_fixed_quantities(self, all_claims):
        for prop, claims in all_claims.items():
            for claim in claims:
                if self.fix_quantity(claim):
                    yield claim
                for qprop, snaks in claim.qualifiers.items():
                    for snak in snaks:
                        if self.fix_quantity(snak):
                            yield claim

    def fix_quantities(self, claims, data):
        fixed = set(self.iter_fixed_quantities(claims))
        data.extend(claim.toJSON() for claim in fixed)
        return bool(fixed)
