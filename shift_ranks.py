#!/usr/bin/python
import pywikibot

from pywikibot import pagegenerators

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class RanksShiftingBot(WikidataEntityBot):

    end_prop = 'P582'
    reason_prop = 'P2241'
    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.available_options.update({
            'limit': 500,
        })
        super().__init__(**kwargs)
        self.store = QueryStore()
        self._generator = generator or self.custom_generator()

    def custom_generator(self):
        query = self.store.build_query(
            'shift_ranks',
            limit=self.opt['limit'],
            prop=self.end_prop
        )
        return pagegenerators.WikidataSPARQLPageGenerator(query, site=self.repo)

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self._generator)

    @property
    def summary(self):
        return ('undeprecate claims and shift other ranks, see '
                '[[Special:MyLanguage/Help:Ranking|Help:Ranking]]')

    def treat_page_and_item(self, page, item):
        changed = False
        for claims in item.claims.values():
            by_rank = {
                'preferred': [],
                'normal': [],
                'deprecated': [],
            }
            ok = False
            for claim in claims:
                by_rank[claim.rank].append(claim)
                if claim.rank == 'preferred':
                    if claim.qualifiers.get(self.end_prop):
                        ok = False
                        break
                elif claim.rank == 'deprecated':
                    if claim.qualifiers.get(self.reason_prop):
                        ok = False
                        break
                    if not ok:
                        ok = bool(claim.qualifiers.get(self.end_prop))
            if not ok:
                continue
            for claim in by_rank['deprecated']:
                if claim.qualifiers.get(self.end_prop):
                    claim.setRank('normal')
                    changed = True
            if not by_rank['preferred']:
                for claim in by_rank['normal']:
                    if not claim.qualifiers.get(self.end_prop):
                        claim.setRank('preferred')
                        changed = True
        if changed:
            self.user_edit_entity(item, summary=self.summary)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = pagegenerators.GeneratorFactory(site=site)
    for arg in genFactory.handle_args(local_args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    bot = RanksShiftingBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
