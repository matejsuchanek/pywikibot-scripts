from itertools import chain

import pywikibot

from pywikibot import Claim, html2unicode, SiteLink, WbMonolingualText
from pywikibot.backports import removesuffix
from pywikibot.exceptions import UnknownSiteError
from pywikibot.tools import first_lower, first_upper
from pywikibot.tools.chars import INVISIBLE_REGEX as invisible_regex


class EntityDataWrapper:

    def __init__(self, entity):
        self.entity = entity

    def get_label(self, lang: str):
        return self.entity.labels.get(lang)

    def set_label(self, lang: str, value: str):
        self.entity.labels[lang] = value

    def iter_labels(self):
        for lang, value in self.entity.labels.items():
            if value:
                yield lang

    def get_description(self, lang: str):
        return self.entity.descriptions.get(lang)

    def set_description(self, lang: str, value: str):
        self.entity.descriptions[lang] = value

    def iter_descriptions(self):
        for lang, value in self.entity.descriptions.items():
            if value:
                yield lang

    def get_aliases(self, lang: str):
        return list(self.entity.aliases.get(lang, []))

    def add_alias(self, lang: str, value: str):
        if value not in self.get_aliases(lang):
            self.entity.aliases.setdefault(lang, []).append(value)
            return True
        return False

    def remove_alias(self, lang: str, value: str):
        if value in self.get_aliases(lang):
            self.entity.aliases[lang].remove(value)
            return True
        return False

    def set_aliases(self, lang: str, aliases):
        self.entity.aliases[lang] = aliases

    def iter_aliases(self):
        for lang, value in self.entity.aliases.items():
            if value:
                yield lang

    def get_sitelink(self, dbname: str):
        return self.entity.sitelinks.get(dbname)

    def iter_sitelinks(self):
        yield from self.entity.sitelinks


class SubmitDataWrapper(EntityDataWrapper):

    def __init__(self, entity, data):
        super().__init__(entity)
        self.data = self.entity._normalizeData(data)

    def get_label(self, lang: str):
        if lang in self.data.get('labels', {}):
            return self.data['labels'][lang]['value']
        return super().get_label(lang)

    def set_label(self, lang, value: str):
        self.data.setdefault('labels', {}).update(
            {lang: {'language': lang, 'value': value}})

    def iter_labels(self):
        seen = set()
        for lang in self.data.get('labels', {}):
            seen.add(lang)
            if self.data['labels'][lang]['value']:
                yield lang
        for lang in super().iter_labels():
            if lang not in seen:
                yield lang

    def get_description(self, lang: str):
        if lang in self.data.get('descriptions', {}):
            return self.data['descriptions'][lang]['value']
        return super().get_description(lang)

    def set_description(self, lang: str, value: str):
        self.data.setdefault('descriptions', {}).update(
            {lang: {'language': lang, 'value': value}})

    def iter_descriptions(self):
        seen = set()
        for lang in self.data.get('descriptions', {}):
            seen.add(lang)
            if self.data['descriptions'][lang]['value']:
                yield lang
        for lang in super().iter_descriptions():
            if lang not in seen:
                yield lang

    def get_aliases(self, lang: str):
        raise NotImplementedError()  # TODO

    def add_alias(self, lang: str, value: str):
        raise NotImplementedError()  # TODO

    def remove_alias(self, lang: str, value: str):
        raise NotImplementedError()  # TODO

    def set_aliases(self, lang: str, aliases):
        raise NotImplementedError()  # TODO

    def iter_aliases(self):
        raise NotImplementedError()  # TODO

    def get_sitelink(self, dbname: str):
        if dbname in self.data.get('sitelinks', {}):
            value = self.data['sitelinks'][dbname]
            if value['title']:
                return SiteLink.fromJSON(value, self.entity.repo)
            else:
                return None

        return super().get_sitelink(dbname)

    def iter_sitelinks(self):
        seen = set()
        for dbname in self.data.get('sitelinks', {}):
            seen.add(dbname)
            if self.data['sitelinks'][dbname]['title']:
                yield dbname
        for dbname in super().iter_sitelinks():
            if dbname not in seen:
                yield dbname


