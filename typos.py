#!/usr/bin/python
import time

import pywikibot
from pywikibot import pagegenerators

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

    def __init__(self, generator, *, offset=0, **kwargs):
        self.available_options.update({
            'allrules': False,
            'quick': False,
            'threshold': 10,
            'typospage': None,
            'whitelistpage': None,
        })
        kwargs['typos'] = False
        self.own_generator = not bool(generator)
        if self.own_generator:
            self.generator = self.make_generator()
        else:
            self.generator = generator

        super().__init__(**kwargs)
        self.offset = offset

    def setup(self):
        loader = TyposLoader(
            self.site, allrules=self.opt['allrules'],
            typospage=self.opt['typospage'],
            whitelistpage=self.opt['whitelistpage'])
        self.typoRules = loader.loadTypos()
        self.fp_page = loader.getWhitelistPage()
        self.whitelist = loader.loadWhitelist()

    @property
    def is_rule_accurate(self):
        threshold = self.opt['threshold']
        result = (self.processed < threshold or
                  self.processed / threshold < self.replaced)
        return result

    def make_generator(self):
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
            self.current_rule = rule
            self.skip_rule = False
            self.processed = 0.0
            self.replaced = 0.0
            for page in rule.querySearch():
                if self.skip_rule:
                    break
                yield page
                if not self.is_rule_accurate:
                    pywikibot.output(
                        'Skipped inefficient query "%s" (%d/%d)' % (
                            rule.query,
                            int(self.replaced), int(self.processed)))
                    break
            else:
                if self.processed < 1:
                    pywikibot.output('No results from query %s' % rule.query)
                else:
                    pywikibot.output('%.f accuracy of query %s' % (
                        (self.replaced / self.processed) * 100, rule.query))

            if self.processed > 0:
                pywikibot.output('Longest match: %fs' % rule.longest)
            rule.longest = max(old_max, rule.longest)

    def save_false_positive(self, page):
        link = page.title(as_link=True)
        self.fp_page.text += '\n* %s' % link
        self.fp_page.save(summary=link, asynchronous=True)
        self.whitelist.append(page.title())

    def skip_page(self, page):
        if page.title() in self.whitelist:
            pywikibot.warning('Skipped {} because it is whitelisted'
                              .format(page))
            return True

        if self.own_generator and self.current_rule.find.search(page.title()):
            pywikibot.warning('Skipped {} because the rule matches its title'
                              .format(page))
            return True

        return super().skip_page(page)

    def init_page(self, page):
        out = super().init_page(page)
        if self.own_generator:
            self.processed += 1
        return out

    def treat_page(self):
        page = self.current_page
        text = page.text
        done_replacements = []
        quickly = self.opt['quick'] is True
        start = time.time()
        if self.own_generator:
            text = self.current_rule.apply(page.text, done_replacements)
            if page.text == text:
                if quickly:
                    pywikibot.output('Typo not found, not fixing another '
                                     'typos in quick mode')
                    return
            else:
                self.replaced += 1

        for rule in self.typoRules:
            if self.own_generator and rule == self.current_rule:  # __eq__
                continue
            if rule.find.search(page.title()):
                continue
            if quickly and rule.needs_decision():
                continue

            text = rule.apply(text, done_replacements)
            stop = time.time()
            if quickly and stop - start > 15:
                pywikibot.warning('Other typos exceeded 15s, skipping')
                break

        self.put_current(
            text, summary='oprava překlepů: %s' % ', '.join(done_replacements))

    def user_confirm(self, question):
        if self.opt['always']:
            return True

        options = [('yes', 'y'), ('no', 'n'), ('all', 'a')]
        if self.fp_page.exists():
            options.append(('false positive', 'f'))
        if self.own_generator:
            options.append(('skip rule', 's'))
        options += [('open in browser', 'b'), ('quit', 'q')]

        choice = pywikibot.input_choice(question, options, default='N',
                                        automatic_quit=False)

        if choice == 'n':
            return False

        if choice == 's':
            self.skip_rule = True
            return False

        if choice == 'b':
            pywikibot.bot.open_webbrowser(self.current_page)
            return False

        if choice == 'f':
            self.save_false_positive(self.current_page)
            return False

        if choice == 'q':
            self.quit()

        if choice == 'a':
            self.options['always'] = True

        return True

    def teardown(self):
        rules = sorted(
            (rule for rule in self.typoRules if not rule.needs_decision()),
            key=lambda rule: rule.longest, reverse=True)[:3]
        pywikibot.output('\nSlowest autonomous rules:')
        for i, rule in enumerate(rules, start=1):
            pywikibot.output(
                '%d. "%s" - %f' % (i, rule.find.pattern, rule.longest))
        if self.own_generator:
            pywikibot.output('\nCurrent offset: %d\n' % self.offset)
        super().teardown()


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    genFactory.handle_arg('-ns:0')
    for arg in local_args:
        if genFactory.handle_arg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator(preload=True)
    bot = TypoBot(generator, **options)
    bot.run()


if __name__ == '__main__':
    main()
