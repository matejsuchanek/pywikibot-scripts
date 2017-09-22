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
        'az': ' və ',
        'bg': ' и ',
        'br': ' ha ',
        'ca': ' i ',
        #'ceb':
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
        #'ja':
        'ka': ' და ',
        'la': ' et ',
        'ms': ' dan ',
        'nb': ' og ',
        'nl': ' en ',
        #'nn':
        'pl': ' i ',
        'pt': ' e ',
        'ro': ' și ',
        'ru': ' и ',
        'sk': ' a ',
        'sl': ' in ',
        'sr': ' и ',
        'sv': ' och ',
        'tr': ' ve ',
        #'uk':
        'vi': ' và ',
        #'war':
        #'zh':
    }
    distribute_properties = ('P21', 'P22', 'P25', 'P27', 'P106',)
    relation_map = {
        #'partner': 'P451', todo
        'sibling': 'P3373',
        'spouse': 'P26',
        'twin': 'P3373',
    }
    use_from_page = False

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'always': True,
            'class': 'Q15618652',
            'min_labels': 1,
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
        kwargs = {'class': self.getOption('class')}
        query = self.store.build_query('duos', **kwargs)
        return pagegenerators.PreloadingItemGenerator(
            pagegenerators.WikidataSPARQLPageGenerator(query, site=self.repo,
                                                       result_type=tuple))

    def get_relation(self, item, prop, cache, step):
        # TODO: use ASK query
        if step > 6:
            return None
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
                return None
            cache.append(target)
            relation = self.get_relation(target, 'P279', cache, step + 1)
            if relation:
                return relation

    def get_labels(self, item, relation):
        labels = [{}, {}]
        for lang in set(item.labels.keys()) & set(self.conj.keys()):
            for conj in (self.conj[lang], ' & '):
                label = item.labels[lang].partition(' (')[0]
                if ', ' in label:
                    continue
                split = label.split(conj)
                if len(split) != 2:
                    continue
                split0 = split[0].split()
                split1 = split[1].split()
                if split1[0].islower():
                    continue
                if len(split1) > len(split0):
                    if len(split1) > 2 and split1[-2].islower():
                        split1[-2:] = [' '.join(split1[-2:])]
                    if len(split1) - len(split0) == 1:
                        # if items are in a relation, then they probably share
                        # their surname
                        if relation:
                            split[0] += ' %s' % split1[-1]
                            split0.append(split1[-1])
                if len(split0) > 1 or len(split1) == 1:
                    for i in range(2):
                        labels[i][lang] = split[i]
                    break

        return labels

    def treat_page_and_item(self, page, item):
        relation = self.get_relation(item, 'P31', [], 0)
        labels = self.get_labels(item, relation)
        count = max(map(len, labels))
        if count < self.getOption('min_labels'):
            pywikibot.output('Too few labels (%i), skipping...' % count)
            return

        to_add = []
        to_remove = []
        for prop in set(self.distribute_properties) & set(item.claims.keys()):
            for claim in item.claims[prop]:
                if claim.getTarget():
                    json = claim.toJSON()
                    to_remove.append(json)
                    json = json.copy()
                    json.pop('id')
                    to_add.append(json)

        pywikibot.output('Creating items (relation "%s")...' % relation)
        items = [self.create_item(item, data, relation, to_add)
                 for data in labels]
        if self.relation_map.get(relation):
            for i in reversed(range(2)):
                claim = pywikibot.Claim(self.repo, self.relation_map[relation])
                claim.setTarget(items[1-i])
                self.user_add_claim(items[i], claim)

        for it in items:
            claim = pywikibot.Claim(self.repo, 'P527')
            claim.setTarget(it)
            self.user_add_claim(item, claim)

        for json in to_remove:
            json['remove'] = ''
            self.user_edit_entity(
                item, {'claims':[json]},
                summary='moved [[Property:%s]] to %s' % (
                    json['mainsnak']['property'], ' & '.join(map(methodcaller(
                        'title', asLink=True, insite=self.repo), items))))

    def create_item(self, item, labels, relation, to_add):
        new_item = pywikibot.ItemPage(self.repo)
        data = {'labels': labels}
        self.user_edit_entity(
            new_item, data, summary='based on data in %s' % item.title(
                asLink=True, insite=self.repo))

        claim = pywikibot.Claim(self.repo, 'P31')
        claim.setTarget(pywikibot.ItemPage(self.repo, 'Q5'))
        self.user_add_claim(new_item, claim)
        if relation == 'twin':
            claim = pywikibot.Claim(self.repo, 'P31')
            claim.setTarget(pywikibot.ItemPage(self.repo, 'Q159979'))
            self.user_add_claim(new_item, claim)

        claim = pywikibot.Claim(self.repo, 'P361')
        claim.setTarget(item)
        self.user_add_claim(new_item, claim)
        for json in to_add:
            self.user_edit_entity(
                new_item, {'claims':[json]},
                summary='moving [[Property:%s]] from %s' % (
                    json['mainsnak']['property'],
                    item.title(asLink=True, insite=self.repo)))
        return new_item

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
