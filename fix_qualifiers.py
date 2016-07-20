# -*- coding: utf-8  -*-
import datetime
import pywikibot

from pywikibot import pagegenerators

start = datetime.datetime.now()

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

bad_cache = ['P143', 'P248', 'P405', 'P459', 'P518', 'P574', 'P577', 'P805', 'P972', 'P1135', 'P1480', 'P1545', 'P1932', 'P2701']
good_cache = ['P17', 'P21', 'P155', 'P156', 'P281', 'P580', 'P582', 'P585', 'P669', 'P969', 'P1355', 'P1356']

good_item = pywikibot.ItemPage(repo, 'Q15720608')

QUERY = """SELECT DISTINCT ?item WHERE {
  ?prop wikibase:propertyType [] .
  {
    ?prop p:P31/ps:P31 wd:Q15720608 .
    MINUS { ?prop wikibase:propertyType wikibase:ExternalId } .
  } UNION {
    FILTER( ?prop IN ( wd:%s ) ) .
  } .
  FILTER( ?prop NOT IN ( wd:%s ) ) .
  MINUS { ?prop p:P31/ps:P31 wd:Q18608359 } .
  ?prop wikibase:reference ?pr .
  ?ref ?pr ?value .
  ?statement prov:wasDerivedFrom ?ref .
  ?item ?p ?statement .
  [] wikibase:claim ?p .
} ORDER BY ?item""".replace('\n', ' ') % (', wd:'.join(good_cache), ', wd:'.join(bad_cache))

for item in pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site):
    item.get()
    for prop in item.claims.keys():
        for claim in item.claims[prop]:
            changed = False
            moved = []
            try:
                data = {"claims":[claim.toJSON()]}
            except Exception as exc:
                pywikibot.output("%s: %s" % (item.getID(), exc.message))
                break
            i = -1
            for source in claim.sources:
                i += 1
                for ref_prop in source.keys():
                    if ref_prop in bad_cache:
                        continue
                    if ref_prop not in good_cache:
                        prop_data = pywikibot.PropertyPage(repo, ref_prop)
                        prop_data.get()
                        if not prop_data.claims.has_key('P31'):
                            pywikibot.output("%s is not classified" % ref_prop)
                            bad_cache.append(ref_prop)
                            continue

                        for prop_claim in prop_data.claims['P31']:
                            if prop_claim.target_equals(good_item):
                                break
                        else:
                            bad_cache.append(ref_prop)
                            continue

                        good_cache.append(ref_prop)

                    for snak in source[ref_prop]:
                        if not data['claims'][0].has_key('qualifiers'):
                            data['claims'][0]['qualifiers'] = {}
                        if not data['claims'][0]['qualifiers'].has_key(ref_prop):
                            data['claims'][0]['qualifiers'][ref_prop] = []
                        snak.isReference = False
                        snak.isQualifier = True
                        data['claims'][0]['qualifiers'][ref_prop].append(snak.toJSON())
                        del data['claims'][0]['references'][i]['snaks'][ref_prop][0]
                        if len(data['claims'][0]['references'][i]['snaks'][ref_prop]) == 0:
                            del data['claims'][0]['references'][i]['snaks'][ref_prop]
                            if len(data['claims'][0]['references'][i]['snaks'].keys()) == 0:
                                del data['claims'][0]['references'][i]
                                i = i - 1
                        changed = True
                        if ref_prop not in moved:
                            moved.append(ref_prop)

            if changed is True:
                pywikibot.output("Fixing %s claim in %s" % (prop, item.getID()))
                moved = map(lambda x: '[[Property:P%s]]' % x, sorted(map(lambda x: int(x[1:]), moved)))
                summary = "[[Property:%s]]: moving misplaced reference%s %s to qualifiers" % (
                    prop, 's' if len(moved) > 1 else '', '%s and %s' % (
                        ', '.join(moved[:-1]), moved[-1]) if len(moved) > 1 else moved[0])
                item.editEntity(data, summary=summary)

end = datetime.datetime.now()

pywikibot.output("Complete! Took %s seconds" % (end - start).total_seconds())
