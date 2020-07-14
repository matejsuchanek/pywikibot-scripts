# -*- coding: utf-8 -*-
import requests
import time

from operator import attrgetter, methodcaller

import pywikibot

from pywikibot.data.sparql import SparqlQuery


class Merger:

    strategies = {
        'id': '_sort_by_id',
        'claims': '_sort_by_claims',
        'revisions': '_sort_by_revisions',
        'sitelinks': '_sort_by_sitelinks',
    }
    no_conflict_props = {'P17', 'P21', 'P105', 'P170', 'P171', 'P225', 'P271',
                         'P296', 'P495', 'P569', 'P570', 'P734', 'P856'}
    no_conflict_trees = {
        'P19': 'P131',
        'P31': 'P279',
        'P131': 'P131',
        'P279': 'P279',
    }
    no_conflict_types = ['external-id']

    @classmethod
    def merge(cls, item_from, item_to, **kwargs):
        try:
            item_from.mergeInto(item_to, **kwargs)
        except pywikibot.data.api.APIError as e:
            raise pywikibot.OtherPageSaveError(item_from, e)

    @classmethod
    def clean_merge(cls, item_from, item_to, safe=False, quick=True, **kwargs):
        kwargs.pop('asynchronous', None)  # fixme
        if safe and not cls.can_merge(item_from, item_to, quick=quick):
            raise pywikibot.OtherPageSaveError(
                item_from, 'Cannot merge %s with %s' % (item_from, item_to))

        cls.merge(item_from, item_to, **kwargs)
        if not item_from.isRedirectPage():
            item_from.get(force=True)
            data = {'claims': [], 'descriptions': {}, 'sitelinks': []}
            for lang in item_from.descriptions:
                data['descriptions'][lang] = '' # fixme upstream
            for dbname in item_from.sitelinks:
                data['sitelinks'].append({'site': dbname, 'title': ''})
            for prop, claims in item_from.claims.items():
                for claim in claims:
                    json = claim.toJSON()
                    json['remove'] = ''
                    data['claims'].append(json)
            try:
                item_from.editEntity(
                    data, summary='Clearing item to prepare for redirect')
            except pywikibot.data.api.APIError as e:
                raise pywikibot.OtherPageSaveError(item_from, e)

            cls.merge(item_from, item_to)

    @classmethod
    def _conflicts(cls, data1, data2):
        set1 = {repr(x.target) for x in data1}  # hack
        set2 = {repr(x.target) for x in data2}  # hack
        return not bool(set1 & set2)

    @classmethod
    def _has_dtype(cls, dtype, claims):
        for cl in claims:
            if cl.type == dtype:
                return True
        return False

    @classmethod
    def _same_tree(cls, prop, data1, data2):
        sparql = SparqlQuery()  # fixme: dependencies
        pattern = ('ASK { VALUES ?x1 { wd:%s } . VALUES ?x2 { wd:%s } . '
                   '?x1 wdt:%s* ?x2 }')
        item1 = ' wd:'.join(map(attrgetter('target.id'), data1))
        item2 = ' wd:'.join(map(attrgetter('target.id'), data2))
        tries = 3
        for ask in (pattern % (item1, item2, prop),
                    pattern % (item2, item1, prop)):
            res = False
            while True:
                try:
                    res = sparql.ask(ask)
                except requests.exceptions.ConnectionError:
                    tries -= 1
                    if tries == 0:
                        raise
                    time.sleep(1)
                    continue
                else:
                    break
            if res:
                return True

        return False

    @classmethod
    def can_merge(cls, item1, item2, quick=True):
        props = list(cls.no_conflict_props)
        if quick:
            props.extend(cls.no_conflict_trees.keys())

        for prop in props:
            item1.get()
            data1 = item1.claims.get(prop, [])
            if not data1:
                continue
            item2.get()
            data2 = item2.claims.get(prop, [])
            if not data2:
                continue
            if cls._conflicts(data1, data2):
                return False

        key = lambda claims: claims[0].id
        for dtype in cls.no_conflict_types:
            callback = lambda claims: claims[0].type == dtype
            item1.get()
            keys1 = set(map(key, filter(callback, item1.claims.values())))
            if not keys1:
                continue
            item2.get()
            keys2 = set(map(key, filter(callback, item2.claims.values())))
            if not keys2:
                continue
            for prop in keys1 & keys2:
                if cls._conflicts(item1.claims[prop], item2.claims[prop]):
                    return False

        if not quick:
            for prop in cls.no_conflict_trees:
                item1.get()
                data1 = item1.claims.get(prop, [])
                if not data1:
                    continue
                item2.get()
                data2 = item2.claims.get(prop, [])
                if not data2:
                    continue
                if not cls._same_tree(cls.no_conflict_trees[prop], data1, data2):
                    return False

        return True

    @classmethod
    def _sort_by_id(cls, item1, item2):
        id1, id2 = map(methodcaller('getID', numeric=True), [item1, item2])
        return (id1 < id2) - (id1 > id2)

    @classmethod
    def _sort_by_revisions(cls, item1, item2):
        len1, len2 = map(
            lambda item: len(list(item.revisions())), [item1, item2])
        return (len1 > len2) - (len1 < len2)

    @classmethod
    def _sort_by_claims(cls, item1, item2):
        callback = lambda item: sum(map(len, item.claims.values()))
        count1, count2 = map(callback, [item1, item2])
        return (count1 > count2) - (count1 < count2)

    @classmethod
    def _sort_by_sitelinks(cls, item1, item2):
        len1, len2 = map(lambda item: len(item.sitelinks), [item1, item2])
        return (len1 > len2) - (len1 < len2)

    @classmethod
    def sort_for_merge(cls, items, key=['id']):
        for strategy in key:
            if strategy not in cls.strategies:
                continue
            callback = getattr(cls, cls.strategies[strategy])
            res = callback(*items)
            if res == 0:
                continue
            if res == -1:
                items[:] = items[::-1]
            break
        target_item, from_item = items
        return target_item, from_item
