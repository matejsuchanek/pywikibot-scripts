# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re

from pywikibot import pagegenerators

from .checkwiki_errors import *
from .wikitext import WikitextFixingBot

class CheckWiki(object):

    '''Singleton class representing the Check Wikipedia project'''

    errorMap = {
        1: PrefixedTemplate,
        2: BrokenHTMLTag,
        7: LowHeadersLevel,
        8: MissingEquation,
        9: SingleLineCategories,
        #10: NoEndSquareBrackets,
        11: HTMLEntity,
        16: InvisibleChars,
        17: DuplicateCategory,
        18: LowerCaseCategory,
        19: SingleEquationHeader,
        20: Dagger,
        21: EnglishCategory,
        22: CategoryWithSpace,
        25: HeaderHierarchy,
        26: Bold,
        #27: Unicode,
        32: MultiplePipes,
        34: MagicWords,
        38: Italics,
        42: StrikedText,
        44: BoldHeader,
        48: SelfLink,
        49: HTMLHeader,
        50: EntitesAsDashes,
        51: InterwikiBeforeHeader,
        52: CategoriesBeforeHeader,
        53: InterwikiBeforeCategory,
        54: ListWithBreak,
        57: HeaderWithColon,
        59: ParameterWithBreak,
        61: RefBeforePunctuation,
        63: SmallInsideTags,
        #75: BadListStructure,
        #76: NoSpace,
        80: BrokenExternalLink,
        81: DuplicateReferences,
        85: EmptyTag,
        86: ExternalLinkLikeInternal,
        88: DefaultsortSpace,
        89: DefaultsortComma,
        93: DoubleHttp,
        101: Ordinals,
        103: SuperfluousPipe,
        104: ReferenceQuotes,
    }

    prio_map = {
        '1': 'high',
        '2': 'medium',
        '3': 'low'
    }

    def __init__(self, site, **kwargs):
        self.site = site
        self.auto = kwargs.pop('auto', True) # todo: user_interactor

    def purge(self):
        self.__cache = {}

    @property
    def site(self):
        return self._site

    @site.setter
    def site(self, value):
        self._site = value
        self.purge()
        self.loadSettings()

    @property
    def settings(self):
        return self._settings

    def loadSettings(self):
        pywikibot.output('Loading CheckWiki settings')
        self._settings = {
            'priority': {
                'high': [],
                'medium': [],
                'low': []
            },
            'whitelists': {},
            #'special': {}
        }
        try:
            set_page = self.site.page_from_repository('Q10784379')
        except (NotImplementedError, UnknownExtension) as e:
            pywikibot.error(e)
            return
        text = set_page.text
        inside_setting = False
        setting = None
        setting_text = ''
        parsed_settings = {}
        for line in text.splitlines():
            if inside_setting is False:
                match = re.match(' *([a-z0-9_]+) *=', line)
                if match is not None:
                    setting = match.group(1)
                    setting_text = ''
                    inside_setting = True
                    line = line[match.end():]

            if inside_setting is True:
                if 'END' in line:
                    setting_text += line[:line.index('END')].strip()
                    inside_setting = False
                    parsed_settings[setting] = setting_text
                else:
                    setting_text += line.strip() + '\n'

        i = 0
        project = parsed_settings.pop('project', self.site.dbName())
        for setting, text in parsed_settings.items():
            split = setting.split('_')
            if len(split) != 4:
                continue
            if split[0] != 'error':
                continue
            if split[-1] != project:
                continue
            if not split[1].isdigit():
                continue
            num = int(split[1])
            if num > 500:
                continue
            if split[2] == 'prio':
                if text in self.prio_map:
                    self._settings['priority'][self.prio_map[text]].append(num)
                    i += 1
            elif split[2] == 'whitelistpage':
                self._settings['whitelists'][num] = text

        self._settings['project'] = project
        pywikibot.output('%s CheckWiki errors recognized' % i)

    def getError(self, number):
        return self.__cache.setdefault(number, self.errorMap[number](self))

    def iter_errors(self, numbers=[], forFixes=False, instances=[],
                    priorities=['*'], **kwargs): # todo: own generator
        for num in self.errorMap.keys():
            if numbers and num not in numbers:
                continue

            #if instances and not ...:
            error = self.getError(num)
            if forFixes and not error.isForFixes():
                continue

            #if priorities and not ...:
            yield error

    def loadErrors(self, limit=0, **kwargs):
        for error in self.iter_errors(**kwargs):
            for page in error.loadError(limit):
                yield page

    def applyErrors(self, text, page, replaced=[], fixed=[], **kwargs):
        errors = list(self.iter_errors(**kwargs))
        while len(errors) > 0:
            error = errors.pop(0)
            if error.needsDecision() or error.handledByCC(): # todo
                continue

            numbers = list(map(lambda e: e.number, errors))
            i = max([numbers.index(num) for num in error.needsFirst
                     if num in numbers] + [0])
            if i > 0:
                errors.insert(i, error)
                continue

            new_text = error.apply(text, page)
            if new_text != text:
                text = new_text
                summary = error.summary
                fixed.append(error.number)
                if summary not in replaced:
                    replaced.append(summary)

        return text

    def markFixed(self, numbers, page):
        for error in self.iter_errors(numbers=numbers):
            error.markFixed(page)

class CheckWikiBot(WikitextFixingBot):

    def __init__(self, numbers, generator, **kwargs):
        kwargs['checkwiki'] = False
        limit = kwargs.pop('limit', 100) # fixme: options
        super(CheckWikiBot, self).__init__(**kwargs)
        self.checkwiki = CheckWiki(self.site, **kwargs)
        if generator: # fixme!
            self.generator = self.checkwiki.loadErrors(limit, numbers=numbers)

    def treat_page(self):
        page = self.current_page
        replaced = []
        fixed = []
        text = self.checkwiki.applyErrors(page.text, page, replaced, fixed)
        summary = 'opravy dle [[WP:WCW|CheckWiki]]: %s' % ', '.join(replaced)
        self.put_current(
            text, summary=summary,
            callback=lambda *args: self.markAsFixedOnSuccess(fixed, *args))

    def markAsFixedOnSuccess(self, numbers, page, exc=None):
        if exc is None:
            self.checkwiki.markFixed(numbers, page)

def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    numbers = []
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue

        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True
        elif arg.isdigit():
            numbers.append(int(arg))

    generator = genFactory.getCombinedGenerator()

    bot = CheckWikiBot(numbers, generator, **options)
    bot.run()

if __name__ == "__main__":
    main()
