# -*- coding: utf-8 -*-
import pywikibot

from pywikibot import pagegenerators
from pywikibot.bot import SkipPageError

from itertools import chain

from .query_store import QueryStore
from .wikidata import WikidataEntityBot

class FakeReferencesBot(WikidataEntityBot):

    item_ids = ['Q2013', 'Q20651139']
    inferred_from = 'P3452'
    ref_props = ['P143', 'P248']
    use_from_page = False
    whitelist_props = ['P813']

    def __init__(self, **kwargs):
        self.availableOptions.update({})
        super(FakeReferencesBot, self).__init__(**kwargs)
        self.store = QueryStore()

    def subgenerator(self):
        for prop in self.ref_props:
            query = self.store.build_query(
                'fake_references', limit=1000, offset=0, prop=prop)
            for item in pagegenerators.WikidataSPARQLPageGenerator(
                    query, site=self.repo):
                yield item

    @property
    def generator(self):
        return pagegenerators.PreloadingItemGenerator(self.query_generator)

    def init_page(self, item):
        super(FakeReferencesBot, self).init_page(item)

    def treat_page_and_item(self, page, item):
        for prop, claims in item.claims.items():
            for claim in claims:
                self.handle_claim(claim)

    def handle_claim(self, claim):
        if not claim.sources or claim.type != 'wikibase-item':
            return
        target = claim.getTarget()
        if not target:
            return
        for source in claim.sources:
            self.handle_source(claim, source, target)

    def handle_source(self, claim, source, target):
        for prop in self.ref_props:
            keys = set(source.keys())
            if not (keys & set([prop])):
                continue
            if keys - (self.whitelist_props | set([prop])):
                continue
            if len(source[prop]) > 1:
                #continue?
                return

            fake = next(iter(source[prop]))
            items = list(item_ids) + [target]
            if any(fake.target_equals(tgt) for tgt in items):
                good_sources = list(chain.from_iterable(
                    source[p] for p in keys - set([prop])))
                snak = pywikibot.Claim(self.repo, self.inferred_from,
                                       isReference=True)
                snak.setTarget(target)
                claim.addSources(good_sources + [snak])
                claim.removeSources(good_sources + [fake])

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
