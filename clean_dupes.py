# -*- coding: utf-8  -*-
import pywikibot

from pywikibot import pagegenerators

from pywikibot.bot import SkipPageError

from scripts.wikidata import WikidataEntityBot

class DupesMergingBot(WikidataEntityBot):

    def __init__(self, site, **kwargs):
        super(DupesMergingBot, self).__init__(site, **kwargs)
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

        if 'P460' in item.claims.keys():
            for claim in item.claims['P460']:
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

        sitelinks = []
        target_sitelinks = []
        while target.isRedirectPage():
            pywikibot.warning("Target %s is redirect" % target.getID())
            target = target.getRedirectTarget()

        target.get()
        for dbname, sitelink in item.sitelinks.items():
            if dbname in target.sitelinks.keys():
                apisite = pywikibot.site.APISite.fromDBName(dbname)
                page = pywikibot.Page(apisite, sitelink)
                if not page.exists():
                    sitelinks.append(dbname)
                    continue
                target_page = pywikibot.Page(apisite, target.sitelinks[dbname])
                if not target_page.exists():
                    target_sitelinks.append(dbname)
                    continue
                if self.redirectsTo(page, target_page) or self.redirectsTo(target_page, page):
                    continue

                pywikibot.output("Target has a conflicting sitelink: %s" % dbname)
                return

        target_claims = []
        if 'P460' in target.claims.keys():
            for claim in target.claims['P460']:
                if claim.snaktype != 'value':
                    continue
                if claim.target_equals(item):
                    target_claims.append(claim)

        if 'P31' in target.claims.keys():
            for claim in target.claims['P31']:
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

        data = {'descriptions': {}}
        for lang in item.descriptions.keys():
            if lang in target.descriptions.keys():
                if item.descriptions[lang] != target.descriptions[lang]:
                    data['descriptions'][lang] = ''
        if len(data['descriptions']) > 0:
            self._save_page(item, self._save_entity, item.editEntity, data,
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

    options['generator'] = pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site)

    bot = DupesMergingBot(site, **options)
    bot.run()

if __name__ == "__main__":
    main()
