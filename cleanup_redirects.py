#!/usr/bin/python
import csv
import re
import urllib

from operator import methodcaller
from urllib.request import urlopen

import pywikibot

from pywikibot.bot import WikidataBot
from pywikibot.exceptions import NoPageError

from merger import Merger


class WikidataRedirectsBot(WikidataBot):

    labs_url = 'https://tools.wmflabs.org'
    sub_directory = 'wikidata-redirects-conflicts-reports/reports'
    namespaces = {0, 10, 14}
    ignore = {'ignore_save_related_errors': True,
              'ignore_server_errors': True,
              }
    treat_missing_item = False
    use_redirects = True

    def __init__(self, **kwargs):
        self.available_options.update({
            'always': False,
            'date': None,
            'force': False,
            'skip': [],
            'start': None,
            'touch': False,
        })
        super().__init__(**kwargs)

    @property
    def generator(self):
        if not self.opt['date']:
            self.options['date'] = pywikibot.input(
                'Enter the date when the reports were created')

        url = f"{self.labs_url}/{self.sub_directory}/{self.opt['date']}/"
        response = urlopen(url)
        regex = re.compile('href="([^"]+)"')
        not_yet = bool(self.opt['start'])
        for match in regex.finditer(response.read().decode()):
            file_name = match[1]
            dbname = file_name.partition('-')[0]
            if not_yet:
                if dbname == self.opt['start']:
                    not_yet = False
                else:
                    continue

            if dbname in self.opt['skip']:
                continue

            try:
                site = pywikibot.site.APISite.fromDBName(dbname)
            except ValueError as e:
                pywikibot.exception(e)
                continue

            pywikibot.info(f"Working on '{dbname}'")
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

    @property
    def summary(self):
        return (f"based on [[toollabs:{self.sub_directory}/{self.opt['date']}/"
                "|Alphos' reports]]")

    def user_confirm(self, *args):
        return True

    def treat_page_and_item(self, page, item):
        items = [item]

        target = page.getRedirectTarget()
        try:
            items.append(target.data_item())
            target.get()
        except NoPageError:
            self._save_page(items[0], items[0].setSitelink, target,
                            **self.ignore)  # todo: summary
            return

        Merger.sort_for_merge(items, key=['sitelinks', 'id'])
        if not self._save_page(items[1], Merger.clean_merge, items[1], items[0],
                               safe=not self.opt['force'],
                               ignore_conflicts=['description'],
                               summary=self.summary, **self.ignore):
            return

        if self.opt['touch'] is True:
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