class WikidataCleanupToolkit:

    lang_map = {
        'als': 'gsw',
        'bat-smg': 'sgs',
        'be-x-old': 'be-tarask',
        'bh': 'bho',
        'de-formal': 'de',
        'es-formal': 'es',
        'fiu-vro': 'vro',
        'foundation': 'en',
        'hu-formal': 'hu',
        'kr': 'knc',
        'meta': 'en',
        'nl-informal': 'nl',
        'no': 'nb',
        'roa-rup': 'rup',
        'simple': 'en',
        'species': 'en',
        'wikidata': 'en',
        'wikimania': 'en',
        'zh-classical': 'lzh',
        'zh-min-nan': 'nan',
        'zh-yue': 'yue',

        # multilingual projects
        'commons': None,
        'incubator': None,
        'mediawiki': None,
        'outreach': None,
        'sources': None,
        'wikifunctions': None,
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
            try:
                ret = handler(*args, **kwargs)
            except NotImplementedError:
                pass
        return ret

    def cleanup_data(self, item, data):
        wrapper = SubmitDataWrapper(item, data)
        # fixme: entity type
        ret = False
        ret = self.exec_fix('fix_languages', wrapper) or ret
        ret = self.exec_fix(
            'fix_HTML',
            wrapper,
            item.claims,
            [], #data.setdefault('claims', [])
        ) or ret
        ret = self.exec_fix('replace_invisible', wrapper) or ret
        #ret = self.exec_fix('move_alias_to_label', wrapper) or ret
        ret = self.exec_fix('add_missing_labels', wrapper) or ret
        ret = self.exec_fix('cleanup_labels', wrapper) or ret
        ret = self.exec_fix('deduplicate_aliases', wrapper) or ret
        # fixme: buggy
##        ret = self.exec_fix(
##            'fix_quantities',
##            item.claims,
##            data.setdefault('claims', [])
##        ) or ret
##        ret = self.exec_fix(
##            'deduplicate_claims',
##            item.claims,
##            data.setdefault('claims', [])
##        ) or ret
##        ret = self.exec_fix(
##            'deduplicate_references',
##            item.claims,
##            data.setdefault('claims', [])
##        ) or ret
        return ret

    def cleanup_entity(self, item):
        wrapper = EntityDataWrapper(item)
        # fixme: entity type
        ret = False
        ret = self.exec_fix('fix_languages', wrapper) or ret
        ret = self.exec_fix('fix_HTML', wrapper, item.claims, []) or ret
        ret = self.exec_fix('replace_invisible', wrapper) or ret
        #ret = self.exec_fix('move_alias_to_label', wrapper) or ret
        ret = self.exec_fix('add_missing_labels', wrapper) or ret
        ret = self.exec_fix('cleanup_labels', wrapper) or ret
        ret = self.exec_fix('deduplicate_aliases', wrapper) or ret
        #ret = self.exec_fix('fix_quantities', item.claims, []) or ret
        ret = self.exec_fix('deduplicate_claims', item.claims, []) or ret
        ret = self.exec_fix('deduplicate_references', item.claims, []) or ret
        return ret

    def move_alias_to_label(self, wrapper):  # todo: not always desired
        ret = False
        for lang in wrapper.iter_aliases():
            aliases = wrapper.get_aliases(lang)
            if len(aliases) == 1 and not wrapper.get_label(lang):
                alias = aliases.pop()
                wrapper.remove_alias(lang, alias)
                wrapper.set_label(lang, alias)
                ret = True
        return ret

    def deduplicate_aliases(self, wrapper):
        ret = False
        for lang in wrapper.iter_aliases():
            already = set()
            aliases = wrapper.get_aliases(lang)
            label = wrapper.get_label(lang)
            if label:
                already.add(label)
            for alias in aliases:
                if alias in already:
                    wrapper.remove_alias(lang, alias)
                    ret = True
                else:
                    already.add(alias)
        return ret

    @classmethod
    def normalize_lang(cls, lang):
        lang = lang.replace('_', '-')
        return cls.lang_map.get(lang, lang)

    def fix_languages(self, wrapper):
        ret = False
        for lang, norm in self.lang_map.items():
            label = wrapper.get_label(lang)
            if not label:
                continue
            if norm:
                norm_label = wrapper.get_label(norm)
                if not norm_label:
                    wrapper.set_label(norm, label)
                elif first_lower(norm_label) != first_lower(label):
                    aliases = wrapper.get_aliases(norm)
                    if first_lower(label) not in map(first_lower, aliases):
                        wrapper.add_alias(norm, label)
            wrapper.set_label(lang, '')
            ret = True

        for lang, norm in self.lang_map.items():
            description = wrapper.get_description(lang)
            if description:
                if norm and not wrapper.get_description(norm):
                    wrapper.set_description(norm, description)
                wrapper.set_description(lang, '')
                ret = True

        for lang, norm in self.lang_map.items():
            old_aliases = wrapper.get_aliases(lang)
            if not old_aliases:
                continue
            if norm:
                new_aliases = wrapper.get_aliases(norm)
                already = set(map(first_lower, new_aliases))
                norm_label = wrapper.get_label(norm)
                if norm_label:
                    already.add(first_lower(norm_label))
                for alias in old_aliases:
                    if first_lower(alias) not in already:
                        wrapper.add_alias(lang, alias)
                        already.add(first_lower(alias))
            wrapper.set_aliases(lang, [])
            ret = True

        return ret

    def get_missing_labels(self, wrapper):
        skip = set()
        labels = {}
        for dbname in wrapper.iter_sitelinks():
            # [[d:Topic:Vedxkcb8ek6ss1pc]]
            if dbname.startswith('alswiki'):
                continue
            lang = self.normalize_lang(dbname.rpartition('wik')[0])
            if not lang or lang in skip:
                continue
            if wrapper.get_label(lang):
                continue

            # try to defer this as much as possible
            try:
                link = wrapper.get_sitelink(dbname)
            except UnknownSiteError:
                continue
            title = link.canonical_title()

            # todo: check if this is still needed
            if ':' not in title and '/' in title:
                continue
            # [[d:Topic:Vhs5f72i5obvkr3t]]
            if title.startswith('Wikipedia:Artikelwerkstatt/'):
                continue
            if title.startswith('Wikipédia:Candidatos a artigo/'):
                continue
            if dbname.endswith('wiktionary') and link.namespace == 0:
                continue
            # [[d:Topic:Vw8cayiif34m2eem]]
            if dbname.endswith('wikinews') and link.namespace == 14:
                continue
            # [[d:Topic:Vn16a76j30dblqo7]]
            if dbname == 'zh_yuewiki' and title.startswith('Portal:時人時事/'):
                continue
            # [[d:Topic:Vrel33kwnco2xp55]]
            if dbname.endswith('wikisource') \
               and link.namespace == link.site.namespaces.lookup_name('Author'):
                title = title.partition(':')[2]
            # [[d:Topic:Uhdjlv9aae6iijuc]]
            # todo: create a lib for this
            if lang == 'fr' and title.startswith(
                    ('Abbaye ', 'Cathédrale ', 'Chapelle ', 'Cloître ',
                     'Couvent ', 'Monastère ', 'Église ')):
                title = first_lower(title)
            label = labels.get(lang)
            if label and first_lower(label) != first_lower(title):
                labels.pop(lang)  # todo: better handling
                skip.add(lang)
                continue

            default = wrapper.get_label('mul')
            if default:
                default_uc = first_upper(default)
                default_lc = first_lower(default)
                if title in (default_uc, default_lc):
                    # cf. Wikidata (Q2013), iPhone (Q2766)
                    labels.pop(lang, None)
                    skip.add(lang)
                    continue
                if title.startswith((
                    f'{default_uc} (',
                    f'{default_lc} (',
                    f'{default_uc},',
                    f'{default_lc},',
                )):
                    labels.pop(lang, None)
                    skip.add(lang)
                    continue

            labels[lang] = title
            # TODO: if 'mul' exists and we add a new label in lang XY,
            # should all languages that fallback to XY get a copy of 'mul'?

        return labels

    def add_missing_labels(self, wrapper):
        labels = self.get_missing_labels(wrapper)
        for lang, label in labels.items():
            wrapper.set_label(lang, label)
        return bool(labels)

    @staticmethod
    def can_strip(lang, part, description):
        if part[-1].isdigit():
            return False
        if lang == 'de':
            # [[d:Topic:Y3blbm3qa391v79u]]
            return False

        if lang == 'en' and part in {'men', 'women'}:
            # [[d:Topic:Xyxkoqqub5ob8vdr]]
            return False
        elif lang == 'fr' and part in {
            # [[d:Topic:Xyxkoqqub5ob8vdr]]
            'simple dames', 'double dames', 'simple messieurs', 'double messieurs'
        }:
            return False
        elif lang == 'nl' and part in {
            # [[d:Topic:Uljziilm6l85hsp3]]
            'vrouwen', 'mannen', 'jongens', 'meisjes', 'enkel', 'dubbel',
            'mannenenkel', 'vrouwenenkel', 'jongensenkel', 'meisjesenkel',
            'mannendubbel', 'vrouwendubbel', 'jongensdubbel', 'meisjesdubbel',
            # [[d:Topic:Wh6ieq0p9uc0jbwo]]
            'kwalificatie', 'rolstoelvrouwen', 'rolstoelvrouwendubbel',
            'rolstoelmannen', 'rolstoelmannendubbel', 'quad', 'quaddubbel',
        }:
            return False
        elif lang == 'pl' and part in {'mężczyźni', 'kobiety'}:
            return False

        if part not in description:  # todo: word to word, not just substring
            for sub in part.split(', '):
                if sub not in description:
                    return False
        return True

    def cleanup_labels(self, wrapper):
        ret = False
        in_claims = None
        search_claims = lambda: {
            claim.getTarget().text
            for claim in chain.from_iterable(wrapper.entity.claims.values())
            if claim.rank != 'deprecated'
            and isinstance(claim.getTarget(), WbMonolingualText)
        }
        # strip "(x)" if "x" is in description
        for lang in wrapper.iter_labels():
            label = wrapper.get_label(lang)
            if not label.endswith(')'):
                continue
            description = wrapper.get_description(lang)
            if not description:
                continue

            if in_claims is None:
                in_claims = search_claims()
            if label in in_claims:
                continue

            left, sep, right = removesuffix(label, ')').rpartition(' (')
            #if not sep:
            #    left, sep, right = label.partition(', ')
            if sep and right and not (set(left) & set('(:)')):
                if self.can_strip(lang, right, description):
                    wrapper.set_label(lang, left.rstrip())
                    ret = True

        # "majority vote"
        labels = {lang: wrapper.get_label(lang) for lang in wrapper.iter_labels()}
        will_strip = {}
        for lang, label in labels.items():
            if not label.endswith(')'):
                continue

            if in_claims is None:
                in_claims = search_claims()
            if label in in_claims:
                continue

            left, sep, right = removesuffix(label, ')').rpartition(' (')
            if sep and right and not (set(left) & set('(:)')):
                if left not in will_strip:
                    with_ = without = 0
                    for txt in labels.values():
                        with_ += txt.startswith(f'{left} (') and txt.endswith(')')
                        without += (txt == left)
                    will_strip[left] = without > with_

                if will_strip[left] and wrapper.get_description(lang):
                    wrapper.set_label(lang, left.rstrip())
                    ret = True

        return ret

    def fix_HTML(self, wrapper, claims, data):
        ret = False
        for lang in wrapper.iter_labels():
            value = wrapper.get_label(lang)
            while True:
                new = html2unicode(value.replace('^|^', '&'))
                if new == value:
                    break
                wrapper.set_label(lang, new)
                value = new
                ret = True

        for lang in wrapper.iter_descriptions():
            value = wrapper.get_description(lang)
            while True:
                new = html2unicode(value.replace('^|^', '&'))
                if new == value:
                    break
                wrapper.set_description(lang, new)
                value = new
                ret = True

        for lang in wrapper.iter_aliases():
            aliases = wrapper.get_aliases(lang)
            change = False
            for i, value in enumerate(aliases):
                while True:
                    new = html2unicode(value.replace('^|^', '&'))
                    if new == value:
                        break
                    aliases[i] = value = new
                    change = True
            if change:
                ret = True
                wrapper.set_aliases(lang, aliases)

        for values in claims.values():
            for claim in values:
                if claim.type != 'monolingualtext':
                    continue
                value = claim.target.text if claim.target else None
                changed = False
                while value:
                    new = html2unicode(value.replace('^|^', '&'))
                    if value == new:
                        break
                    claim.target.text = value = new
                    changed = True
                if changed:
                    data.append(claim.toJSON())
                    ret = True
        return ret

    def replace_invisible(self, wrapper):
        ret = False
        double = ' ' * 2
        for lang in wrapper.iter_labels():
            new = value = wrapper.get_label(lang)
            # fixme: really all of them?
            #new = invisible_regex.sub('', new)
            while double in new:
                new = new.replace(double, ' ')
            if new != value:
                wrapper.set_label(lang, new)
                ret = True

        for lang in wrapper.iter_descriptions():
            new = value = wrapper.get_description(lang)
            # fixme: really all of them?
            #new = invisible_regex.sub('', new)
            while double in new:
                new = new.replace(double, ' ')
            if new != value:
                wrapper.set_description(lang, new)
                ret = True

        for lang in wrapper.iter_aliases():
            aliases = wrapper.get_aliases(lang)
            change = False
            for i, value in enumerate(aliases):
                new = value
                # fixme: really all of them?
                #new = invisible_regex.sub('', new)
                while double in new:
                    new = new.replace(double, ' ')
                if new != value:
                    aliases[i] = new
                    change = True
            if change:
                ret = True
                wrapper.set_aliases(lang, aliases)

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

    def deduplicate_references(self, claims, data):
        ret = False
        for claims_list in claims.values():
            for claim in claims_list:
                hashes = set()
                to_remove = []

                for i, source in enumerate(claim.sources):
                    my_hashes = set()
                    for values in source.values():
                        for ref in values:
                            h = ref.hash
                            if h in my_hashes:
                                continue
                            my_hashes.add(h)
                            if h in hashes:
                                to_remove.append(i)
                            else:
                                hashes.add(h)

                for i in reversed(to_remove):
                    claim.sources.pop(i)
                    ret = True

        return ret

    def deduplicate_claims(self, claims, data):
        ret = False
        for claims_list in claims.values():
            ret = self.deduplicate_claims_list(claims_list, data) or ret
        return ret

    def deduplicate_claims_list(self, claims, data):
        stack = []
        changed = set()
        removed = set()
        for i, claim in enumerate(claims):
            remove = False
            for j, c in stack:
                if self.merge_claims(c, claim):
                    remove = True
                    changed.add(j)
                    break
            if remove:
                removed.add(i)
            else:
                stack.append((i, claim))
        for i in changed:
            data.append(claims[i].toJSON())
        for i in sorted(removed, reverse=True):
            json = claims[i].toJSON()
            json['remove'] = ''
            data.append(json)
            claims.pop(i)
        return bool(changed)

    @staticmethod
    def _same_value(snak1, snak2):
        if snak1.same_as(snak2, ignore_rank=True, ignore_quals=True,
                         ignore_refs=True):
            return True

        if snak1.type == 'time' == snak2.type:
            first, second = snak1.getTarget(), snak2.getTarget()
            if not first or not second:
                return False

            if first.calendarmodel != second.calendarmodel:
                return False

            if first.precision == second.precision:
                if first.precision in {9, 10} and first.year == second.year:
                    if first.precision == 10:
                        return first.month == second.month
                    else:
                        return True

        return False

    @classmethod
    def claims_are_same(cls, claim1, claim2):
        if not cls._same_value(claim1, claim2):
            return False

        if claim1.qualifiers == claim2.qualifiers:
            return True

        if claim1.qualifiers.keys() != claim2.qualifiers.keys():
            return False

        for key, values in claim1.qualifiers.items():
            other = claim2.qualifiers[key]
            if len(other) != len(values):
                return False
            for this in values:
                if not any(cls._same_value(this, val) for val in other):
                    return False

        return True

    def merge_claims(self, claim1, claim2):
        if self.claims_are_same(claim1, claim2):
            if claim1.rank != claim2.rank:
                if claim1.rank == 'normal':
                    claim1.rank = claim2.rank
                elif claim2.rank != 'normal':
                    return False
            hashes = {ref['hash'] for ref in claim1.toJSON().get(
                'references', [])}
            for ref in claim2.toJSON().get('references', []):
                if ref['hash'] not in hashes:
                    ref_copy = Claim.referenceFromJSON(claim2.repo, ref)
                    claim1.sources.append(ref_copy)
                    hashes.add(ref['hash'])
            return True
        else:
            return False
