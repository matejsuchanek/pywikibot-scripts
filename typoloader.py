import re
import time

import pywikibot

from pywikibot import textlib


class IncompleteTypoRuleException(Exception):

    '''Exception raised when constructing a typo rule from incomplete data'''

    def __init__(self, message):
        self.message = message


class InvalidExpressionException(Exception):

    '''Exception raised when an expression has invalid syntax'''

    def __init__(self, error, aspect='regular expression'):
        self.message = error.msg
        self.aspect = aspect


class TypoRule:

    '''Class representing one typo rule'''

    exceptions = [
        'category', 'comment', 'header', 'hyperlink', 'interwiki', 'invoke',
        'property', 'template',

        # tags
        'blockquote', 'code', 'gallery', 'graph', 'imagemap', 'kbd',
        'mapframe', 'maplink', 'math', 'nowiki', 'poem', 'pre', 'score',
        'section', 'syntaxhighlight', 'timeline', 'tt', 'var',

        # "target-part" of a wikilink
        re.compile(r'\[\[([^][|]+)(\]\]\w*|([^][|]+\|)+)'),

        re.compile('<[a-z]+ [^<>]+>|</[a-z]+>'),  # HTML tag
        re.compile(r'„[^\n"„“]+["“]|(?<!\w)"[^"\n]+"'),  # quotation marks
        # FIXME: re.compile(r"(?<!')''(?!')(?:(?!'')[^\n])+''"),  # italics
        re.compile(r'\b([A-Za-z]+\.)+[a-z]{2,}'),  # url fragment
    ]

    nowikiR = re.compile('</?nowiki>')

    def __init__(self, find, replacements, auto=False, query=None):
        self.find = find
        self.replacements = replacements
        self.auto = auto
        self.query = query
        self.longest = 0

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return (
            f'{self.__class__.name}({self.find!r}, {self.replacements!r}, '
            f'auto={self.auto!r}, query={self.query!r})'
        )

    def needs_decision(self):
        return not self.auto or len(self.replacements) > 1

    @classmethod
    def newFromParameters(cls, parameters):
        if '1' not in parameters:
            raise IncompleteTypoRuleException('Missing find expression')

        find = cls.nowikiR.sub('', parameters['1'])
        try:
            find = re.compile(find, re.M)
        except re.error as exc:
            raise InvalidExpressionException(exc)

        replacements = []
        for key in '23456':
            if key in parameters:
                replacement = re.sub(r'\$([1-9])', r'\\\1', cls.nowikiR.sub(
                    '', parameters[key]))
                replacements.append(replacement)

        if not replacements:
            raise IncompleteTypoRuleException(
                f'No replacements found for rule "{find.pattern}"')

        query = None
        if parameters.get('hledat'):
            part = parameters['hledat'].replace('{{!}}', '|')
            if parameters.get('insource') == 'ne':
                query = part
            else:
                try:
                    re.compile(part)
                    query = f'insource:/{part}/'
                except re.error as exc:
                    raise InvalidExpressionException(exc, 'query')

        auto = parameters.get('auto') == 'ano'

        return cls(find, replacements, auto, query)

    def summary_hook(self, match, replaced):
        def underscores(string):
            if string.startswith(' '):
                string = '_' + string[1:]
            if string.endswith(' '):
                string = string[:-1] + '_'
            return string

        new = old = match.group()
        if self.needs_decision():
            options = [('keep', 'k')]
            replacements = []
            for i, repl in enumerate(self.replacements, start=1):
                replacement = match.expand(repl)
                replacements.append(replacement)
                options.append((f'{i} {underscores(replacement)}', str(i)))
            text = match.string
            pre = text[max(0, match.start() - 30):match.start()].rpartition('\n')[2]
            post = text[match.end():match.end() + 30].partition('\n')[0]
            pywikibot.info(f'{pre}<<lightred>>{old}<<default>>{pos}')
            choice = pywikibot.input_choice('Choose the best replacement',
                                            options, automatic_quit=False,
                                            default='k')
            if choice != 'k':
                new = replacements[int(choice) - 1]
        else:
            new = match.expand(self.replacements[0])
            if old == new:
                pywikibot.warning(f'No replacement done in string "{old}"')

        if old != new:
            old_str = underscores(old.replace('\n', '\\n'))
            new_str = underscores(new.replace('\n', '\\n'))
            fragment = f'{old_str} → {new_str}'
            if fragment.lower() not in map(str.lower, replaced):
                replaced.append(fragment)
        return new

    def apply(self, text, replaced=None):
        if replaced is None:
            replaced = []
        hook = lambda match: self.summary_hook(match, replaced)
        start = time.clock()
        text = textlib.replaceExcept(
            text, self.find, hook, self.exceptions, site=self.site)
        finish = time.clock()
        delta = finish - start
        self.longest = max(delta, self.longest)
        if delta > 5:
            pywikibot.warning(f'Slow typo rule "{self.find.pattern}" ({delta})')
        return text


class TyposLoader:

    top_id = 0

    '''Class loading and holding typo rules'''

    def __init__(self, site, *, allrules=False, typospage=None,
                 whitelistpage=None):
        self.site = site
        self.load_all = allrules
        self.typos_page_name = typospage
        self.whitelist_page_name = whitelistpage

    def getWhitelistPage(self):
        if self.whitelist_page_name is None:
            self.whitelist_page_name = 'Wikipedie:WPCleaner/Typo/False'

        return pywikibot.Page(self.site, self.whitelist_page_name)

    def loadTypos(self):
        pywikibot.info('Loading typo rules...')
        self.typoRules = []

        if self.typos_page_name is None:
            self.typos_page_name = 'Wikipedie:WPCleaner/Typo'
        typos_page = pywikibot.Page(self.site, self.typos_page_name)
        if not typos_page.exists():
            # todo: feedback
            return

        text = textlib.removeDisabledParts(
            typos_page.text, include=['nowiki'], site=self.site)
        load_all = self.load_all is True
        for template, fielddict in textlib.extract_templates_and_params(
                text, remove_disabled_parts=False, strip=False):
            if template.lower() == 'typo':
                try:
                    rule = TypoRule.newFromParameters(fielddict)
                except IncompleteTypoRuleException as exc:
                    pywikibot.warning(exc.message)  # pwb.exception?
                except InvalidExpressionException as exc:
                    if 'fixed-width' not in exc.message:
                        pywikibot.warning('Invalid {} {}: {}'.format(
                            exc.aspect, fielddict['1'], exc.message))
                else:
                    rule.id = self.top_id
                    # fixme: cvar or ivar?
                    self.top_id += 1
                    if load_all or not rule.needs_decision():
                        self.typoRules.append(rule)

        pywikibot.info(f'{len(self.typoRules)} typo rules loaded')
        return self.typoRules

    def loadWhitelist(self):
        self.whitelist = []
        self.fp_page = self.getWhitelistPage()
        if self.fp_page.exists():
            for match in re.finditer(r'\[\[([^]|]+)\]\]', self.fp_page.text):
                self.whitelist.append(match[1].strip())
        return self.whitelist
