# -*- coding: utf-8  -*-
import pywikibot

from pywikibot import pagegenerators

from pywikibot.bot import SkipPageError

from scripts.wikidata import WikidataEntityBot

class DupesMergingBot(WikidataEntityBot):

    def __init__(self, **kwargs):
        super(DupesMergingBot, self).__init__(**kwargs)
        self.__dupe_item = pywikibot.ItemPage(self.repo, 'Q17362920')

    def init_page(self, item):
        super(DupesMergingBot, self).init_page(item)
        if 'P31' not in item.claims:
            raise SkipPageError(
                item,
                "Missing P31 property"
            )

    #def getClaimsToRemove(self, claims, target, remove_claims):

    def treat_page(self):
        item = self.current_page
        claims = []
        target = None
        for claim in item.claims['P31']:
            if claim.snaktype != 'value':
                continue
            if claim.target_equals(self.__dupe_item):
                claims.append(claim)
                for prop in ['P460', 'P642']:
                    if prop in claim.qualifiers.keys():
                        for snak in claim.qualifiers[prop]:
                            if snak.snaktype != 'value':
                                continue
                            if target is None:
                                target = snak.getTarget()
                            else:
                                if not snak.target_equals(target):
                                    pywikibot.output("Multiple targets found")
                                    return

        for claim in item.claims.get('P460', []):
            if claim.snaktype != 'value':
                continue
            claims.append(claim)
            if target is None:
                target = claim.getTarget()
            else:
                if not claim.target_equals(target):
                    pywikibot.output("Multiple targets found")
                    return

        if target is None:
            pywikibot.output("No target found")
            return

        while target.isRedirectPage():
            pywikibot.warning("Target %s is redirect" % target.getID())
            target = target.getRedirectTarget()

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
            if self.redirectsTo(page, target_page) or self.redirectsTo(target_page, page):
                continue

            pywikibot.output("Target has a conflicting sitelink: %s" % site.dbName())
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
            if claim.target_equals(self.__dupe_item):
                for prop in ['P460', 'P642']:
                    if prop in claim.qualifiers.keys():
                        for snak in claim.qualifiers[prop]:
                            if snak.snaktype != 'value':
                                continue
                            if snak.target_equals(item):
                                target_claims.append(claim)
                        break

        if len(sitelinks) > 0:
            self._save_page(item, self._save_entity, item.removeSitelinks, sitelinks)
        if len(claims) > 0:
            self._save_page(item, self._save_entity, item.removeClaims, claims)
        if len(target_sitelinks) > 0:
            self._save_page(item, self._save_entity, target.removeSitelinks, target_sitelinks)
        if len(target_claims) > 0:
            self._save_page(item, self._save_entity, target.removeClaims, target_claims)

        descriptions = {}
        for lang in item.descriptions.keys():
            if lang in target.descriptions.keys():
                if item.descriptions[lang] != target.descriptions[lang]:
                    descriptions[lang] = ''

        if len(descriptions) > 0:
            self._save_page(item, self._save_entity, item.editDescriptions, descriptions,
                            summary="Removing conflicting descriptions before merging")

        self._save_page(item, self._save_entity, item.mergeInto, target,
                        ignore_conflicts=("description"))

    def redirectsTo(self, page, target):
        return page.isRedirectPage() and page.getRedirectTarget().title() == target.title()

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    QUERY = """SELECT DISTINCT ?item WHERE {
  ?item p:P31 ?statement .
  ?statement ps:P31 wd:Q17362920 .
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
} ORDER BY ?mod""".replace('\n', ' ')

    site = pywikibot.Site('wikidata', 'wikidata')

    generator = pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site)

    bot = DupesMergingBot(site=site, generator=generator, **options)
    bot.run()

if __name__ == "__main__":
    main()
