#!/usr/bin/python
import pywikibot

from pywikibot import pagegenerators
from pywikibot.data.sparql import SparqlQuery

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class DuosManagingBot(WikidataEntityBot):

    conj = {
        'af': ' en ',
        'az': ' və ',
        'bg': ' и ',
        'br': ' ha ',
        'ca': ' i ',
        'cs': ' a ',
        'cy': ' a ',
        'da': ' og ',
        'de': ' und ',
        'el': ' και ',
        'en': ' and ',
        'en-ca': ' and ',
        'en-gb': ' and ',
        'en-us': ' and ',
        'eo': ' kaj ',
        'es': ' y ',
        'et': ' ja ',
        'eu': ' eta ',
        'fi': ' ja ',
        'fr': ' et ',
        'fy': ' en ',
        'gl': ' e ',
        'hr': ' i ',
        'hu': ' és ',
        'id': ' dan ',
        'it': ' e ',
        'ka': ' და ',
        'la': ' et ',
        'lt': ' ir ',
        'lv': ' un ',
        'ms': ' dan ',
        'nb': ' og ',
        'nl': ' en ',
        'nn': ' og ',
        'oc': ' e ',
        'pl': ' i ',
        'pt': ' e ',
        'ro': ' și ',
        'ru': ' и ',
        'sk': ' a ',
        'sl': ' in ',
        'sr': ' и ',
        'sv': ' och ',
        'tr': ' ve ',
        'uk': ' і ',
        'vi': ' và ',
        'war': ' ngan ',
    }
    distribute_properties = [
        'P21', 'P22', 'P25', 'P27', 'P40', 'P53', 'P106', 'P1412',
    ]
    class_to_relation = [
        ('Q106925878', 'father-son'),
        ('Q14756018', 'twin'),
        ('Q14073567', 'sibling'),
        ('Q3046146', 'spouse'),
        # TODO: ('Q1141470', 'comedians'), not a "relation by blood"
    ]
    relation_map = {
        'sibling': 'P3373',
        'spouse': 'P26',
        'twin': 'P3373',
        # TODO: 'partner': 'P451',
        #'father-son': '', we don't know who is who
        #'comedians': 'P1327',
    }
    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.available_options.update({
            'always': True,
            'class': 'Q10648343',
            'min_labels': 1,
        })
        super().__init__(**kwargs)
        self.store = QueryStore()
        self.sparql = SparqlQuery(repo=self.repo)
        self._generator = generator or self.custom_generator()

    def skip_page(self, item):
        if super().skip_page(item):
            return True
        if 'P31' not in item.claims:
            pywikibot.info(f'{item} is missing P31 property')
            return True
        if 'P527' in item.claims:
            pywikibot.info(f'{item} already has P527 property')
            return True
        return False

    def custom_generator(self):
        kwargs = {'class': self.opt['class']}
        query = self.store.build_query('duos', **kwargs)
        return pagegenerators.WikidataSPARQLPageGenerator(query, site=self.repo)

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self._generator)

    def get_relation(self, item):
        ask_pattern = 'ASK { wd:%s wdt:P31/wdt:P279* wd:%%s }' % item.id
        for key, rel in self.class_to_relation:
            if self.sparql.ask(ask_pattern % key):
                return rel
        return None

    def get_labels(self, item, relation):
        labels = [{}, {}]
        for lang in item.labels.keys() & self.conj.keys():
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
                # TODO: if len(split1) > 1 and split1[0][-1] == '.':
                if len(split1) > len(split0):
                    if len(split1) > 2 and split1[-2].islower():
                        split1[-2:] = [' '.join(split1[-2:])]
                    if len(split1) - len(split0) == 1:
                        # if items are in a relation, then
                        # they probably share their surname
                        if relation:
                            split[0] += ' %s' % split1[-1]
                            split0.append(split1[-1])
                if len(split0) > 1 or len(split1) == 1:
                    labels[0][lang] = split[0]
                    labels[1][lang] = split[1]
                    break

        return labels

    def treat_page_and_item(self, page, item):
        relation = self.get_relation(item)
        labels = self.get_labels(item, relation)
        count = max(map(len, labels))
        if count == 0:
            pywikibot.info('No labels, skipping...')
            return

        if count < self.opt['min_labels']:
            pywikibot.info(f'Too few labels ({count}), skipping...')
            return

        to_add = []
        to_remove = []
        if relation == 'twin':
            distribute = self.distribute_properties + ['P569', 'P19']
        else:
            distribute = self.distribute_properties
        for prop in distribute:
            for claim in item.claims.get(prop, []):
                if claim.getTarget():
                    to_remove.append(claim)
                    json = claim.toJSON()
                    json.pop('id')
                    to_add.append(json)

        items = [self.create_item(item, data, relation, to_add)
                 for data in labels]
        if self.relation_map.get(relation):
            for it, target in zip(items, reversed(items)):
                claim = pywikibot.Claim(self.repo, self.relation_map[relation])
                claim.setTarget(target)
                self.user_add_claim(it, claim)

        for it in items:
            claim = pywikibot.Claim(self.repo, 'P527')
            claim.setTarget(it)
            self.user_add_claim(item, claim)

        for claim in to_remove:
            pywikibot.info('Removing %s --> %s' % (
                claim.id, claim.getTarget()))
            json = claim.toJSON()
            json['remove'] = ''
            summary = 'moved [[Property:{}]] to {} & {}'.format(
                claim.id,
                items[0].title(as_link=True, insite=self.repo),
                items[1].title(as_link=True, insite=self.repo)
            )
            self.user_edit_entity(item, {'claims':[json]}, summary=summary)

    def create_item(self, item, labels, relation, to_add):
        pywikibot.info(f'Creating item (relation "{relation}")...')
        new_item = pywikibot.ItemPage(self.repo)
        self.user_edit_entity(
            new_item,
            {'labels': labels},
            asynchronous=False,
            summary='based on data in %s' % item.title(
                as_link=True, insite=self.repo))

        claim = pywikibot.Claim(self.repo, 'P31')
        claim.setTarget(pywikibot.ItemPage(self.repo, 'Q5'))
        self.user_add_claim(new_item, claim)
        claim = pywikibot.Claim(self.repo, 'P361')
        claim.setTarget(item)
        self.user_add_claim(new_item, claim)
        for json in to_add:
            temp_claim = pywikibot.Claim.fromJSON(self.repo, json)
            pywikibot.info('Adding %s --> %s' % (
                temp_claim.id, temp_claim.getTarget()))
            self.user_edit_entity(
                new_item, {'claims':[json]},
                summary='moving [[Property:%s]] from %s' % (
                    temp_claim.id,
                    item.title(as_link=True, insite=self.repo)))
        return new_item


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = pagegenerators.GeneratorFactory(site=site)
    for arg in genFactory.handle_args(local_args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    bot = DuosManagingBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
