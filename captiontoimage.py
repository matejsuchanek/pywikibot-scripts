# -*- coding: utf-8  -*-
import datetime
import pywikibot
from pywikibot import pagegenerators

start = datetime.datetime.now()

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

QUERY = """SELECT DISTINCT ?item WHERE { ?item p:P2096/ps:P2096 ?value }"""

for item in pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site):
    item.get()
    if item.claims.has_key('P2096'):
        our_prop = None
        if item.claims.has_key('P18'):
            our_prop = 'P18'
        else:
            for prop in item.claims.keys():
                prop_page = pywikibot.PropertyPage(repo, prop)
                if prop_page.type == "commonsMedia":
                    if our_prop is not None:
                        our_prop = False
                        break
                    else:
                        our_prop = prop

        if our_prop is None:
            pywikibot.output("%s contains no media property" % item.title())
            continue

        if our_prop is False:
            pywikibot.output("%s contains more than one media property" % item.title())
            continue

        if len(item.claims[our_prop]) > 1:
            pywikibot.output("There is more than one value for %s property in %s" % (our_prop, item.title()))
            continue

        media_claim = item.claims[our_prop][0]
        if media_claim.qualifiers.has_key('P2096'):
            pywikibot.output("%s property is already described in %s" % (our_prop, item.title()))
        else:
            qualifier = item.claims['P2096'][0]
            qualifier.isQualifier = True
            qualifier.setTarget(item.claims['P2096'][0].getTarget())
            media_claim.addQualifier(qualifier)

        site.removeClaims([item.claims['P2096'][0]])

end = datetime.datetime.now()

pywikibot.output("Complete! Took %s seconds" % (end - start).total_seconds())
