# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re

from datetime import datetime
from itertools import chain

from pywikibot import i18n, textlib
from pywikibot.bot import ExistingPageBot, SingleSiteBot, NoRedirectPageBot
from pywikibot.pagegenerators import (
    PreloadingGenerator,
    SearchPageGenerator,
)

birth = {
    'wikipedia': {
        'cs': r'Narození (\d+)',
    },
}

death = {
    'wikipedia': {
        'cs': 'Úmrtí %d',
    },
}

replace_pattern = '[[{inside}]] ({left}{year1}{right}–{left}{year2}{right})'


class DeathDateUpdatingBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'year': datetime.today().year,
        })
        super(DeathDateUpdatingBot, self).__init__(**kwargs)
        self.categoryR = re.compile(i18n.translate(self.site, birth))
        self.year = self.getOption('year')

    @property
    def generator(self):
        while True:
            category = pywikibot.Category(
                self.site, i18n.translate(self.site, death) % self.year)
            for page in category.articles(content=True, namespaces=[0]):
                yield page
            self.year -= 1

    def treat_page(self):
        page = self.current_page
        categories = textlib.getCategoryLinks(page.text, site=self.site)
        titles = map(
            lambda cat: cat.title(with_ns=False, with_section=False,
                                  allow_interwiki=False, insite=self.site),
            categories)
        matches = list(filter(bool, map(self.categoryR.fullmatch, titles)))
        if not matches:
            pywikibot.output('No birthdate category found')
            return
        fullmatch = matches.pop()
        if matches:
            pywikibot.output('Multiple birthdate categories found')
            return
        birth_date = fullmatch.group(1)
        search_query = 'linksto:"%s"' % page.title()
        search_query += r' insource:/\[\[[^\[\]]+\]\]'
        search_query += r' +\(\* *\[*%s\]*\)/' % birth_date
        search_query += ' -intitle:"Seznam"'
        pattern = r'\[\[((?:%s)(?:\|[^\[\]]+)?)\]\]' % '|'.join(
            map(lambda p: re.escape(p.title()),
                chain([page], page.backlinks(
                    followRedirects=False, filterRedirects=True,
                    namespaces=[0]))))
        pattern += r' +\(\* *(\[\[)?(%s)(\]\])?\)' % birth_date
        regex = re.compile(pattern)
        for ref_page in PreloadingGenerator(
                SearchPageGenerator(
                    search_query, namespaces=[0], site=self.site)):
            text = ref_page.text
            # todo: multiple matches
            match = regex.search(text)
            if not match:
                continue
            inside, left, year1, right = match.groups('')
            new_text = text[:match.start()]
            new_text += replace_pattern.format(
                inside=inside, left=left, right=right, year1=year1,
                year2=self.year)
            new_text += text[match.end():]
            self.userPut(ref_page, ref_page.text, new_text,
                         summary='doplnění data úmrtí')


def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = DeathDateUpdatingBot(**options)
    bot.run()


if __name__ == '__main__':
    main()
