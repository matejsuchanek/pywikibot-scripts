# -*- coding: utf-8 -*-
import pywikibot

from pywikibot import html2unicode
from pywikibot.tools import first_lower
from pywikibot.tools.chars import invisible_regex


class DataWrapper(dict):

    def __init__(self, read, write):
        self.write = write
        read.update(write)
        super(DataWrapper, self).__init__(read)

    def __delitem__(self, key):
        del self.write[key]
        super(DataWrapper, self).__delitem__(key)

    def __setitem__(self, key, value):
        self.write[key] = value
        super(DataWrapper, self).__setitem__(key, value)

    def update(self, *args, **kwargs):
        self.write.update(*args, **kwargs)
        return super(DataWrapper, self).update(*args, **kwargs)

    def setdefault(self, *args):
        self.write.setdefault(*args)
        return super(DataWrapper, self).setdefault(*args)


class WikidataCleanupToolkit(object):

    lang_map = {
        'als': 'gsw',
        'bat-smg': 'sgs',
        'be-x-old': 'be-tarask',
        'bh': 'bho',
        'commons': None,
        'de-formal': 'de',
        'es-formal': 'es',
        'fiu-vro': 'vro',
        'hu-formal': 'hu',
        'media': None,
        'meta': 'en',
        'nl-informal': 'nl',
        'no': 'nb',
        'roa-rup': 'rup',
        'simple': 'en',
        'species': 'en',
        'tokipona': None,
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
                'aliases': item.aliases,
                'sitelinks': item.sitelinks}

    def cleanup_data(self, item, data):
        terms = {}
        keys = ('labels', 'descriptions', 'aliases', 'sitelinks')
        for key in keys:
            terms[key] = DataWrapper(
                getattr(item, key), data.setdefault(key, {}))
        ret = False
        ret = self.exec_fix('fix_languages', terms) or ret
        ret = self.exec_fix('deduplicate_aliases', terms) or ret
        #ret = self.exec_fix('move_alias_to_label', terms) or ret
        ret = self.exec_fix('add_missing_labels',
                            terms['sitelinks'], terms['labels']) or ret
        ret = self.exec_fix('cleanup_labels', terms) or ret
        ret = self.exec_fix('fix_HTML', terms) or ret
        #ret = self.exec_fix('replace_invisible', terms) or ret
        ret = self.exec_fix(
            'fix_quantities', item.claims, data.setdefault('claims', [])) or ret
        for key in keys:
            if not data[key]:
                data.pop(key)
        return ret

    def cleanup_entity(self, item):
        terms = self._get_terms(item)
        ret = False
        ret = self.exec_fix('fix_languages', terms) or ret
        ret = self.exec_fix('deduplicate_aliases', terms) or ret
        #ret = self.exec_fix('move_alias_to_label', terms) or ret
        ret = self.exec_fix('add_missing_labels',
                            terms['sitelinks'], terms['labels']) or ret
        ret = self.exec_fix('cleanup_labels', terms) or ret
        ret = self.exec_fix('fix_HTML', terms) or ret
        #ret = self.exec_fix('replace_invisible', terms) or ret
        ret = self.exec_fix('fix_quantities', item.claims, []) or ret  # dummy
        return ret

    def move_alias_to_label(self, terms):  # todo: not always desired
        ret = False
        for lang, aliases in terms['aliases'].items():
            if len(aliases) == 1:
                terms['aliases'][lang] = []
                terms['labels'][lang] = aliases.pop()
                ret = True
        return ret

    def deduplicate_aliases(self, data):
        ret = False
        for lang, aliases in data['aliases'].items():
            already = set()
            label = data['labels'].get(lang)
            if label:
                already.add(label)
            for alias in aliases[:]:
                if alias in already:
                    aliases.remove(alias)
                    ret = True
                else:
                    already.add(alias)
            data['aliases'][lang] = aliases
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
            if norm:
                if norm in data['labels']:
                    aliases = data['aliases'].get(norm, [])
                    if label not in map(first_lower, aliases):
                        aliases.append(label)
                        data['aliases'][norm] = aliases
                else:
                    data['labels'][norm] = label
            data['labels'][lang] = ''
            ret = True
        for lang, norm in self.lang_map.items():
            description = data['descriptions'].get(lang)
            if description:
                if norm and norm not in data['descriptions']:
                    data['descriptions'][norm] = description
                data['descriptions'][lang] = ''
                ret = True
        for lang, norm in self.lang_map.items():
            old_aliases = data['aliases'].get(lang)
            if old_aliases:
                if norm:
                    new_aliases = data['aliases'].get(norm, [])
                    already = set(map(first_lower, new_aliases))
                    if norm in data['labels']:
                        already.add(first_lower(data['labels'][norm]))
                    for alias in old_aliases:
                        if alias not in already:
                            new_aliases.append(alias)
                            already.add(alias)
                    data['aliases'][norm] = new_aliases
                data['aliases'][lang] = []
                ret = True
        return ret

    def get_missing_labels(self, sitelinks, dont):
        labels = {}
        for dbname, title in sitelinks.items():
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

    def add_missing_labels(self, sitelinks, data):
        labels = self.get_missing_labels(sitelinks, set(data.keys()))
        data.update(labels)
        return bool(labels)

    @staticmethod
    def can_strip(part, description):
        words = {  # [[d:Topic:Uljziilm6l85hsp3]]
            'vrouwen', 'mannen', 'jongens', 'meisjes', 'enkel', 'dubbel',
            'mannenenkel', 'vrouwenenkel', 'jongensenkel', 'meisjesenkel',
            'mannendubbel', 'vrouwendubbel', 'jongensdubbel', 'meisjesdubbel',
        }
        if part.isdigit() or part in words:
            return False
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
        for claims in all_claims.values():
            for claim in claims:
                ret = self.fix_quantity(claim)
                for snaks in claim.qualifiers.values():
                    for snak in snaks:
                        ret = self.fix_quantity(snak) or ret
                if ret:
                    yield claim

    def fix_quantities(self, claims, data):
        ret = False
        for claim in self.iter_fixed_quantities(claims):
            data.append(claim.toJSON())
            ret = True
        return ret
