# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot

from pywikibot import pagegenerators, textlib
from pywikibot.bot import SingleSiteBot

from .typoloader import TypoRule, TyposLoader


class TypoReportBot(SingleSiteBot):

    pattern = '# {} – {}'

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'always': True,
            'anything': False,
            'outputpage': None,
            'typospage': None,
            'whitelistpage': None,
        })
        super(TypoReportBot, self).__init__(**kwargs)

    def setup(self):
        loader = TyposLoader(
            self.site, allrules=True, typospage=self.getOption('typospage'),
            whitelistpage=self.getOption('whitelistpage'))
        self.typoRules = loader.loadTypos()
        self.fp_page = loader.getWhitelistPage()
        self.whitelist = loader.loadWhitelist()
        self.data = []

    @property
    def generator(self):
        for rule in self.typoRules:
            if not rule.canSearch():
                continue

            pywikibot.output('Query: "%s"' % rule.query)
            self.current_rule = rule
            for page in pagegenerators.PreloadingGenerator(rule.querySearch()):
                yield page

    def skip_page(self, page):
        if page.title() in self.whitelist:
            pywikibot.warning('Skipped {} because it is whitelisted'
                              .format(page))
            return True

        if self.current_rule.find.search(page.title()):
            pywikibot.warning('Skipped {} because the rule matches its title'
                              .format(page))
            return True

        return super(TypoReportBot, self).skip_page(page)

    def treat(self, page):
        match = self.current_rule.find.search(page.text)
        if not match:
            return
        text = textlib.removeDisabledParts(
            page.text, TypoRule.exceptions, site=self.site)
        match = self.current_rule.find.search(text)
        if match:
            text = self.pattern.format(page.title(as_link=True), match.group(0))
            pywikibot.stdout(text)
            self.data.append(text)

    def teardown(self):
        outputpage = self.getOption('outputpage')
        if (self._generator_completed or self.getOption('anything')
                ) and outputpage:
            page = pywikibot.Page(self.site, outputpage)
            page.put('\n'.join(self.data),
                     summary='aktualizace seznamu překlepů',
                     apply_cosmetic_changes=False,
                     botflag=False, minor=False)
        super(TypoReportBot, self).teardown()


def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True

    bot = TypoReportBot(**options)
    bot.run()


if __name__ == '__main__':
    main()
