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
            'false_positives': None,
        })
        super().__init__(**kwargs)
        self.loader = TyposLoader(
            self.site, allrules=True, typospage=self.opt.typospage,
            whitelistpage=self.opt.whitelistpage)
        self.false_positives = set()

    def setup(self):
        super().setup()
        self.typoRules = self.loader.loadTypos()
        #self.fp_page = self.loader.getWhitelistPage()
        self.whitelist = self.loader.loadWhitelist()
        self.data = defaultdict(list)
        self.order = []  # remove when dictionaries are ordered
        self.load_false_positives()

    def load_false_positives(self):
        if not self.opt.false_positives:
            return
        page = pywikibot.Page(self.site, self.opt.false_positives)
        fps = self.false_positives
        for line in page.text.splitlines():
            if line.startswith(('#', '*')):
                fps.add(line.lstrip('#* '))

    @property
    def generator(self):
        for rule in self.typoRules:
            if rule.query is None:
                continue

            pywikibot.output('Query: "%s"' % rule.query)
            self.current_rule = rule
            yield from PreloadingGenerator(
                self.site.search(rule.query, namespaces=[0]))

    def skip_page(self, page):
        # TODO: better terminology
        if page.title() in self.whitelist:
            pywikibot.warning('Skipped {} because it is whitelisted'
                              .format(page))
            return True

        if self.current_rule.find.search(page.title()):
            pywikibot.warning('Skipped {} because the rule matches the title'
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
        found = set()
        for match in self.current_rule.find.finditer(text):
            match_text = match.group(0)
            if match_text in found:
                continue
            found.add(match_text)
            title = page.title(as_link=True)
            put_text = self.pattern.format(title, match_text)
            if put_text.lstrip('# ') not in self.false_positives:
                pywikibot.stdout(put_text)
                self.order.append(title)
                self.data[title].append(match_text)

    def teardown(self):
        outputpage = self.opt.outputpage
        if (self._generator_completed or self.opt.anything) and outputpage:
            put = []
            for title in self.order:
                for match in self.data[title]:
                    put.append(self.pattern.format(title, match))
            page = pywikibot.Page(self.site, outputpage)
            page.text = '\n'.join(put)
            page.save(summary='aktualizace seznamu překlepů', minor=False,
                      botflag=False, apply_cosmetic_changes=False)
        super().teardown()


class PurgeTypoReportBot(SingleSiteBot, ExistingPageBot):

    def __init__(self, **kwargs):
        self.helper = TypoReportBot(**kwargs)
        super().__init__(site=self.helper.site)
        self.put = []
        self.cache = defaultdict(list)

    def setup(self):
        super().setup()
        self.whitelist = self.helper.loader.loadWhitelist()
        self.generator = [pywikibot.Page(self.site, self.helper.opt.outputpage)]
        self.helper.load_false_positives()

    def line_iterator(self, text):
        regex = re.compile(self.helper.pattern.format(
            r'\[\[([^]]+)\]\]', '(.+)'))
        for line in text.splitlines():
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
        for entry in PreloadingGenerator(self.line_iterator(page.text)):
            key = title = entry.title()
            if not entry.exists():
                self.cache.pop(key)
                continue
            while entry.isRedirectPage():
                entry = entry.getRedirectTarget()
                title = entry.title()
            text = self.helper.remove_disabled_parts(entry.text)
            for string in self.cache.pop(key):
                if string not in text:
                    continue
                put_text = pattern.format('[[%s]]' % title, string)
                if put_text.lstrip('# ') in self.helper.false_positives:
                    continue
                self.put.append(put_text)

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
