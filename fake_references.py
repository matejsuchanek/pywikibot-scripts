# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot

from pywikibot import pagegenerators

from itertools import chain

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class FakeReferencesBot(WikidataEntityBot):

    item_ids = ['Q2013', 'Q20651139']
    inferred_from = 'P3452'
    ref_props = ['P143', 'P248']
    use_from_page = False
    whitelist_props = ['P813']
    # todo: P854

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'limit': None,
        })
        super(FakeReferencesBot, self).__init__(**kwargs)
        self.store = QueryStore()

    def subgenerator(self):
        limit = self.getOption('limit')
        for ident in self.item_ids:
            from_item = pywikibot.ItemPage(self.repo, ident)
            for item in pagegenerators.WikibaseItemGenerator(
                    from_item.backlinks(
                        total=limit, filterRedirects=False, namespaces=[0])):
                yield item
                if limit is not None:
                    limit -= 1

            if limit == 0:
                return

        for prop in self.ref_props:
            if limit == 0:
                break
            # TODO: item_ids
            query = self.store.build_query(
                'fake_references',
                limit=10 if limit is None else min(10, limit),
                prop=prop)
            for item in pagegenerators.WikidataSPARQLPageGenerator(
                    query, site=self.repo):
                yield item
                if limit is not None:
                    limit -= 1

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self.subgenerator())

    @property
    def summary(self):
        return ('update reference per [[Wikidata:Requests for permissions/'
                'Bot/MatSuBot 8|RfPB]]')

    def treat_page_and_item(self, page, item):
        all_claims = set()
        for prop, claims in item.claims.items():
            for claim in claims:
                if self.handle_claim(claim):
                    all_claims.add(claim)
        if all_claims:
            data = {'claims': [cl.toJSON() for cl in all_claims]}
            self.user_edit_entity(item, data, summary=self.summary)

    def handle_claim(self, claim):
        ret = False
        if not claim.sources or claim.type != 'wikibase-item':
            return ret
        if claim.id == 'P1343' and 'P805' in claim.qualifiers.keys():
            return ret  # todo
        target = claim.getTarget()
        if not target:
            return ret
        for source in claim.sources:
            ret = self.handle_source(claim, source, target) or ret
        return ret

    def handle_source(self, claim, source, target):
        ret = False
        for prop in self.ref_props:
            keys = set(source.keys())
            if prop not in keys:
                continue
            if keys - (set(self.whitelist_props) | set([prop])):
                continue
            if len(source[prop]) > 1:
                #continue?
                return ret

            fake = next(iter(source[prop]))
            items = list(self.item_ids) + [target]
            if any(fake.target_equals(tgt) for tgt in items):
                good_sources = list(chain.from_iterable(
                    source[p] for p in keys - set([prop])))
                snak = pywikibot.Claim(
                    self.repo, self.inferred_from, isReference=True)
                snak.setTarget(target)
                source.setdefault(self.inferred_from, []).append(snak)
                source.pop(prop)
                ret = True
        return ret


def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = FakeReferencesBot(**options)
    bot.run()


if __name__ == '__main__':
    main()
