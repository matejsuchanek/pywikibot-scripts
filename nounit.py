# -*- coding: utf-8 -*-
import pywikibot

from pywikibot import pagegenerators

from .wikidata import WikidataEntityBot

class UnitsFixingBot(WikidataEntityBot):

    good_item = 'Q21027105'

    @property
    def generator(self):
        QUERY = '''
SELECT DISTINCT ?item WHERE {
  {
    ?pst rdf:type wdno:P2237 .
  } UNION {
    ?pst ps:P2237 wd:%s .
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
    FILTER(?unit != wd:Q199) .
    ?item ?p ?statement .
  } UNION {
    ?statement1 ?pqv ?value .
    ?value wikibase:quantityUnit ?unit .
    FILTER(?unit != wd:Q199) .
    ?item ?claim1 ?statement1 .
  } UNION {
    ?ref ?prv ?value .
    ?value wikibase:quantityUnit ?unit .
    FILTER(?unit != wd:Q199) .
    ?statement2 prov:wasDerivedFrom ?ref .
    ?item ?claim2 ?statement2 .
  } .
}'''.replace('\n', ' ') % self.good_item
        return pagegenerators.PreloadingItemGenerator(
            pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=self.repo))

    def filterProperty(self, prop_page):
        if prop_page.type != 'quantity':
            return False
        prop_page.get()
        if 'P2237' not in prop_page.claims.keys():
            return False
        for claim in prop_page.claims['P2237']:
            if claim.snaktype == 'novalue':
                continue
            if (claim.snaktype == 'value' and
                claim.target_equals(self.good_item)):
                continue
            return False
        return True

    def treat_page(self):
        item = self.current_page
        item.get() # fixme upstream
        for prop, claims in item.claims.items():
            for claim in claims:
                if claim.type == 'quantity':
                    if self.checkProperty(prop):
                        target = claim.getTarget()
                        if self.change_target(target):
                            pywikibot.output('Removing unit for property %s' % prop)
                            self._save_page(
                                item, self._save_entity, claim.changeTarget,
                                target, summary='removing invalid unit, see '
                                "[[P:%s#P2237|property's page]]" % prop)
                else:
                    self.bad_cache.add(prop)

                json = claim.toJSON()
                changed = False
                for qprop, snaks in claim.qualifiers.items():
                    if not self.checkProperty(qprop):
                        continue
                    new_snaks = snaks.copy()
                    if self.handle_snaks(new_snaks):
                        changed = True
                        json['qualifiers'][qprop] = new_snaks
                        #pywikibot.output("Removing unit for qualifier %s of %s" % (qprop, prop))

                for i, source in enumerate(claim.sources):
                    for ref_prop, snaks in source.items():
                        if not self.checkProperty(ref_prop):
                            continue
                        new_snaks = snaks.copy()
                        if self.handle_snaks(new_snaks):
                            changed = True
                            json['references'][i]['snaks'][ref_prop] = new_snaks
                            #pywikibot.output("Removing unit for reference %s of %s" % (ref_prop, prop))

                if changed is True:
                    data = {'claims': [json]}
                    self._save_page(item, self._save_entity, item.editEntity,
                                    data, summary='removing invalid unit(s)')

    def change_target(self, target):
        if target is None or target.unit == '1':
            return False

        target.unit = '1'
        return True

    def handle_snaks(self, snaks):
        changed = False
        for snak in snaks:
            target = snak.getTarget()
            if self.change_target(target):
                changed = True
                snak.setTarget(target)
        return changed

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = UnitsFixingBot(**options)
    bot.run()

if __name__ == '__main__':
    main()
