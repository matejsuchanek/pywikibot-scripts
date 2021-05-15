#!/usr/bin/python
from itertools import chain

import pywikibot

from pywikibot.pagegenerators import (
    GeneratorFactory,
    PreloadingEntityGenerator,
    WikidataSPARQLPageGenerator,
)

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class WikidataRedirectsFixingBot(WikidataEntityBot):

    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.available_options.update({
            'always': True,
            'days': 7,
        })
        super().__init__(**kwargs)
        self.store = QueryStore()
        self.generator = generator or self.custom_generator()
        self.summary = 'fix redirect [[%s]] → [[%s]]'

    def custom_generator(self):
        query = self.store.build_query('redirects', days=self.opt['days'])
        return WikidataSPARQLPageGenerator(query, site=self.repo)

    def skip_page(self, item):
        return False

    def _make_callback(self, callback, *args, **kwargs):
        return lambda: callback(*args, **kwargs)

    def update_snak(self, snak, old, target):
        if snak.snaktype != 'value':
            return False
        if snak.type == 'wikibase-item':
            eq = snak.target_equals(old)
            if eq:
                snak.setTarget(target)
            return eq
        #elif snak.type == 'wikibase-lexeme':
        elif snak.type == 'quantity':
            eq = snak.target.unit == target.concept_uri()
            if eq:
                snak.target._unit = target
            return eq
        return False

    def treat_page_and_item(self, page, item):
        if not item.isRedirectPage():
            return
        target = item.getRedirectTarget()
        while target.isRedirectPage():
            target = target.getRedirectTarget()
        pywikibot.output('%s --> %s' % (item, target))
        backlinks = item.backlinks(
            follow_redirects=False,
            filter_redirects=None,
            namespaces=[0, 120])
        summary = self.summary % (
            item.title(with_ns=True), target.title(with_ns=True))
        if target != item.getRedirectTarget():
            item.set_redirect_target(target, summary=summary)
        for entity in PreloadingEntityGenerator(backlinks):
            if entity == target:
                continue
            if entity.isRedirectPage():
                entity.set_redirect_target(target, summary=summary)
                continue
            callbacks = []
            update = []
            for claim in chain.from_iterable(entity.claims.values()):
                changed = False
                if self.update_snak(claim, item, target):
                    changed = True
                    callbacks.append(self._make_callback(
                        claim.changeTarget, target, summary=summary))
                for snak in chain.from_iterable(claim.qualifiers.values()):
                    if self.update_snak(snak, item, target):
                        changed = True
                        callbacks.append(self._make_callback(
                            claim.repo.editQualifier, claim, snak,
                            summary=summary))
                for source in claim.sources:
                    snaks = list(chain.from_iterable(source.values()))
                    for snak in snaks:
                        if self.update_snak(snak, item, target):
                            changed = True
                            callbacks.append(self._make_callback(
                                claim.repo.editSource, claim, snaks,
                                summary=summary))
                if changed:
                    update.append(claim)
            if len(callbacks) > 1:
                data = {'claims': [c.toJSON() for c in update]}
                self.user_edit_entity(
                    entity, data, cleanup=False, summary=summary)
            elif len(callbacks) == 1:
                callbacks[0]()


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = GeneratorFactory(site=site)
    for arg in local_args:
        if genFactory.handle_arg(arg):
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
