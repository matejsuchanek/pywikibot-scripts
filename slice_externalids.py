#!/usr/bin/python
import re

import pywikibot

from pywikibot.data.sparql import SparqlQuery
from pywikibot.pagegenerators import (
    PreloadingEntityGenerator,
    WikidataSPARQLPageGenerator,
)

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class ExternalIdSlicingBot(WikidataEntityBot):

    blacklist = {'P2013'}
    use_from_page = False

    def __init__(self, **options):
        self.available_options.update({
            'step': 10,
            'offset': 0,
        })
        super().__init__(**options)
        self.cache = {}
        self.failed = {}
        self.sparql = SparqlQuery(repo=self.repo)
        self.store = QueryStore()

    @property
    def generator(self):
        step = self.opt['step']
        opts = {
            # fixme: don't use this word
            'blacklist': ' wd:'.join(self.blacklist),
            'limit': step,
        }
        offset = self.opt['offset']
        while True:
            pywikibot.output('\nLoading items (offset %i)...' % offset)
            opts['offset'] = offset
            ask = self.store.build_query('ask_externalid_props', **opts)
            if not self.sparql.ask(ask):
                break
            query = self.store.build_query('external-ids', **opts)
            gen = PreloadingEntityGenerator(
                WikidataSPARQLPageGenerator(query, site=self.repo))
            yield from gen
            offset += step

    def treat_page_and_item(self, page, item):
        for prop, claims in item.claims.items():
            if prop in self.blacklist:
                continue
            if claims[0].type != 'external-id':
                continue
            for cl in claims:
                if not cl.target or not cl.target.startswith('http'):
                    continue
                formatter, regex = self.get_formatter_and_regex(prop)
                if not formatter:
                    pywikibot.output("%s doesn't have a formatter" % prop)
                    break
                value = self.find_value(cl.target, formatter)
                if not value:
                    pywikibot.output('Value not found in "%s" for property %s'
                                     % (cl.target, prop))
                    self.failed.setdefault(prop, set()).add(item)
                    continue
                if regex:
                    try:
                        match = re.match('(%s)' % regex, value)
                    except re.error:
                        pywikibot.output('Couldn\'t apply regex "%s"' % regex)
                        break
                    if not match:
                        pywikibot.output('Value "%s" not matched by regex '
                                         '"%s"' % (value, regex))
                        self.failed.setdefault(prop, set()).add(item)
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
            if 'P1630' in ppage.claims:
                if len(ppage.claims['P1630']) > 1:
                    preferred = [cl for cl in ppage.claims['P1630']
                                 if cl.rank == 'preferred']
                    if len(preferred) == 1:
                        formatter = preferred[0].target
                else:
                    formatter = ppage.claims['P1630'][0].target

            if 'P1793' in ppage.claims:
                if len(ppage.claims['P1793']) > 1:
                    preferred = [cl for cl in ppage.claims['P1793']
                                 if cl.rank == 'preferred']
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
            return None
        if not split[1]:
            return value[len(split[0]):].rstrip('/')

        value = value[:-len(split[-1])]

        try:
            index = value.index(split[1], len(split[0]))
        except ValueError:
            return None
        else:
            return value[len(split[0]):index].rstrip('/')

    def exit(self):
        if self.failed:
            text = ''
            for prop in sorted(self.failed):
                text += '* [[Property:%s]]:\n' % prop
                for item in sorted(self.failed[prop]):
                    text += '** [[%s]]\n' % item.title()
            page = pywikibot.Page(
                self.repo, 'User:%s/Wrong external ids' % self.repo.username())
            page.put(text, summary='update')
        super().exit()


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
