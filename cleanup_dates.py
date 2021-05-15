#!/usr/bin/python
from itertools import chain, combinations
from operator import attrgetter

import pywikibot

from pywikibot import Claim
from pywikibot.pagegenerators import (
    GeneratorFactory,
    PreloadingEntityGenerator,
    WikidataSPARQLPageGenerator,
)

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class DuplicateDatesBot(WikidataEntityBot):

    invalid_refs = {'P143', 'P4656'}
    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.available_options.update({
            'limit': 1000,
            'props': ['P569', 'P570'],
        })
        super().__init__(**kwargs)
        self.store = QueryStore()
        self._generator = generator or self.custom_generator()

    def custom_generator(self):
        for prop in self.opt['props']:
            for key in ('duplicate_dates', 'unmerged_dates'):
                query = self.store.build_query(
                    key, prop=prop, limit=self.opt['limit'])
                yield from WikidataSPARQLPageGenerator(query, site=self.repo)

    @property
    def generator(self):
        return PreloadingEntityGenerator(self._generator)

    @property
    def summary(self):
        return ('remove redundant and less precise unsourced claim(s), '
                '[[Wikidata:Requests for permissions/Bot/MatSuBot 7|see RfPB]]')

    @staticmethod
    def first_inside_second(first, second):
        if first.precision > second.precision:
            if second.precision in {9, 10}:
                if first.year == second.year:
                    if second.precision == 9:
                        return True
                    elif second.precision == 10:
                        return first.month == second.month
        return False

    @staticmethod
    def first_same_as_second(first, second):
        if first == second:
            return True
        if first.precision == second.precision:
            if first.precision in {9, 10} and first.year == second.year:
                if first.precision == 10:
                    return first.month == second.month
                else:
                    return True
        return False

    @classmethod
    def is_valid_source(cls, source):
        return bool(source) and not (set(source) & cls.invalid_refs)

    @classmethod
    def number_of_sources(cls, claim):
        number = 0
        for source in claim.sources:
            number += cls.is_valid_source(source)
        return number

    @classmethod
    def is_sourced(cls, claim):
        return cls.number_of_sources(claim) > 0

    def treat_page_and_item(self, page, item):
        for prop in self.opt['props']:
            claims = item.claims.get(prop, [])
            if len(claims) < 2:
                continue
            if any(claim.rank != 'normal' for claim in claims):
                continue
            already = set()
            redundant = []
            unmerged = []
            for claim1, claim2 in combinations(claims, 2):
                if claim1.snak in already or claim2.snak in already:
                    continue
                skip = False
                for claim in (claim1, claim2):
                    if not bool(claim.getTarget()) or bool(claim.qualifiers):
                        already.add(claim.snak)
                        skip = True
                if skip:
                    continue
                targets = lambda c1, c2: (c1.getTarget(), c2.getTarget())
                if self.first_same_as_second(*targets(claim1, claim2)):
                    if self.is_sourced(claim1) and self.is_sourced(claim2):
                        cl = claim2
                        for source in cl.sources:
                            if self.is_valid_source(source):
                                try:
                                    claim1.addSources([
                                        c.copy() for c in chain(*source.values())])
                                except pywikibot.data.api.APIError:
                                    pass  # duplicate reference present
                    elif self.is_sourced(claim1):
                        cl = claim2
                    else:
                        cl = claim1
                    unmerged.append(cl)
                    already.add(cl.snak)
                    continue
                pairs = [(claim1, claim2), (claim2, claim1)]
                for first, second in pairs:
                    if self.is_sourced(second):
                        continue
                    if self.first_inside_second(*targets(first, second)):
                        redundant.append(second)
                        already.add(second.snak)
                        break
            if redundant or unmerged:
                if redundant:
                    summary = self.summary
                else:
                    summary = 'remove redundant claim(s)'
                item.removeClaims(redundant + unmerged, summary=summary)


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
            if arg == '-prop':
                options.setdefault('props', []).append(
                    value or pywikibot.input('Which property should be treated?'))
            elif value:
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    bot = DuplicateDatesBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
