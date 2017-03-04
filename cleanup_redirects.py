# -*- coding: utf-8 -*-
import csv
import re
import urllib

import pywikibot

from operator import methodcaller
from urllib.request import urlopen

from pywikibot.bot import MultipleSitesBot, RedirectPageBot

from .merger import Merger

class WikidataRedirectsBot(MultipleSitesBot, RedirectPageBot):

    labs_url = 'https://tools.wmflabs.org'
    sub_directory = 'wikidata-redirects-conflicts-reports/reports'
    namespaces = set((0, 10, 14))
    ignore = {'ignore_save_related_errors': True,
              'ignore_server_errors': True,
              }

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'always': False,
            'date': None,
            'force': False,
            'skip': [],
            'start': None,
            'touch': False,
        })
        super(WikidataRedirectsBot, self).__init__(**kwargs)

    @property
    def generator(self):
        if not self.getOption('date'):
            self.options['date'] = pywikibot.input(
                'Enter the date when the reports were created')

        url = '%s/%s/%s/' % (self.labs_url, self.sub_directory,
                             self.getOption('date'))
        response = urlopen(url)
        regex = re.compile('href="([^"]+)"')
        not_yet = bool(self.getOption('start'))
        for match in regex.finditer(response.read().decode()):
            file_name = match.group(1)
            dbname = file_name.partition('-')[0]
            if not_yet:
                if dbname == self.getOption('start'):
                    not_yet = False
                else:
                    continue

            if dbname in self.getOption('skip'):
                continue

            try:
                site = pywikibot.site.APISite.fromDBName(dbname)
            except ValueError as e:
                pywikibot.exception(e)
                continue

            pywikibot.output('Working on \'%s\'' % dbname)
            resp = urlopen(url + file_name)
            lines = resp.readlines()
            if not lines:
                continue
            lines.pop(0)
            f = map(methodcaller('decode', 'utf-8'), lines)
            for row in csv.reader(f, delimiter='\t'):
                if len(set(row[1:3])) > 1:
                    continue
                if int(row[1]) not in self.namespaces:
                    continue
                if '#' in row[4]:
                    continue

                yield pywikibot.Page(site, row[3], ns=int(row[1]))

    def user_confirm(self, *args):
        return True

    def treat_page(self):
        page = self.current_page
        items = []
        try:
            items.append(page.data_item())
        except pywikibot.NoPage:
            return

        target = page.getRedirectTarget()
        try:
            items.append(target.data_item())
        except pywikibot.NoPage:
            self._save_page(items[0], items[0].setSitelink, target,
                            **self.ignore) # todo: summary
            return

        summary = 'based on [[toollabs:%s/%s/|Alphos\' reports]]' % (
            self.sub_directory, self.getOption('date'))

        Merger.sort_for_merge(items, key=['sitelinks', 'id'])
        if not self._save_page(items[1], Merger.clean_merge, items[1], items[0],
                               safe=not self.getOption('force'),
                               ignore_conflicts=['description'],
                               summary=summary, **self.ignore):
            return

        if self.getOption('touch') is True:
            self._save_page(target, target.touch, **self.ignore)

def main(*args):
    options = {}
    skip = []
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-skip:'):
            skip.append(arg.partition(':')[2])
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = WikidataRedirectsBot(skip=skip, **options)
    bot.run()

if __name__ == '__main__':
    main()
