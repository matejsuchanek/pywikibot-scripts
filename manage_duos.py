# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot

from operator import methodcaller

from pywikibot import pagegenerators

from pywikibot.bot import SkipPageError

from .query_store import QueryStore
from .wikidata import WikidataEntityBot

class DuosManagingBot(WikidataEntityBot):

    conj = {
        'af': ' en ',
        'br': ' ha ',
        'ca': ' i ',
        'cs': ' a ',
        'da': ' og ',
        'de': ' und ',
        'el': ' και ',
        'en': ' and ',
        'en-gb': ' and ',
        'eo': ' kaj ',
        'es': ' y ',
        'et': ' ja ',
        'eu': ' eta ',
        'fi': ' ja ',
        'fr': ' et ',
        'fy': ' en ',
        'hr': ' i ',
        'hu': ' és ',
        'id': ' dan ',
        'it': ' e ',
        'la': ' et ',
        'nl': ' en ',
        #'nn':
        'nb': ' og ',
        'pl': ' i ',
        'pt': ' e ',
        'ro': ' și ',
        'ru': ' и ',
        'sk': ' a ',
        #'sr':
        'sv': ' och ',
        'tr': ' ve ',
    }
    relation_map = {
        'partner': 'P451',
        'sibling': 'P3373',
        'spouse': 'P26',
        'twin': 'P3373',
    }

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'min_labels': 1
        })
        super(DuosManagingBot, self).__init__(**kwargs)
        self.store = QueryStore()

    def init_page(self, item):
        super(DuosManagingBot, self).init_page(item)
        if 'P31' not in item.claims:
            raise SkipPageError(item, 'Missing P31 property')
        if 'P527' in item.claims:
            raise SkipPageError(item, 'Has P527 property')

    @property
    def generator(self):
        query = self.store.get_query('duos')
        return pagegenerators.PreloadingItemGenerator(
            pagegenerators.WikidataSPARQLPageGenerator(query, site=self.repo,
                                                       result_type=tuple))

    def get_relation(self, item, prop, cache, step):
        if step > 6:
            return
        for claim in item.get()['claims'].get(prop, []):
            if claim.target_equals('Q15618652'):
                continue
            if claim.target_equals('Q14756018'):
                return 'twin'
            if claim.target_equals('Q3046146'):
                return 'spouse'
            if claim.target_equals('Q14073567'):
                return 'sibling'
            target = claim.getTarget()
            if target in cache:
                return
            cache.append(target)
            relation = self.get_relation(target, 'P279', cache, step + 1)
            if relation:
                return relation

    def get_labels(self, item, relation):
        labels = [{}, {}]
        for lang in set(item.labels.keys()) & set(self.conj.keys()):
            for conj in (self.conj[lang], ' & '):
                split = item.labels[lang].partition(' (')[0].split(conj)
                if len(split) != 2:
                    continue
                split0 = split[0].split()
                split1 = split[1].split()
                if len(split1) - len(split0) == 1:
                    if relation:
                        split[0] += ' %s' % split1[-1]
                        split0.append(split1[-1])
                if len(split0) == len(split1):
                    for i in range(2):
                        labels[i][lang] = split[i]
                    break

        return labels

    def treat_page(self):
        item = self.current_page
        relation = self.get_relation(item, 'P31', [], 0)
        labels = self.get_labels(item, relation)
        if sum(map(len, labels)) < self.getOption('min_labels'):
            pywikibot.output('Too few labels (%i)' % sum(map(len, labels)))
            return

        pywikibot.output('Creating items (relation: %s)...' % relation)
        items = [self.create_item(data, relation) for data in labels]
        for i in range(2):
            claim = pywikibot.Claim(self.repo, 'P527')
            claim.setTarget(items[i])
            item.addClaim(claim)
            if relation in self.relation_map:
                claim = pywikibot.Claim(self.repo, self.relation_map[relation])
                claim.setTarget(items[(set(range(2)) - set([i])).pop()])
                items[i].addClaim(claim)

        for prop in ('P21', 'P27', 'P106'):
            for claim in item.claims.get(prop, [])[:]:
                json = claim.toJSON()
                if claim.getTarget():
                    json.pop('id')
                    for it in items:
                        it.editEntity({'claims':[json]},
                                      summary='moving [[Property:%s]] from %s'
                                      % (prop, item.title(asLink=True,
                                                          insite=self.repo)))
                    json = claim.toJSON()
                json['remove'] = ''
                item.editEntity(
                    {'claims':[json]}, summary='moved [[Property:%s]] to %s' % (
                        prop, ' & '.join(map(methodcaller(
                            'title', asLink=True, insite=self.repo), items))))

    def create_item(self, labels, relation):
        item = pywikibot.ItemPage(self.repo)
        data = {'labels': labels}
        item.editEntity(data, summary='based on data in %s' %
                        self.current_page.title(asLink=True, insite=self.repo))

        claim = pywikibot.Claim(self.repo, 'P31')
        claim.setTarget(pywikibot.ItemPage(self.repo, 'Q5'))
        item.addClaim(claim)
        if relation == 'twin':
            claim = pywikibot.Claim(self.repo, 'P31')
            claim.setTarget(pywikibot.ItemPage(self.repo, 'Q159979'))
            item.addClaim(claim)

        claim = pywikibot.Claim(self.repo, 'P361')
        claim.setTarget(self.current_page)
        item.addClaim(claim)
        return item

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = DuosManagingBot(**options)
    bot.run()

if __name__ == '__main__':
    main()
