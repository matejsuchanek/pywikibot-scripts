# -*- coding: utf-8 -*-
import pywikibot

from pywikibot.pagegenerators import (
    PreloadingEntityGenerator,
    WikidataSPARQLPageGenerator,
)

from itertools import chain

from .query_store import QueryStore
from .wikidata import WikidataEntityBot

class WikidataRedirectsFixingBot(WikidataEntityBot):

    summary = 'fixed redirect'
    use_from_page = False

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'always': True,
            'days': 7,
        })
        super(WikidataRedirectsFixingBot, self).__init__(**kwargs)
        self.store = QueryStore()

    @property
    def generator(self):
        query = self.store.build_query('redirects', days=self.getOption('days'))
        return PreloadingEntityGenerator(
            WikidataSPARQLPageGenerator(query, site=self.repo))

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
        gen = PreloadingEntityGenerator(
            WikidataSPARQLPageGenerator(query, site=self.repo))
        for redir in gen:
            if not redir.isRedirectPage():
                continue
            target = redir.getRedirectTarget()
            pywikibot.output('%s --> %s' % (redir, target))
            subgen = PreloadingEntityGenerator(
                redir.backlinks(followRedirects=False, filterRedirects=False,
                                namespaces=[0, 120]))
            for entity in subgen:
                if entity == target:
                    continue
                for claims in entity.claims.values():
                    for claim in claims:
                        if self.update_snak(claim, redir):
                            claim.changeTarget(claim.target, summary=summary)
                        for snaks in claim.qualifiers.values():
                            for snak in snaks:
                                if self.update_snak(snak, redir):
                                    self.repo.editQualifier(
                                        claim, snak, summary=summary)
                        for source in claim.sources:
                            snaks = list(chain.from_iterable(source.values()))
                            for snak in snaks:
                                if self.update_snak(snak, redir):
                                    self.repo.editSource(
                                        claim, snaks, summary=summary)


def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = WikidataRedirectsFixingBot(**options)
    bot.run()


if __name__ == '__main__':
    main()
