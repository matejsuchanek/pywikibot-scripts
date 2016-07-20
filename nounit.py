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

for item in pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site):
    item.get()
    for prop in item.claims.keys():
        for claim in item.claims[prop]:
            if claim.type == "quantity":
                if prop in bad_cache:
                    break
                if prop not in good_cache:
                    prop_data = pywikibot.PropertyPage(repo, prop)
                    prop_data.get()
                    ok = False
                    if prop_data.claims.has_key('P2237'):
                        ok = True
                        for prop_claim in prop_data.claims['P2237']:
                            if prop_claim.snaktype == "novalue":
                                continue
                            if prop_claim.target_equals(good_item):
                                continue
                            ok = False
                            break

                    if ok is False:
                        bad_cache.append(prop)
                        break

                good_cache.append(prop)
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
                i = -1
                for snak in claim.qualifiers[qprop]:
                    i += 1
                    if snak.type != "quantity":
                        break
                    if qprop in bad_cache:
                        break
                    if qprop not in good_cache:
                        qprop_data = pywikibot.PropertyPage(repo, qprop)
                        qprop_data.get()
                        ok = False
                        if qprop_data.claims.has_key('P2237'):
                            ok = True
                            for qprop_claim in qprop_data.claims['P2237']:
                                if qprop_claim.snaktype == "novalue":
                                    continue
                                if qprop_claim.target_equals(good_item):
                                    continue
                                ok = False
                                break

                        if ok is False:
                            bad_cache.append(qprop)
                            break

                    good_cache.append(qprop)
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
                        ref_prop_data = pywikibot.PropertyPage(repo, ref_prop)
                        ref_prop_data.get()
                        if not ref_prop_data.claims.has_key('P2237'):
                            continue
                        for ref_prop_claim in ref_prop_data.claims['P2237']:
                            if ref_prop_claim.snaktype != "novalue":
                                if not ref_prop_claim.target_equals(good_item):
                                    ok = False
                                    break

                        if ok is False:
                            bad_cache.append(ref_prop)
                            continue

                    good_cache.append(ref_prop)
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
