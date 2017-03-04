# -*- coding: utf-8 -*-
import pywikibot

from pywikibot import pagegenerators

from pywikibot.bot import SkipPageError

from .wikidata import WikidataEntityBot
from scripts.revertbot import BaseRevertBot

class DupesMergingBot(WikidataEntityBot, BaseRevertBot):

    dupe_item = 'Q17362920'

    def __init__(self, offset=0, **kwargs):
        super(DupesMergingBot, self).__init__(**kwargs)
        self.offset = offset
        BaseRevertBot.__init__(self, self.site)

    @property
    def generator(self):
        QUERY = '''
SELECT DISTINCT ?item WHERE {
  ?item p:P31 ?statement .
  ?statement ps:P31 wd:%s .
  {
    VALUES ?pq { pq:P460 pq:P642 } .
    ?statement ?pq ?target .
  } UNION {
    ?item wdt:P460 ?target .
  } .
  MINUS {
    ?target wdt:P31/wdt:P279* wd:Q16521 .
  } .
  ?item schema:dateModified ?mod .
} ORDER BY ?mod OFFSET %s
'''.strip().replace('\n', ' ') % (self.dupe_item, self.offset)

        return pagegenerators.PreloadingGenerator(
            pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=self.repo,
                                                       result_type=tuple))

    def init_page(self, item):
        self.offset += 1
        super(DupesMergingBot, self).init_page(item)
        if 'P31' not in item.get().get('claims'):
            raise SkipPageError(item, 'Missing P31 property')

    def treat_page(self):
        item = self.current_page
        claims = []
        targets = set()
        for claim in item.claims['P31']:
            if claim.snaktype != 'value':
                continue
            if not claim.target_equals(self.dupe_item):
                continue
            claims.append(claim)
            for prop in ['P460', 'P642']:
                for snak in claim.qualifiers.get(prop, []):
                    if snak.snaktype == 'value':
                        targets.add(snak.getTarget())

        for claim in item.claims.get('P460', []):
            if claim.snaktype == 'value':
                claims.append(claim)
                targets.add(claim.getTarget())

        if not targets:
            pywikibot.output('No target found')
            return

        target = targets.pop()
        if targets:
            pywikibot.output('Multiple targets found')
            return

        while target.isRedirectPage():
            pywikibot.warning('Target %s is redirect' % target.getID())
            target = target.getRedirectTarget()

        if item.getID() == target.getID():
            self._save_page(item, self._save_entity, item.removeClaims, claims)
            return

        target.get()
        target_sitelinks = []
        sitelinks = []
        for page in item.iterlinks():
            site = page.site
            try:
                target_link = target.getSitelink(site)
            except pywikibot.NoPage:
                continue

            if not page.exists():
                sitelinks.append(site)
                continue

            target_page = pywikibot.Page(site, target_link)
            if not target_page.exists():
                target_sitelinks.append(site)
                continue
            if (self.redirectsTo(page, target_page) or
                self.redirectsTo(target_page, page)):
                continue

            pywikibot.output('Target has a conflicting sitelink: %s'
                             % site.dbName())
            return

        target_claims = []
        for claim in target.claims.get('P460', []):
            if claim.snaktype != 'value':
                continue
            if claim.target_equals(item):
                target_claims.append(claim)

        for claim in target.claims.get('P31', []):
            if claim.snaktype != 'value':
                continue
            if not claim.target_equals(self.dupe_item):
                continue
            for prop in ['P460', 'P642']:
                for snak in claim.qualifiers.get(prop, []):
                    if snak.snaktype != 'value':
                        continue
                    if snak.target_equals(item):
                        target_claims.append(claim)

        if len(sitelinks) > 0:
            self._save_page(item, self._save_entity, item.removeSitelinks, sitelinks)
        if len(claims) > 0:
            self._save_page(item, self._save_entity, item.removeClaims, claims)
        if len(target_sitelinks) > 0:
            self._save_page(target, self._save_entity, target.removeSitelinks, target_sitelinks)
        if len(target_claims) > 0:
            self._save_page(target, self._save_entity, target.removeClaims, target_claims)

        try:
            self._save_page(item, self._save_entity, item.mergeInto, target,
                            ignore_conflicts=['description'])
        except pywikibot.data.api.APIError as e:
            pywikibot.exception(e)
            pywikibot.output('Reverting changes...')
            self.comment = 'Error occurred when attempting to merge with %s' % target.title(asLink=True)
            self.revert({'title': item.title()})
            self.comment = 'Error occurred when attempting to merge with %s' % item.title(asLink=True)
            self.revert({'title': target.title()})
            return

        if not item.isRedirectPage(): # todo: migrate to Merger
            item.get(force=True)
            descriptions = {}
            for lang in item.descriptions.keys():
                descriptions[lang] = ''

            self._save_page(item, self._save_entity, item.editDescriptions,
                            descriptions, summary='Removing conflicting '
                            'descriptions before merging')
            item.mergeInto(target)

        self.offset -= 1

    def redirectsTo(self, page, target):
        return page.isRedirectPage() and page.getRedirectTarget() == target

    def exit(self):
        super(DupesMergingBot, self).exit()
        pywikibot.output('\nCurrent offset: %s\n' % self.offset)

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = DupesMergingBot(**options)
    bot.run()

if __name__ == '__main__':
    main()
