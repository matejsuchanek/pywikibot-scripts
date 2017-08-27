# -*- coding: utf-8 -*-
import pywikibot
import re

from pywikibot.data.sparql import SparqlQuery
from pywikibot.pagegenerators import (
    PreloadingItemGenerator,
    WikidataSPARQLPageGenerator,
)

from .query_store import QueryStore
from .wikidata import WikidataEntityBot

class ExternalIdSlicingBot(WikidataEntityBot):

    blacklist = ['P2013']

    def __init__(self, **options):
        self.availableOptions.update({
            'limit': 10,
            'offset': 0,
        })
        super(ExternalIdSlicingBot, self).__init__(**options)
        self.cache = {}
        self.failed = {}
        self.sparql = SparqlQuery(repo=self.repo)
        self.store = QueryStore()

    @property
    def generator(self):
        opts = dict(blacklist=' wd:'.join(self.blacklist),
                    limit=self.getOption('limit'))
        offset = self.getOption('offset')
        while True:
            pywikibot.output('\nLoading items (offset %i)...' % offset)
            opts['offset'] = offset
            ask = self.store.build_query('ask_externalid_props', **opts)
            if not self.sparql.ask(ask):
                break
            query = self.store.build_query('external-ids', **opts)
            gen = PreloadingItemGenerator(
                WikidataSPARQLPageGenerator(query, site=self.repo))
            for item in gen:
                yield item
            offset += limit

    def treat_page(self):
        item = self.current_page
        for prop, claims in item.claims.items():
            if prop in self.blacklist:
                continue
            if claims[0].type != 'external-id':
                continue
            for cl in claims:
                if not cl.target.startswith('http'):
                    continue
                formatter, regex = self.get_formatter_and_regex(prop)
                if not formatter:
                    pywikibot.output('%s doesn\'t have a formatter' % prop)
                    break
                value = self.find_value(cl.target, formatter)
                if not value:
                    pywikibot.output('Value not found in "%s" for property %s' % (
                        cl.target, prop))
                    if prop not in self.failed:
                        self.failed[prop] = set()
                    self.failed[prop].add(item)
                    continue
                if regex:
                    match = re.match('(%s)' % regex, value)
                    if not match:
                        pywikibot.output('Value "%s" not matched by regex "%s"' % (
                            value, regex))
                        if prop not in self.failed:
                            self.failed[prop] = set()
                        self.failed[prop].add(item)
                        continue
                    value = match.group()
                summary = 'harvested the identifier based on [[Property:P1630]]'
                if regex:
                    summary += ' and [[Property:P1793]]'
                cl.changeTarget(value, summary=summary)
    
    def get_formatter_and_regex(self, prop):
        if prop not in self.cache:
            formatter = regex = None
            ppage = pywikibot.PropertyPage(self.repo, prop)
            ppage.get()
            if 'P1630' in ppage.claims:
                if len(ppage.claims['P1630']) > 1:
                    preferred = list(filter(lambda x: x.rank == 'preferred',
                                            ppage.claims['P1630']))
                    if len(preferred) == 1:
                        formatter = preferred[0].target
                else:
                    formatter = ppage.claims['P1630'][0].target

            if 'P1793' in ppage.claims:
                if len(ppage.claims['P1793']) > 1:
                    preferred = list(filter(lambda x: x.rank == 'preferred',
                                            ppage.claims['P1793']))
                    if len(preferred) == 1:
                        regex = preferred[0].target
                else:
                    regex = ppage.claims['P1793'][0].target

            self.cache[prop] = (formatter, regex)

        return self.cache[prop]

    def strip_init_stuff(self, string):
        if string.startswith(('http://', 'https://')):
            string = string.partition('//')[2]
        if string.startswith('www.'):
            string = string[4:]
        return string

    def find_value(self, url, formatter):
        url = self.strip_init_stuff(url)
        formatter = self.strip_init_stuff(formatter)
        value = pywikibot.page.url2unicode(url)
        split = formatter.split('$1')
        if not value.startswith(split[0]):
            return
        if not split[1]:
            return value[len(split[0]):].rstrip('/')

        value = value[:-len(split[-1])]

        try:
            index = value.index(split[1], len(split[0]))
        except ValueError:
            return
        else:
            return value[len(split[0]):index].rstrip('/')

    def exit(self):
        super(ExternalIdSlicingBot, self).exit()
        if self.failed:
            pywikibot.output('\nFailed items:')
            for prop, items in self.failed.items():
                pywikibot.output('* [[Property:%s]]:' % prop)
                for item in items:
                    pywikibot.output('** [[%s]]' % item.title())

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True

    site = pywikibot.Site('wikidata', 'wikidata')
    bot = ExternalIdSlicingBot(site=site, **options)
    bot.run()

if __name__ == '__main__':
    main()
