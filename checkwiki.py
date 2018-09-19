# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re

from pywikibot import pagegenerators
from pywikibot.exceptions import UnknownExtension

from operator import attrgetter

from .checkwiki_errors import *
from .wikitext import WikitextFixingBot


class CheckWikiSettings(object):

    prio_map = {
        '0': '',
        '1': 'high',
        '2': 'medium',
        '3': 'low'
    }

    def __init__(self, data):
        self.data = data

    def get_priority(self, error):
        return self.data[error]['priority']

    def get_errors_by_priority(self, priority):
        for error, data in self.data.items():
            if data['priority'] == priority:
                yield error

    @classmethod
    def new_from_text(cls, text, dbName):
        data = {}
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

        project = parsed_settings.pop('project', dbName)
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
            data.setdefault(num, {})
            if split[2] == 'prio':
                text = text.strip()
                if text in cls.prio_map.keys():
                    data[num]['priority'] = cls.prio_map[text]
            elif split[2] == 'whitelistpage':
                data[num].setdefault('whitelists', []).append(text)
        return cls(data)

    @classmethod
    def new_from_site(cls, site):
        try:
            page = site.page_from_repository('Q10784379')
        except (NotImplementedError, UnknownExtension) as e:
            pywikibot.error(e)
            return None
        return cls.new_from_text(page.text, site.dbName())


class CheckWikiErrorGenerator(object):

    def __init__(self, checkwiki, priorities=None, ids=None):
        self.checkwiki = checkwiki
        self.priorities = priorities or []
        self.ids = ids or []

    def __iter__(self):
        for error in self.ids:
            for page in self.checkwiki.iter_pages(error):
                yield page
        already = set(self.ids)
        for prio in self.priorities:
            for error in self.checkwiki.settings.get_errors_by_priority(prio):
                if error not in already:
                    for page in self.checkwiki.iter_pages(error):
                        yield page


class CheckWiki(object):

    url = 'https://tools.wmflabs.org/checkwiki/cgi-bin/checkwiki_bots.cgi'

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

    def __init__(self, site):
        self.site = site

    def purge(self):
        self.__cache = {}

    @property
    def site(self):
        return self._site

    @site.setter
    def site(self, value):
        self._site = value
        self.purge()
        self.load_settings()

    def load_settings(self):
        pywikibot.output('Loading CheckWiki settings...')
        self._settings = CheckWikiSettings.new_from_site(self.site)

    @property
    def settings(self):
        if not hasattr(self, '_settings'):
            self.load_settings()
        return self._settings

    def get_error(self, number):
        return self.__cache.setdefault(number, self.errorMap[number](self))

    def iter_errors(self, numbers=None, only_for_fixes=False, priorities=None):
        for num in self.errorMap:
            if numbers and num not in numbers:
                continue
            if priorities and self.settings.get_priority(num) not in priorities:
                continue

            error = self.get_error(num)
            if only_for_fixes and not error.isForFixes():
                continue

            yield error

    def apply(self, text, page, replaced=[], fixed=[], errors=[], **kwargs):
        errors = list(self.iter_errors(set(errors)))
        while len(errors) > 0:
            error = errors.pop(0)
            if error.needsDecision() or error.handledByCC(): # todo
                continue

            numbers = list(map(attrgetter('number'), errors))
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

    def iter_titles(self, num, **kwargs):
        data = {
            'action': 'list',
            'id': num,
            'project': self.site.dbName(),
        }
        for line in self.get(data, **kwargs).iter_lines():
            yield line.decode().replace('title=', '')  # fixme: b/c

    def iter_pages(self, num, **kwargs):
        for title in self.iter_titles(num, **kwargs):
            yield pywikibot.Page(self.site, title)

    def get(self, data, **kwargs):
        return requests.get(self.url, data, **kwargs)

    def post(self, data, **kwargs):
        return requests.post(self.url, data, **kwargs)

    def mark_as_fixed(self, page, error):
        data = {
            'action': 'mark',
            'id': error,
            'project': page.site.dbName(),
            'title': page.title(),
        }
        return self.post(data)

    def mark_as_fixed_multiple(self, page, errors):
        for error in errors:
            self.mark_as_fixed(page, error)

    @staticmethod
    def parse_option(option):
        ids = []
        priorities = []
        for part in option.split(','):
            if part.isdigit():
                ids.append(int(part))
            elif part in CheckWikiSettings.prio_map.values():
                priorities.append(part)
        return ids, priorities


class CheckWikiBot(WikitextFixingBot):

    def __init__(self, checkwiki, numbers, **kwargs):
        kwargs['checkwiki'] = False
        super(CheckWikiBot, self).__init__(**kwargs)
        self.checkwiki = checkwiki
        self.numbers = numbers

    def treat_page(self):
        page = self.current_page
        replaced = []
        fixed = []
        text = self.checkwiki.apply(
            page.text, page, replaced, fixed, self.numbers)
        summary = 'opravy dle [[WP:WCW|CheckWiki]]: %s' % ', '.join(replaced)
        self.put_current(
            text, summary=summary,
            callback=lambda *args: self.mark_as_fixed_on_success(fixed, *args))

    def mark_as_fixed_on_success(self, numbers, page, exc=None):
        if exc is not None:
            return
        self.checkwiki.mark_as_fixed_multiple(page, numbers)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    checkwiki = CheckWiki(site)
    genFactory = pagegenerators.GeneratorFactory(site=site)
    numbers = []
    gens = []
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-checkwiki:'):
            ids, priorities = checkwiki.parse_option(arg.partition(':')[2])
            gen = CheckWikiErrorGenerator(
                checkwiki, ids=ids, priorities=priorities)
            gens.append(gen)
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True
        else:
            numbers.extend(checkwiki.parse_option(arg)[0])

    if gens:
        genFactory.gens.extend(gens)
    generator = genFactory.getCombinedGenerator(preload=True)
    if not generator:
        genFactory.gens.append(CheckWikiErrorGenerator(checkwiki, ids=numbers))
        generator = genFactory.getCombinedGenerator(preload=True)

    bot = CheckWikiBot(checkwiki, numbers, generator=generator,
                       site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
