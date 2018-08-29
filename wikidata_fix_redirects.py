# -*- coding: utf-8 -*-
import pywikibot

from pywikibot.pagegenerators import (
    GeneratorFactory,
    PreloadingEntityGenerator,
    WikidataSPARQLPageGenerator,
)

from itertools import chain

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class WikidataRedirectsFixingBot(WikidataEntityBot):

    summary = 'fixed redirect'
    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.availableOptions.update({
            'always': True,
            'days': 7,
        })
        super(WikidataRedirectsFixingBot, self).__init__(**kwargs)
        self.store = QueryStore()
        self.generator = generator or self.custom_generator()
        self.summary = 'fixed redirect'

    def custom_generator(self):
        query = self.store.build_query('redirects', days=self.getOption('days'))
        return WikidataSPARQLPageGenerator(query, site=self.repo)

    def skip_page(self, item):
        return False

    def update_snak(self, snak, old):
        if snak.snaktype != 'value':
            return False
        if snak.type == 'wikibase-item':
            eq = snak.target_equals(old)
            if eq:
                snak.setTarget(old.getRedirectTarget())
            return eq
        elif snak.type == 'quantity':
            eq = snak.target.unit == old.concept_uri()
            if eq:
                snak.target._unit = old.getRedirectTarget()
            return eq
        return False

    def treat_page_and_item(self, page, item):
        if not item.isRedirectPage():
            return
        target = item.getRedirectTarget()
        pywikibot.output('%s --> %s' % (item, target))
        backlinks = item.backlinks(
            followRedirects=False, filterRedirects=False, namespaces=[0, 120])
        for entity in PreloadingEntityGenerator(backlinks):
            if entity == target:
                continue
            for claims in entity.claims.values():
                for claim in claims:
                    if self.update_snak(claim, item):
                        claim.changeTarget(claim.target, summary=self.summary)
                    for snaks in claim.qualifiers.values():
                        for snak in snaks:
                            if self.update_snak(snak, item):
                                self.repo.editQualifier(
                                    claim, snak, summary=self.summary)
                    for source in claim.sources:
                        snaks = list(chain.from_iterable(source.values()))
                        for snak in snaks:
                            if self.update_snak(snak, item):
                                self.repo.editSource(
                                    claim, snaks, summary=self.summary)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = GeneratorFactory(site=site)
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    bot = WikidataRedirectsFixingBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
