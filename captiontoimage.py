# -*- coding: utf-8  -*-
import datetime
import pywikibot
from pywikibot import pagegenerators

start = datetime.datetime.now()

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

QUERY = """SELECT DISTINCT ?item WHERE { ?item p:P2096/ps:P2096 ?value }"""

good_cache = []

for item in pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site):
    item.get()
    if not item.claims.has_key('P2096'):
        continue

    our_prop = None
    if item.claims.has_key('P18'):
        our_prop = 'P18'
    else:
        for prop in item.claims.keys():
            if prop not in good_cache:
                prop_page = pywikibot.PropertyPage(repo, prop)
                if prop_page.type == "commonsMedia":
                    good_cache.append(prop)

            if prop in good_cache:
                if our_prop is not None:
                    our_prop = False
                    break
                else:
                    our_prop = prop

    if our_prop is None:
        pywikibot.output("%s: No media property found" % item.title())
        continue

    if our_prop is False:
        pywikibot.output("%s: More than one media property used" % item.title())
        continue

    if len(item.claims[our_prop]) > 1:
        pywikibot.output("%s: More than one value for %s property" % (item.title(), our_prop))
        continue

    media_claim = item.claims[our_prop][0]
    qualifier = item.claims['P2096'][0]
    target = qualifier.getTarget()
    if media_claim.qualifiers.has_key('P2096'):
        has_same_lang = False
        for claim in media_claim.qualifiers['P2096']:
            if claim.getTarget().language == target.language:
                has_same_lang = True
                break
        if has_same_lang is True:
            pywikibot.output("%s: %s property already has a description in language %s" % (item.title(), our_prop, target.language))
            continue

    qualifier.isQualifier = True
    media_claim.addQualifier(qualifier)
    site.removeClaims([item.claims['P2096'][0]])

end = datetime.datetime.now()

pywikibot.output("Complete! Took %s seconds" % (end - start).total_seconds())
