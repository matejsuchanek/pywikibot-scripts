# -*- coding: utf-8  -*-
import pywikibot
import re

from pywikibot import pagegenerators
from pywikibot import textlib

from pywikibot.tools.formatter import color_format

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
                             + color_format(u'{lightred}{0}{default}', old)
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
