# -*- coding: utf-8  -*-
import pywikibot
import re
import time # fixme

from pywikibot import pagegenerators
from pywikibot import textlib
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, SkipPageError
)

from pywikibot.tools.formatter import color_format

from scripts.wikitext import WikitextFixingBot

class InaccurateTypoRuleException(Exception):
    '''Exception to stop the bot on an inefficient query'''
    pass

class IncompleteTypoRuleException(Exception):
    '''Exception raised when constructing a typo rule from incomplete data'''
    def __init__(self, message):
        self.message = message

class InvalidExpressionException(Exception):
    '''Exception raised when an expression has invalid syntax'''
    def __init__(self, error, aspect='regular expression'):
        self.message = error.msg
        self.aspect = aspect

class TypoRule(object):

    '''Class representing one typo rule'''

    exceptions = ['category', 'comment', 'gallery', 'header', 'hyperlink',
                  'interwiki', 'invoke', 'pre', 'property', 'source',
                  'startspace', 'template']
    # tags
    exceptions += ['ce', 'code', 'graph', 'imagemap', 'mapframe', 'maplink',
                   'math', 'nowiki', 'poem', 'score', 'section', 'timeline']
    # regexes ('target-part' of a wikilink; quotation marks; italics)
    exceptions += [re.compile(r'\[\[[^][|]+[]|]'),
                   re.compile(u'„[^“]+“'),
                   re.compile(r"((?<!\w)\"|(?<!')'')(?:(?!\1).)+\1", re.M | re.U)]

    def __init__(self, find, replacements, site, auto=False, query=None):
        self.find = find
        self.replacements = replacements
        self.site = site
        self.auto = auto
        self.query = query

    def needsDecision(self):
        return not self.auto or len(self.replacements) > 1

    def canSearch(self):
        return self.query is not None

    def querySearch(self):
        return pagegenerators.SearchPageGenerator(
            self.query, namespaces=[0], site=self.site)

    @staticmethod
    def newFromParameters(parameters, site):
        if '1' not in parameters:
            raise IncompleteTypoRuleException('Missing find expression')

        find = re.sub(r'</?nowiki>', '', parameters['1'])
        try:
            find = re.compile(find, re.U | re.M)
        except re.error as exc:
            raise InvalidExpressionException(exc)

        replacements = []
        for key in '23456':
            if key in parameters:
                replacement = re.sub(
                    r'\$([1-9])',
                    r'\\\1',
                    re.sub(
                        r'</?nowiki>',
                        '',
                        parameters[key]
                    )
                )
                replacements.append(replacement)

        if len(replacements) == 0:
            raise IncompleteTypoRuleException('No replacements found')

        query = None
        if 'hledat' in parameters:
            if parameters['hledat'] != '':
                part = parameters['hledat'].replace('{{!}}', '|')
                if 'insource' in parameters and parameters['insource'] == 'ne':
                    query = part
                else:
                    try:
                        re.compile(part)
                        query = u'insource:/%s/' % part
                    except re.error as exc:
                        raise InvalidExpressionException(exc, 'query')

        auto = 'auto' in parameters and parameters['auto'] == 'ano'

        return TypoRule(find, replacements, site, auto, query)

    def matches(self, text):
        return re.search(self.find, text) is not None

    def summary_hook(self, match, replaced):
        new = old = match.group(0)
        if self.needsDecision():
            options = [('keep', 'k')]
            replacements = []
            for i, repl in enumerate(self.replacements):
                replacement = match.expand(repl)
                replacements.append(replacement)
                options.append(
                    (u"%s %s" % (i + 1, replacement), str(i + 1))
                )
            text = match.string
            pywikibot.output(text[max(0, match.start() - 30):match.start()]
                             + color_format(u'{lightred}%s{default}' % old)
                             + text[match.end():match.end() + 30])
            choice = pywikibot.input_choice('Choose the best replacement',
                                            options, automatic_quit=False,
                                            default='k')
            if choice != 'k':
                new = replacements[int(choice) - 1]
        else:
            new = match.expand(self.replacements[0])
            if old == new:
                pywikibot.warning(u'No replacement done in string "%s"' % old)

        if old == new:
            fragment = u' → '.join([re.sub('(^ | $)', '_', re.sub('\n', r'\\n', i)) for i in [old, new]])
            if fragment.lower() not in [i.lower() for i in replaced]:
                replaced.append(fragment)
        return new

    def apply(self, text, replaced=[]):
        hook = lambda match: self.summary_hook(match, replaced)
        return textlib.replaceExcept(text, self.find, hook, self.exceptions,
                                     self.site)

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

class TyposLoader(object):

    '''Class loading and holding typo rules'''

    def __init__(self, site, **kwargs):
        self.site = site
        self.typos_page_name = kwargs.pop('typospage', None)
        self.whitelist_page_name = kwargs.pop('whitelistpage', None)
        self.load_all = kwargs.pop('allrules', False)

    def loadTypos(self):
        self.typoRules = []
        if self.typos_page_name is None:
            self.typos_page_name = u'Wikipedie:WPCleaner/Typo'

        pywikibot.output('Loading typo rules')
        typos_page = pywikibot.Page(self.site, self.typos_page_name)
        if not typos_page.exists():
            return
        content = typos_page.get()

        load_all = self.load_all is True
        for template, fielddict in textlib.extract_templates_and_params(content, False, False):
            if template.lower() == 'typo':
                try:
                    rule = TypoRule.newFromParameters(fielddict, self.site)
                except IncompleteTypoRuleException as exc:
                    pywikibot.warning(exc.message)
                except InvalidExpressionException as exc:
                    if 'fixed-width' not in exc.message:
                        pywikibot.warning(u'Invalid %s %s: %s' % (exc.aspect, find, exc.message))
                except:
                    raise
                else:
                    if load_all or not rule.needsDecision():
                        self.typoRules.append(rule)

        pywikibot.output('%s typo rules loaded' % len(self.typoRules))
        return self.typoRules

    def loadWhitelist(self):
        if self.whitelist_page_name is None:
            self.whitelist_page_name = u'Wikipedie:WPCleaner/Typo/False'

        self.whitelist = []
        self.fp_page = pywikibot.Page(self.site, self.whitelist_page_name)
        if self.fp_page.exists():
            content = self.fp_page.get()
            for match in re.finditer(r'\[\[([^]|]+)\]\]', content):
                self.whitelist.append(match.group(1).strip())
        return self.whitelist

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
