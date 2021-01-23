#!/usr/bin/python
import re

from collections import defaultdict

import pywikibot

from pywikibot import textlib
from pywikibot.bot import SingleSiteBot, ExistingPageBot
from pywikibot.pagegenerators import PreloadingGenerator
from pywikibot.tools import itergroup

from .typoloader import TypoRule, TyposLoader


class TypoReportBot(SingleSiteBot):

    pattern = '# {} \u2013 {}'

    def __init__(self, **kwargs):
        self.available_options.update({
            'always': True,
            'anything': False,
            'outputpage': None,
            'typospage': None,
            'whitelistpage': None,
        })
        super().__init__(**kwargs)
        self.loader = TyposLoader(
            self.site, allrules=True, typospage=self.opt['typospage'],
            whitelistpage=self.opt['whitelistpage'])

    def setup(self):
        self.typoRules = self.loader.loadTypos()
        self.fp_page = self.loader.getWhitelistPage()
        self.whitelist = self.loader.loadWhitelist()
        self.data = []

    @property
    def generator(self):
        for rule in self.typoRules:
            if not rule.canSearch():
                continue

            pywikibot.output('Query: "%s"' % rule.query)
            self.current_rule = rule
            yield from PreloadingGenerator(rule.querySearch())

    def skip_page(self, page):
        if page.title() in self.whitelist:
            pywikibot.warning('Skipped {} because it is whitelisted'
                              .format(page))
            return True

        if self.current_rule.find.search(page.title()):
            pywikibot.warning('Skipped {} because the rule matches its title'
                              .format(page))
            return True

        return super().skip_page(page)

    def remove_disabled_parts(self, text):
        return textlib.removeDisabledParts(
            text, TypoRule.exceptions, site=self.site)

    def treat(self, page):
        match = self.current_rule.find.search(page.text)
        if not match:
            return
        text = self.remove_disabled_parts(page.text)
        match = self.current_rule.find.search(text)
        if match:
            text = self.pattern.format(page.title(as_link=True), match.group(0))
            pywikibot.stdout(text)
            self.data.append(text)

    def teardown(self):
        outputpage = self.opt['outputpage']
        if (self._generator_completed or self.opt['anything']
                ) and outputpage:
            page = pywikibot.Page(self.site, outputpage)
            page.text = '\n'.join(self.data)
            page.save(summary='aktualizace seznamu překlepů', minor=False,
                      botflag=False, apply_cosmetic_changes=False)
        super().teardown()


class PurgeTypoReportBot(SingleSiteBot, ExistingPageBot):

    def __init__(self, **kwargs):
        super().__init__()
        self.helper = TypoReportBot(**kwargs)

    def setup(self):
        super().setup()
        self.whitelist = self.helper.loader.loadWhitelist()
        outputpage = self.helper.opt['outputpage']
        self.generator = [pywikibot.Page(self.site, outputpage)]
        self.put = []
        self.cache = defaultdict(list)

    def line_iterator(self, page):
        regex = re.compile(self.helper.pattern.format(
            r'\[\[([^]]+)\]\]', '(.+)'))
        for line in page.text.splitlines():
            match = regex.fullmatch(line)
            if match:
                title, text = match.groups()
                entry = pywikibot.Page(self.site, title)
                self.cache[entry.title()].append(text)
                yield entry
            else:
                self.put.append(line)

    def treat(self, page):
        pattern = self.helper.pattern
        for entry in PreloadingGenerator(self.line_iterator(page)):
            key = title = entry.title()
            if not entry.exists():
                self.cache.pop(key)
                continue
            while entry.isRedirectPage():
                entry = entry.getRedirectTarget()
                title = entry.title()
            text = self.helper.remove_disabled_parts(entry.text)
            for string in self.cache.pop(key):
                if string in text:
                    self.put.append(pattern.format('[[%s]]' % title, string))

        page.text = '\n'.join(self.put)
        page.save(summary='odstranění vyřešených překlepů', minor=True,
                  botflag=True, apply_cosmetic_changes=False)


def main(*args):
    options = {}
    cls = TypoReportBot
    for arg in pywikibot.handle_args(args):
        if arg == 'purge':
            cls = PurgeTypoReportBot
        elif arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True

    bot = cls(**options)
    bot.run()


if __name__ == '__main__':
    main()
