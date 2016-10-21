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

class IteratingTypoBot(WikitextFixingBot, ExistingPageBot, NoRedirectPageBot):

    '''Bot to iterate and fix typos in a given set of pages'''

    def __init__(self, site, rules, whitelist, fp_page, **kwargs):
        self.availableOptions.update({
            'allrules': False,
            'threshold': 10,
            'quick': False,
        })
        kwargs['typos'] = False
        #kwargs['cw'] = True
        super(IteratingTypoBot, self).__init__(site, **kwargs)
        self.rules = rules
        self.whitelist = whitelist
        self.fp_page = fp_page

    def exit(self):
        super(IteratingTypoBot, self).exit()
        rules = sorted(filter(lambda rule: not rule.needsDecision(), self.rules),
                       key=lambda rule: rule.longest, reverse=True)[:3]
        pywikibot.output("\nSlowest autonomous rules:")
        for i, rule in enumerate(rules, start=1):
            pywikibot.output("%s. %s - %s" % (i, rule.find.pattern, rule.longest))

    def saveFalsePositive(self):
        title = self.current_page.title()
        self.fp_page.text += u'\n* [[%s]]' % title
        self.fp_page.save(summary=u'[[%s]]' % title, async=True)
        self.whitelist.append(title)

    def init_page(self, page):
        if page.title() in self.whitelist:
            raise SkipPageError(page, 'Page is whitelisted')

        self.done_replacements = []
        page.get()

    def treat_page(self):
        page = self.current_page
        text = page.text
        for rule in self.rules:
            if rule.matches(page.title()):
                continue
            if self.getOption('quick') is True or\
               (self.getOption('allrules') is not True
                and rule.needsDecision()):
                continue
            text = rule.apply(text, self.done_replacements)

        if len(self.done_replacements) > 0:
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
            self._save_page(
                page, self.fix_wikitext, page, async=True,
                summary=u'oprava překlepů: %s' % ', '.join(self.done_replacements))
            self.options['always'] = always

class SingleRuleTypoBot(IteratingTypoBot):

    '''Bot to iterate one typo rule over pages where it may apply. Factored by TypoBot'''

    def __init__(self, site, rule, rules, whitelist, fp_page, **kwargs):
        super(SingleRuleTypoBot, self).__init__(site, rules, whitelist, fp_page, **kwargs)
        self.rule = rule
        self.rule.longest = 0
        self.processed = 0.0
        self.replaced = 0.0

    def run(self):
        super(SingleRuleTypoBot, self).run()
        return self._save_counter

    def init_page(self, page):
        if not self.isAccurate():
            raise InaccurateTypoRuleException

        if self.rule.matches(page.title()):
            raise SkipPageError(page, 'Rule matched title')

        super(SingleRuleTypoBot, self).init_page(page)

    def treat_page(self):
        page = self.current_page
        text = page.text
        text = self.rule.apply(text, self.done_replacements)
        self.processed += 1
        if page.text == text:
            if self.getOption('quick') is True:
                return
        else:
            self.replaced += 1
            page.text = text
        super(SingleRuleTypoBot, self).treat_page()

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
        pywikibot.output("Longest match: %ss" % self.rule.longest)

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

    def __init__(self, site, genFactory, **kwargs):
        self.availableOptions.update({ # fixme: expose additional options to bots
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
        self.fp_page = loader.getWhitelistPage()
        self.whitelist = loader.loadWhitelist()
        self.generator = genFactory.getCombinedGenerator()

    def run(self):
        opts = dict(allrules=self.getOption('allrules'),
                    always=self.getOption('always'),
                    quick=self.getOption('quick'),
                    threshold=self.getOption('threshold'))
        if self.generator:
            opts['generator'] = self.generator
            bot = IteratingTypoBot(self.site, self.typoRules[:],
                                   self.whitelist, self.fp_page, **opts)
            bot.run()
            return

        offset = self.getOption('offset')
        for i, rule in enumerate(self.typoRules):
            if offset > i:
                continue
            if not rule.canSearch():
                continue

            pywikibot.output(u'Doing %s' % rule.query)
            opts['generator'] = rule.querySearch()
            bot = SingleRuleTypoBot(self.site, rule, self.typoRules[:],
                                    self.whitelist, self.fp_page, **opts)
            self._save_counter += bot.run()
            time.sleep(3) # fixme: raise exception from the bot

def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    genFactory.handleArg('-ns:0')
    for arg in local_args:
        if not genFactory.handleArg(arg):
            if arg.startswith('-'):
                arg, sep, value = arg.partition(':')
                if value != '':
                    options[arg[1:]] = value if not value.isdigit() else int(value)
                else:
                    options[arg[1:]] = True

    site = pywikibot.Site()
    bot = TypoBot(site, genFactory, **options)
    bot.run()

if __name__ == "__main__":
    main()
