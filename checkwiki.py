# -*- coding: utf-8  -*-
import pywikibot
import re

from pywikibot import pagegenerators

from pywikibot.bot import ExistingPageBot

from scripts.checkwiki_errors import *
from scripts.wikitext import WikitextFixingBot

def deduplicate(array):
    for index, member in enumerate(array, start=1):
        while member in array[index:]:
            array.pop(index + array[index:].index(member))

class CheckWiki(object):

    '''Object to load errors from CheckWiki'''

    errorMap = {
        1: PrefixedTemplate,
        2: BrokenHTMLTag,
        7: LowHeadersLevel,
        #8: MissingEquation, todo
        17: DuplicateCategory,
        21: EnglishCategory,
        25: HeaderHierarchy,
        32: MultiplePipes,
        #34: MagicWords, todo
        44: BoldHeader,
        48: SelfLink,
        54: ListWithBreak,
        57: HeaderWithColon,
        63: SmallInsideTags,
        #75: BadListStructure, todo
        81: DuplicateReferences,
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
        self.cache = {}
        self.loadSettings()
        self.auto = kwargs.pop('auto', True)

    def purge(self):
        self.cache = {}

    def loadSettings(self):
        pywikibot.output('Loading CheckWiki settings')
        self.settings = {
            'priority': {
                'high': [],
                'medium': [],
                'low': []
            },
            'whitelists': {},
            #'special': {}
        }
        repo = self.site.data_repository()
        item = pywikibot.ItemPage(repo, 'Q10784379')
        try:
            sitelink = item.getSitelink(self.site)
        except pywikibot.NoPage:
            return
        set_page = pywikibot.Page(self.site, sitelink)
        text = set_page.get()
        inside_setting = False
        setting = None
        setting_text = ''
        parsed_settings = {}
        for line in text.splitlines():
            if inside_setting is False:
                match = re.match(r' *([a-z0-9_]+) *=', line)
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
                    self.settings['priority'][self.prio_map[text]].append(num)
                    i += 1
            elif split[2] == 'whitelistpage':
                self.settings['whitelists'][num] = text

        self.settings['project'] = project
        pywikibot.output(u'%s CheckWiki errors recognized' % i)

    def getError(self, number):
        if number not in self.cache:
            error = self.errorMap[number](self.site, self.settings,
                                          auto=self.auto)
            self.cache[number] = error
        return self.cache[number]

    def iter_errors(self, numbers=[]):
        for num in self.errorMap.keys():
            if not numbers or num in numbers:
                yield self.getError(num)

    def loadErrors(self, numbers=[], limit=None):
        for error in self.iter_errors(numbers):
            yield from error.loadError(limit=limit)

    def applyErrors(self, text, page, replaced=[], fixed=[], numbers=[]):
        errors = set(self.errorMap.keys())
        if len(numbers) > 0:
            errors &= set(numbers)
        errors = list(errors)
        while len(errors) > 0:
            num = errors.pop(0)
            error = self.getError(num)
            needsFirst = set(error.needsFirst())
            i = 0
            while len(needsFirst & set(errors[i:])) > 0:
                i += 1
            if i > 0:
                errors.insert(i, num)
                continue
            new_text = error.apply(text, page)
            if new_text != text:
                text = new_text
                summary = error.summary()
                fixed.append(num)
                if summary not in replaced:
                    replaced.append(summary)

        return text

    def markFixed(self, numbers, page):
        for error in self.iter_errors(numbers):
            error.markFixed(page)

class CheckWikiBot(WikitextFixingBot, ExistingPageBot):

    def __init__(self, site, numbers, **kwargs):
        kwargs['cw'] = False
        limit = kwargs.pop('limit', 100)
        super(CheckWikiBot, self).__init__(site, **kwargs)
        self.checkwiki = CheckWiki(site, **kwargs)
        if self.generator is None:
            self.generator = self.checkwiki.loadErrors(numbers, limit)

    def init_page(self, page):
        page.get()

    def treat_page(self):
        page = self.current_page
        replaced = []
        fixed = []
        text = self.checkwiki.applyErrors(page.text, page, replaced, fixed)
        if page.text == text:
            return
        summary = u'opravy dle [[WP:WCW|CheckWiki]]: %s' % ', '.join(replaced)
        if self.getOption('always') is not True:
            pywikibot.showDiff(page.text, text)
        page.text = text
        self._save_page(page, self.fix_wikitext, page, summary=summary,
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
        if not genFactory.handleArg(arg):
            if arg.startswith('-'):
                arg, sep, value = arg.partition(':')
                if value != '':
                    options[arg[1:]] = value if not value.isdigit() else int(value)
                else:
                    options[arg[1:]] = True
            elif arg.isdigit():
                numbers.append(int(arg))

    site = pywikibot.Site()
    bot = CheckWikiBot(site, numbers=numbers,
                       generator=genFactory.getCombinedGenerator(), **options)
    bot.run()

if __name__ == "__main__":
    main()
