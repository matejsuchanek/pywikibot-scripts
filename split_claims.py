# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot

from pywikibot import pagegenerators

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class ClaimsSplittingBot(WikidataEntityBot):

    start_prop = 'P580'
    end_prop = 'P582'
    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.availableOptions.update({
            'limit': 500,
        })
        super(ClaimsSplittingBot, self).__init__(**kwargs)
        self.store = QueryStore()
        self._generator = generator or self.custom_generator()

    def custom_generator(self):
        query = self.store.build_query(
            'mixed_claims', limit=self.getOption('limit'))
        return pagegenerators.WikidataSPARQLPageGenerator(query, site=self.repo)

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self._generator)

    def has_multiple(self, claim):
        return (len(claim.qualifiers.get(self.start_prop, [])) > 1
                or len(claim.qualifiers.get(self.end_prop, [])) > 1)

    def can_divide(self, claim):
        qualifiers = (claim.qualifiers.get(self.start_prop, [])
                      + claim.qualifiers.get(self.end_prop, []))
        return (len(claim.sources) == 0
                and set(claim.qualifiers.keys()) == {
                    self.start_prop, self.end_prop}
                and all(qual.snaktype == 'value' for qual in qualifiers))

    def sort_key(self, claim):
        return claim.target.toTimestamp()
            #{self.start_prop: 1, self.end_prop: 0}.get(claim.id)

    def get_qualifier_pairs(self, claim):
        qualifiers = (claim.qualifiers.get(self.start_prop, [])
                      + claim.qualifiers.get(self.end_prop, []))
        qualifiers.sort(key=self.sort_key)
        pairs = []
        i = 0
        any_previous_finished = False
        while i < len(qualifiers):
            qual = qualifiers[i]
            if qual.id == self.start_prop:
                next_end = None
                if i + 1 < len(qualifiers):
                    if qualifiers[i+1].id == self.end_prop:
                        pairs.append(
                            (qual, qualifiers[i+1])
                        )
                        i += 2
                        any_previous_finished = True
                        continue
                    elif qualifiers[i+1].id == self.start_prop:
                        next_end = pywikibot.Claim(self.repo, self.end_prop)
                        next_end.setSnakType('somevalue')
                        any_previous_finished = True
                pairs.append(
                    (qual, next_end)
                )
            elif qual.id == self.end_prop:
                next_start = None
                if any_previous_finished:
                    next_start = pywikibot.Claim(self.repo, self.start_prop)
                    next_start.setSnakType('somevalue')
                pairs.append(
                    (next_start, qual)
                )
                any_previous_finished = True
            i += 1
        return pairs

    @property
    def summary(self):
        return 'removing splitted claim(s)'

    def treat_page_and_item(self, page, item):
        to_remove = []
        for claims in item.claims.values():
            for claim in claims:
                if self.has_multiple(claim) and self.can_divide(claim):
                    assert not claim.sources  # todo
                    to_remove.append(claim)
                    pairs = self.get_qualifier_pairs(claim)
                    for start, end in pairs:
                        new_claim = pywikibot.Claim(self.repo, claim.id)
                        if claim.target:
                            new_claim.setTarget(claim.target)
                        else:
                            new_claim.setSnakType(claim.snaktype)
                        new_claim.setRank(claim.rank)
                        if start:
                            start.hash = None
                            new_claim.addQualifier(start)
                        if end:
                            end.hash = None
                            new_claim.addQualifier(end)
                        for ref in claim.sources:
                            sources = []
                            for snaks in ref.values():
                                sources.extend(snaks)
                            new_claim.addSources(sources)
                        self.user_add_claim(item, new_claim)
        if to_remove:
            data = {'claims': [
                {'id': cl.toJSON()['id'], 'remove': ''} for cl in to_remove]}
            self.user_edit_entity(item, data, summary=self.summary)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = pagegenerators.GeneratorFactory(site=site)
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    bot = ClaimsSplittingBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
