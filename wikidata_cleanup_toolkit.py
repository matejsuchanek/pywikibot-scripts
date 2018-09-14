# -*- coding: utf-8 -*-
import pywikibot

from pywikibot import html2unicode
from pywikibot.tools import first_lower
from pywikibot.tools.chars import invisible_regex


class DataWrapper(dict):

    def __init__(self, read, write):
        self.read = read
        self.write = write
        read.update(write)
        super(DataWrapper, self).__init__(read)

    def __delitem__(self, key):
        del self.read[key]
        del self.write[key]
        return super(DataWrapper, self).__delitem__(key)

    def __getitem__(self, key):
        return super(DataWrapper, self).__getitem__(key)

    def __setitem__(self, key, value):
        self.read[key] = value
        self.write[key] = value
        return super(DataWrapper, self).__setitem__(key, value)

    def update(self, data):
        self.read.update(data)
        self.write.update(data)
        return super(DataWrapper, self).update(data)


class WikidataCleanupToolkit(object):

    lang_map = {
        'als': 'gsw',
        'bat-smg': 'sgs',
        'be-x-old': 'be-tarask',
        'bh': 'bho',
        'commons': None,
        'fiu-vro': 'vro',
        'media': None,
        'meta': 'en',
        'no': 'nb',
        'roa-rup': 'rup',
        'simple': 'en',
        'species': 'en',
        'wikidata': None,
        'zh-classical': 'lzh',
        'zh-min-nan': 'nan',
        'zh-yue': 'yue',
    }

    def __init__(self, fixes=[]):
        self.fixes = set(fixes)

    def cleanup(self, item, data=None):
        # todo: unify
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
        for key in ['labels', 'descriptions', 'aliases']:
            terms[key] = DataWrapper(
                getattr(item, key), data.setdefault(key, {}))
        ret = False
        ret = self.exec_fix('fix_languages', terms) or ret
        #ret = self.exec_fix('deduplicate_aliases', terms) or ret
        #ret = self.exec_fix('move_alias_to_label', terms) or ret
        ret = self.exec_fix('add_missing_labels', item, terms['labels']) or ret
        ret = self.exec_fix('cleanup_labels', terms) or ret
        ret = self.exec_fix('fix_HTML', terms) or ret
        #ret = self.exec_fix('replace_invisible', terms) or ret
        ret = self.exec_fix(
            'fix_quantities', item.claims, data.setdefault('claims', [])) or ret
        return ret

    def cleanup_entity(self, item):
        terms = self._get_terms(item)
        ret = False
        ret = self.exec_fix('fix_languages', terms) or ret
        #ret = self.exec_fix('deduplicate_aliases', terms) or ret
        #ret = self.exec_fix('move_alias_to_label', terms) or ret
        ret = self.exec_fix('add_missing_labels', item, terms['labels']) or ret
        ret = self.exec_fix('cleanup_labels', terms) or ret
        ret = self.exec_fix('fix_HTML', terms) or ret
        #ret = self.exec_fix('replace_invisible', terms) or ret
        ret = self.exec_fix('fix_quantities', item.claims, []) or ret  # dummy
        return ret

    def move_alias_to_label(self, terms):  # todo
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

    def deduplicate_aliases(self, data):  # todo
        ret = False
        for lang, aliases in data['aliases'].items():
            already = set()
            label = data['labels'].get(lang)
            for alias in aliases[:]:
                if alias == label or alias in already:
                    aliases.remove(alias)
                    ret = True
                already.add(alias)
        return ret

    @classmethod
    def normalize_lang(cls, lang):
        lang = lang.replace('_', '-')
        return cls.lang_map.get(lang, lang)

    def fix_languages(self, data):
        ret = False
        for lang, norm in self.lang_map.items():
            label = data['labels'].get(lang)
            if not label:
                continue
            if norm in data['labels']:
                data['aliases'].setdefault(norm, []).append(label)
            else:
                data['labels'][norm] = label
            data['labels'][lang] = ''
            ret = True
        for lang, norm in self.lang_map.items():
            description = data['descriptions'].get(lang)
            if description:
                if norm not in data['descriptions']:
                    data['descriptions'][norm] = description
                data['descriptions'][lang] = ''
                ret = True
##        for lang, norm in self.lang_map.items():  # fixme: T194512
##            aliases = data['aliases'].get(lang)
##            if aliases:
##                data['aliases'].setdefault(norm, []).extend(aliases)
##                ret = True
        for lang, aliases in data['aliases'].items():
            for alias in aliases:
                if alias not in data['aliases'].get(lang, []):
                    data['aliases'].setdefault(lang, []).append(alias)
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
                label = labels.get(lang)
                if label and first_lower(label) != first_lower(title):
                    labels.pop(lang)  # todo: better handling
                    dont.add(lang)
                    continue
                labels[lang] = title
        return labels

    def add_missing_labels(self, item, data):
        labels = self.get_missing_labels(item, set(data.keys()))
        data.update(labels)
        return bool(labels)

    @staticmethod
    def can_strip(part, description):
        if part not in description:  # todo: word to word, not just substring
            for sub in part.split(', '):
                if sub not in description:
                    return False
        return True

    def cleanup_labels(self, terms):
        ret = False
        for lang, label in terms['labels'].items():
            description = terms['descriptions'].get(lang)
            if not description:
                continue
            left, sep, right = label.rstrip(')').rpartition(' (')
            if not sep:
                left, sep, right = label.partition(', ')
                if right.isdigit():
                    sep = False
            if sep and not (set(left) & set('(:)')):
                if self.can_strip(right, description):
                    terms['labels'][lang] = left.strip()
                    ret = True
        return ret

    def fix_HTML(self, terms):
        ret = False
        for key in ['labels', 'descriptions']:
            for lang, value in terms[key].items():
                new = html2unicode(value)
                if new != value:
                    terms[key][lang] = new
                    ret = True
        return ret

    def replace_invisible(self, terms):  # fixme: really all of them?
        ret = False
        for key in ['labels', 'descriptions']:
            for lang, value in terms[key].items():
                new = invisible_regex.sub('', value)
                if new != value:
                    terms[key][lang] = new
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
