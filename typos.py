# -*- coding: utf-8  -*-
import pywikibot
import time # fixme

from pywikibot import pagegenerators
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, SkipPageError
)

from scripts.typoloader import TyposLoader
from scripts.wikitext import WikitextFixingBot

class InaccurateTypoRuleException(Exception):
    '''Exception to stop the bot on an inefficient query'''
    pass

class SingleRuleTypoBot(SingleSiteBot, WikitextFixingBot, ExistingPageBot, NoRedirectPageBot):

    '''Bot to handle one typo rule. Factored by TypoBot'''

    def __init__(self, site, rule, rules, whitelist, fp_page, **kwargs):
        self.availableOptions.update({
            'allrules': False,
            'threshold': 10,
            'quick': False,
        })
        kwargs['typos'] = False
        super(SingleRuleTypoBot, self).__init__(site, **kwargs)
        self.rule = rule
        self.rules = rules
        self.whitelist = whitelist
        self.fp_page = fp_page
        self.processed = 0.0
        self.replaced = 0.0

    def run(self):
        super(SingleRuleTypoBot, self).run()
        return self._save_counter

    def init_page(self, page):
        if not self.isAccurate():
            raise InaccurateTypoRuleException

        if page.title() in self.whitelist:
            raise SkipPageError(page, 'Page is whitelisted')

        if self.rule.matches(page.title()):
            raise SkipPageError(page, 'Rule matched title')

        page.get()

    def treat_page(self):
        page = self.current_page
        text = page.text
        replaced = []
        text = self.rule.apply(text, replaced)
        self.processed += 1
        if page.text == text:
            if self.getOption('quick') is True:
                return
        else:
            self.replaced += 1

        for rule in self.rules:
            if rule.matches(page.title()):
                continue
            if self.getOption('quick') is True or\
               (self.getOption('allrules') is not True
                and rule.needsDecision()):
                continue
            text = rule.apply(text, replaced)

        if len(replaced) > 0:
            always = (self.getOption('always') is True or
                      self.getOption('quick') is True)
            if not always:
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
            self.options['always'] = True
            self._save_article(page, self._save_page, page.save, async=True,
                               summary=u'oprava překlepů: %s' % ', '.join(replaced))
            self.options['always'] = always

    def saveFalsePositive(self):
        title = self.current_page.title()
        fb_page.text += u'\n* [[%s]]' % title
        fb_page.save(summary=u'[[%s]]' % title, async=True)
        self.whitelist.append(title)

    def isAccurate(self):
        threshold = self.getOption('threshold')
        return self.processed < threshold or\
               self.processed / threshold > self.replaced

    def exit(self):
        if self.processed < 1:
            pywikibot.output(u'No results from query %s' % self.rule.query)
        elif not self.isAccurate():
            pywikibot.output(u'Skipping inefficient query %s (%s/%s)' % (
                self.rule.query, int(self.replaced), int(self.processed)))
        else:
            pywikibot.output(u'{}% accuracy of query {}'.format(
                int((self.replaced / self.processed) * 100), self.rule.query))

class TypoBot(SingleSiteBot):

    '''
    Bot factoring bots for typo fixing

    Supported parameters:
    * -allrules - use if you want to load rules that need user's decision
    * -offset:# - what typo rule do you want to start from
    * -quick - use if you want the bot to focus on the current rule,
      ie. skip the page if the rule couldn't be applied
    * -threshold:# - skip rule when loaded/replaced ratio gets over #
    * -typospage: - what page do you want to load typo rules from
    * -whitelistpage: - what page holds pages which should be skipped
    '''

    def __init__(self, site, **kwargs):
        self.availableOptions.update({
            'allrules': False,
            'offset': 0,
            'quick': False,
            'threshold': 10,
            'typospage': None,
            'whitelistpage': None,
        })
        super(TypoBot, self).__init__(site, **kwargs)
        loader = TyposLoader(site, **kwargs)
        self.typoRules = loader.loadTypos()
        self.whitelist = loader.loadWhitelist()

    def run(self):
        i = 0
        offset = self.getOption('offset')
        for rule in self.typoRules:
            if offset > i:
                continue
            if not rule.canSearch():
                continue

            i += 1
            pywikibot.output(u'Doing %s' % rule.query)
            opts = dict(allrules=self.getOption('allrules'),
                        always=self.getOption('always'),
                        generator=rule.querySearch(),
                        quick=self.getOption('quick'),
                        threshold=self.getOption('threshold'))

            bot = SingleRuleTypoBot(self.site, rule, self.typoRules[:],
                                    self.whitelist, self.fp_page, **opts)
            self._save_counter += bot.run()
            time.sleep(3) # fixme: raise exception from the bot

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    site = pywikibot.Site()
    bot = TypoBot(site, **options)
    bot.run()

if __name__ == "__main__":
    main()
