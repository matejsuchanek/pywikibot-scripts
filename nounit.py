# -*- coding: utf-8  -*-
import datetime
import pywikibot

from pywikibot import pagegenerators

start = datetime.datetime.now()

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

QUERY = """SELECT DISTINCT ?item WHERE {
  {
    ?pst rdf:type wdno:P2237 .
  } UNION {
    ?pst ps:P2237 wd:Q21027105 .
  } .
  ?prop p:P2237 ?pst;
        wikibase:claim ?p;
        wikibase:statementValue ?psv;
        wikibase:qualifierValue ?pqv;
        wikibase:referenceValue ?prv .
  FILTER(?prop != wd:P1092) .
  {
    ?statement ?psv ?value .
    ?value wikibase:quantityUnit ?unit .
    ?item ?p ?statement .
  } UNION {
    ?statement1 ?pqv ?value .
    ?value wikibase:quantityUnit ?unit .
    ?item ?claim1 ?statement1 .
  } UNION {
    ?ref ?prv ?value .
    ?value wikibase:quantityUnit ?unit .
    ?statement2 prov:wasDerivedFrom ?ref .
    ?item ?claim2 ?statement2 .
  } .
  FILTER(?unit != wd:Q199) .
}""".replace('\n', ' ')

bad_cache = []
good_cache = []
good_item = pywikibot.ItemPage(repo, 'Q21027105')

def checkProp(prop):
    prop_data = pywikibot.PropertyPage(repo, prop)
    prop_data.get()
    if prop_data.type != "quantity":
        return False
    if 'P2237' not in prop_data.claims.keys():
        return False
    for claim in prop_data.claims['P2237']:
        if claim.snaktype == "novalue":
            continue
        if claim.snaktype == "value" and claim.target_equals(good_item):
            continue
        return False
    return True

for item in pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site):
    item.get()
    for prop in item.claims.keys():
        for claim in item.claims[prop]:
            if claim.type != "quantity":
                bad_cache.append(prop)
            if prop not in bad_cache:
                if prop not in good_cache:
                    if checkProp(prop):
                        good_cache.append(prop)
                    else:
                        bad_cache.append(prop)

                if prop in good_cache:
                    target = claim.getTarget()
                    if target is None:
                        continue
                    if target.unit == "1":
                        continue
                    target.unit = "1"
                    pywikibot.output("Removing unit in %s for property %s" % (item.getID(), prop))
                    claim.changeTarget(target, summary="removing invalid unit, see [[P:%s#P2237|property's page]]" % prop)

            data = {"claims":[claim.toJSON()]}
            changed = False
            for qprop in claim.qualifiers.keys():
                if qprop in bad_cache:
                    continue
                if qprop not in good_cache:
                    if checkProp(qprop):
                        good_cache.append(qprop)
                    else:
                        bad_cache.append(qprop)
                        continue
                i = -1
                for snak in claim.qualifiers[qprop]:
                    i += 1
                    target = snak.getTarget()
                    if target is None:
                        continue
                    if target.unit == "1":
                        continue
                    target.unit = "1"
                    snak.setTarget(target)
                    pywikibot.output("Removing unit in %s for qualifier %s of %s" % (item.getID(), qprop, prop))
                    data['claims'][0]['qualifiers'][qprop][i] = snak.toJSON()
                    changed = True

            i = -1
            for source in claim.sources:
                i += 1
                for ref_prop in source.keys():
                    if ref_prop in bad_cache:
                        continue
                    if ref_prop not in good_cache:
                        if checkProp(qprop):
                            good_cache.append(qprop)
                        else:
                            bad_cache.append(qprop)
                            continue

                    j = -1
                    for snak in source[ref_prop]:
                        j += 1
                        target = snak.getTarget()
                        if target is None:
                            continue
                        if target.unit == "1":
                            continue
                        target.unit = "1"
                        snak.setTarget(target)
                        pywikibot.output("Removing unit in %s for reference %s of %s" % (item.getID(), ref_prop, prop))
                        data['claims'][0]['references'][i]['snaks'][ref_prop][j] = snak.toJSON()
                        changed = True

            if changed is True:
                item.editEntity(data, summary="removing invalid unit(s)")

end = datetime.datetime.now()

pywikibot.output("Complete! Took %s seconds" % (end - start).total_seconds())
