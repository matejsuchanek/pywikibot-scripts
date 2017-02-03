# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import time

from pywikibot import pagegenerators
from pywikibot.bot import SkipPageError

from .typoloader import TyposLoader
from .wikitext import WikitextFixingBot

class TypoBot(WikitextFixingBot):

    '''
    Bot for typo fixing

    Supported parameters:
    * -allrules - use if you want to load rules that need user's decision
    * -offset:# - what typo rule do you want to start from
    * -quick - use if you want the bot to focus on the current rule,
      ie. skip the page if the rule couldn't be applied
    * -threshold:# - skip rule when loaded/replaced ratio gets over #
    * -typospage: - what page do you want to load typo rules from
    * -whitelistpage: - what page holds pages which should be skipped
    '''

    def __init__(self, genFactory, offset=0, **kwargs):
        self.availableOptions.update({
            'allrules': False,
            'quick': False,
            'threshold': 10,
            'typospage': None,
            'whitelistpage': None,
        })
        kwargs['typos'] = False
        super(TypoBot, self).__init__(**kwargs)
        loader = TyposLoader(self.site, **kwargs)
        self.typoRules = loader.loadTypos()
        self.fp_page = loader.getWhitelistPage()
        self.whitelist = loader.loadWhitelist()
        self.offset = offset
        generator = genFactory.getCombinedGenerator()
        self.own_generator = not bool(generator)
        if self.own_generator:
            generator = self.makeGenerator
        self.generator = pagegenerators.PreloadingGenerator(generator)

    @property
    def isRuleAccurate(self):
        threshold = float(self.getOption('threshold'))
        result = (self.processed < threshold or
                  self.processed / threshold < self.replaced)
        return result

    @property
    def makeGenerator(self):
        for i, rule in enumerate(self.typoRules[:]):
            if self.offset > i:
                continue
            if not rule.canSearch():
                continue

            # todo: if not allrules:...
            self.offset = i
            pywikibot.output('\nQuery: "%s"' % rule.query)
            old_max = rule.longest
            rule.longest = 0.0
            self.currentrule = rule
            self.processed = 0.0
            self.replaced = 0.0
            for page in rule.querySearch():
                yield page
                if not self.isRuleAccurate:
                    pywikibot.output(
                        'Skipped inefficient query "%s" (%s/%s)' % (
                            rule.query,
                            int(self.replaced), int(self.processed)))
                    break
            else:
                if self.processed < 1:
                    pywikibot.output('No results from query %s' % rule.query)
                else:
                    pywikibot.output('{}% accuracy of query {}'.format(
                        int((self.replaced / self.processed) * 100), rule.query))

            if self.processed > 0:
                pywikibot.output('Longest match: %ss' % rule.longest)
            rule.longest = max(old_max, rule.longest)

    def saveFalsePositive(self):
        title = self.current_page.title()
        self.fp_page.text += '\n* [[%s]]' % title
        self.fp_page.save(summary='[[%s]]' % title, async=True)
        self.whitelist.append(title)

    def init_page(self, page):
        if page.title() in self.whitelist:
            raise SkipPageError(page, 'Page is whitelisted')

        if self.own_generator:
            if self.currentrule.matches(page.title()):
                raise SkipPageError(page, 'Rule matches title')

        super(TypoBot, self).init_page(page)
        if self.own_generator:
            self.processed += 1

    def treat_page(self):
        page = self.current_page
        text = page.text
        done_replacements = []
        quickly = self.getOption('quick') is True
        if self.own_generator:
            text = self.currentrule.apply(page.text, done_replacements)
            if page.text == text:
                if quickly:
                    # todo: output
                    return
            else:
                self.replaced += 1

        start = time.clock()
        for rule in self.typoRules:
            if rule == self.currentrule: # __eq__
                continue
            if rule.matches(page.title()):
                continue
            if quickly and rule.needsDecision():
                continue

            text = rule.apply(text, done_replacements)
            stop = time.clock()
            if quickly and stop - start > 15:
                pywikibot.warning('Other typos exceeded 15s, skipping')
                break

        if len(done_replacements) > 0:
            always = self.getOption('always') is True
            if not always: # fixme: override supermethod
                pywikibot.showDiff(page.text, text)
                options = [('yes', 'y'),
                           ('no', 'n'),
                           ('open in browser', 'b'),
                           ('always', 'a')]
                if self.fp_page.exists():
                    options.insert(2, ('false positive', 'f'))
                choice = pywikibot.input_choice(
                    'Do you want to accept these changes?',
                    options, default='n')

                if choice == 'n':
                    return
                if choice == 'b':
                    pywikibot.bot.open_webbrowser(page)
                    return
                if choice == 'f':
                    self.saveFalsePositive()
                    return
                if choice == 'a':
                    self.options['always'] = always = True

            page.text = text
            self.options['always'] = True # fixme: can bypass other features
            self._save_page(
                page, self.fix_wikitext, page, async=True,
                summary='oprava překlepů: %s' % ', '.join(done_replacements))
            self.options['always'] = always

    def exit(self):
        super(TypoBot, self).exit()
        rules = sorted(filter(lambda rule: not rule.needsDecision(),
                              self.typoRules),
                       key=lambda rule: rule.longest, reverse=True)[:3]
        pywikibot.output('\nSlowest autonomous rules:')
        for i, rule in enumerate(rules, start=1):
            pywikibot.output(
                '%s. "%s" - %s' % (i, rule.find.pattern, rule.longest))
        pywikibot.output('\nCurrent offset: %s\n' % self.offset)

def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    genFactory.handleArg('-ns:0')
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = TypoBot(genFactory, **options)
    bot.run()

if __name__ == "__main__":
    main()
