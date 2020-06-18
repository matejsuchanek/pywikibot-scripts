# -*- coding: utf-8 -*-
import pywikibot

from pywikibot.pagegenerators import (
    GeneratorFactory,
    PreloadingEntityGenerator,
    WikidataSPARQLPageGenerator,
)
from itertools import combinations
from operator import attrgetter

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class DuplicateDatesBot(WikidataEntityBot):

    invalid_refs = {'P143', 'P4656'}
    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.availableOptions.update({
            'limit': 2000,
            'props': ['P569', 'P570'],
        })
        super(DuplicateDatesBot, self).__init__(**kwargs)
        self.store = QueryStore()
        self._generator = generator or self.custom_generator()

    def custom_generator(self):
        for prop in self.getOption('props'):
            for key in ('duplicate_dates', 'unmerged_dates'):
                query = self.store.build_query(
                    key, prop=prop, limit=self.getOption('limit'))
                for item in WikidataSPARQLPageGenerator(query, site=self.repo):
                    yield item

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
        for prop in self.getOption('props'):
            claims = item.claims.get(prop, [])
            if len(claims) < 2:
                continue
            if any(claim.rank != 'normal' for claim in claims):
                continue
            already = set()
            redundant = []
            unmerged = []
            for claim1, claim2 in combinations(claims, 2):
                if claim1.id in already or claim2.id in already:
                    continue
                skip = False
                for claim in (claim1, claim2):
                    if not bool(claim.getTarget()):
                        already.add(claim.id)
                        skip = True
                if skip:
                    continue
                pair = (claim1.getTarget(), claim2.getTarget())
                if self.first_same_as_second(*pair):
                    if self.is_sourced(claim1) and self.is_sourced(claim2):
                        # todo: merge
                        continue
                    if self.is_sourced(claim1):
                        cl = claim2
                    else:
                        cl = claim1
                    unmerged.append(cl)
                    already.add(cl.id)
                    continue
                pairs = []
                if not self.is_sourced(claim1):
                    pairs.append(pair)
                if not self.is_sourced(claim2):
                    pairs.append(reversed(pair))
                for first, second in pairs:
                    if self.first_inside_second(first, second):
                        redundant.append(first)
                        already.add(first.id)
                        break
            if redundant or unmerged:
                if redundant:
                    summary = self.summary
                else:
                    summary = 'remove redundant claim(s)'
                item.removeClaims(remove, summary=summary)


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
