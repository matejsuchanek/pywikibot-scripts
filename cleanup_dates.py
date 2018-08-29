# -*- coding: utf-8 -*-
import pywikibot

from pywikibot.pagegenerators import (
    PreloadingEntityGenerator,
    WikidataSPARQLPageGenerator,
)
from itertools import combinations
from operator import attrgetter

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class DuplicateDatesBot(WikidataEntityBot):

    props = ['P569', 'P570']
    use_from_page = False

    def __init__(self, generator, **kwargs):
        super(DuplicateDatesBot, self).__init__(**kwargs)
        self.store = QueryStore()
        self._generator = generator or self.custom_generator()

    def custom_generator(self):
        for prop in self.props:
            query = self.store.build_query('duplicate_dates', prop=prop)
            for item in WikidataSPARQLPageGenerator(query, site=self.repo):
                yield item

    @property
    def generator(self):
        return PreloadingEntityGenerator(self._generator)

    @property
    def summary(self):
        return ('remove less precise unsourced date, '
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

    @classmethod
    def one_inside_another_in_pair(cls, cl1, cl2):
        return bool(cl1.target) and bool(cl2.target) and (
            cls.first_inside_second(cl1.target, cl2.target) or
            cls.first_inside_second(cl2.target, cl1.target))

    @staticmethod
    def valid_source(source):
        return bool(source) and 'P143' not in source

    @classmethod
    def number_of_sources(cls, claim):
        number = 0
        for source in claim.sources:
            if cls.valid_source(source):
                number += 1
        return number

    @classmethod
    def is_unsourced(cls, claim):
        return cls.number_of_sources(claim) == 0

    @staticmethod
    def is_sourced(claim):
        return True
        #return cls.number_of_sources(claim) > 0

    def treat_page_and_item(self, page, item):
        for prop in self.props:
            claims = item.claims.get(prop, [])
            if len(claims) > 1 and all(
                    claim.rank == 'normal' for claim in claims):
                for pair in combinations(claims, 2):
                    if self.one_inside_another_in_pair(*pair):
                        cl1, cl2 = tuple(
                            sorted(pair, key=attrgetter('target.precision')))
                        if self.is_unsourced(cl1) and self.is_sourced(cl2):
                            item.removeClaims(cl1, summary=self.summary)
                            item.get(force=True)
                            break


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
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    bot = DuplicateDatesBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
