# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot

from pywikibot import pagegenerators

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class FakeReferencesBot(WikidataEntityBot):

    item_ids = ['Q2013']
    inferred_from = 'P3452'
    ref_props = ['P143', 'P248']
    url_props = ['P854']
    use_from_page = False
    whitelist_props = {'P813', 'P4656'}

    def __init__(self, generator, **kwargs):
        self.availableOptions.update({
            'limit': None,
        })
        super(FakeReferencesBot, self).__init__(**kwargs)
        self.store = QueryStore()
        self._generator = generator or self.subgenerator()
        self.url_start = self.repo.base_url(self.repo.article_path)

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

        for prop in self.url_props:
            ok = True
            while ok and limit != 0:
                ok = False
                query = self.store.build_query(
                    'fake_references_url',
                    limit=500 if limit is None else min(500, limit),
                    prop=prop)
                for item in pagegenerators.WikidataSPARQLPageGenerator(
                        query, site=self.repo):
                    ok = True
                    yield item
                    if limit is not None:
                        limit -= 1

        for prop in self.ref_props:
            ok = True
            while ok and limit != 0:
                ok = False
                query = self.store.build_query(
                    'fake_references',
                    limit=100 if limit is None else min(100, limit),
                    prop=prop)
                for item in pagegenerators.WikidataSPARQLPageGenerator(
                        query, site=self.repo):
                    ok = True
                    yield item
                    if limit is not None:
                        limit -= 1

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self._generator)

    @property
    def summary(self):
        return ('update reference per [[Wikidata:Requests for permissions/'
                'Bot/MatSuBot 8|RfPB]]')

    def treat_page_and_item(self, page, item):
        changed = False
        for prop, claims in item.claims.items():
            for claim in claims:
                if self.handle_claim(claim):
                    changed = True
        if changed:
            self.user_edit_entity(item, summary=self.summary)

    def handle_claim(self, claim):
        ret = False
        if not claim.sources:
            return ret
        if claim.type == 'wikibase-item':
            if claim.id == 'P1343' and 'P805' in claim.qualifiers:
                target = claim.qualifiers['P805'][0].getTarget()
            else:
                target = claim.getTarget()
            if target:
                for source in claim.sources:
                    ret = self.handle_source_item(source, target) or ret
        for source in claim.sources:
            ret = self.handle_source_url(source) or ret
        return ret

    def handle_source_item(self, source, target):
        ret = False
        for prop in self.ref_props:
            keys = set(source.keys())
            if prop not in keys:
                continue
            if keys - (self.whitelist_props | {prop}):
                continue
            if len(source[prop]) > 1:
                #continue?
                return ret

            fake = next(iter(source[prop]))
            items = list(self.item_ids) + [target]
            if any(fake.target_equals(tgt) for tgt in items):
                snak = pywikibot.Claim(
                    self.repo, self.inferred_from, isReference=True)
                snak.setTarget(target)
                source.setdefault(self.inferred_from, []).append(snak)
                source.pop(prop)
                ret = True
        return ret

    def handle_source_url(self, source):
        ret = False
        for prop in self.url_props:
            keys = set(source.keys())
            if prop not in keys:
                continue
            if keys - (self.whitelist_props | {prop}):
                continue
            if len(source[prop]) > 1:
                #continue?
                return ret

            snak = next(iter(source[prop]))
            url = snak.getTarget()
            if not url:
                continue
            target = None
            try:
                if url.startswith(self.url_start):
                    target = pywikibot.ItemPage(
                        self.repo, url[len(self.url_start):])
                elif url.startswith(self.repo.concept_base_uri):
                    target = pywikibot.ItemPage(
                        self.repo, url[len(self.repo.concept_base_uri):])
            except pywikibot.InvalidTitle:
                pass
            except ValueError:
                pass
            if target:
                if target.isRedirectPage():
                    target = target.getRedirectTarget()
                if target != snak.on_item:
                    snak = pywikibot.Claim(
                        self.repo, self.inferred_from, isReference=True)
                    snak.setTarget(target)
                    source.setdefault(self.inferred_from, []).append(snak)
                source.pop(prop)
                ret = True
        return ret


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
    bot = FakeReferencesBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
