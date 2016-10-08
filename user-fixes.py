# -*- coding: utf-8  -*-
import pywikibot

from pywikibot.tools.formatter import color_format

from scripts import checkwiki_errors
from scripts.typoloader import (
    TypoRule, TyposLoader
)
from scripts.checkwiki import CheckWiki

from checkwiki_errors import CheckWikiError

class TyposGenerator(object):

    def __init__(self):
        self.len = 1

    def __iter__(self):
        site = pywikibot.Site()
        loader = TyposLoader(site)
        rules = loader.loadTypos()
        self.len = len(rules)
        return map(lambda rule: (rule.find.pattern, rule.replacements[0]), rules)

    def __len__(self):
        return self.len

class CheckWikiFixesGenerator(object):

    exceptions = {
        'inside': [],
        'inside-tags': [],
        'text-contains': [],
        'title': []
    }

    def __init__(self, number=None):
        self.len = 1
        self.number = number

    def __iter__(self):
        self.len = 0
        site = pywikibot.Site()
        cw = CheckWiki(site)
        numbers = [self.number] if self.number is not None else []
        for error in cw.iter_errors(numbers):
            try:
                pair = error.toTuple()
                self.len += 1
                yield pair
            except AttributeError:
                continue

    def __len__(self):
        return self.len

fixes['typos'] = {
    'regex': True,
    'msg': {
        '_default': u'oprava překlepů',
    },
    'exceptions': { # todo: whitelist
        'inside-tags': TypoRule.exceptions[:],
    },
    'replacements': TyposGenerator()
}

fixes['cw'] = {
    'regex': True,
    'msg': {
        '_default': u'opravy dle [[WP:WCW|CheckWiki]]',
    },
    'exceptions': {
        'inside-tags': CheckWikiError.base_exceptions
    },
    'replacements': CheckWikiFixesGenerator(),
}

for num in CheckWiki.errorMap.keys():
    fixes['cw%s' % num] = {
        'regex': True,
        'msg': {
            '_default': u'oprava dle [[WP:WCW|CheckWiki]]', # staticmethods
        },
        'exceptions': {
            'inside-tags': CheckWikiError.base_exceptions + CheckWiki.errorMap[num].exceptions
        },
        'replacements': CheckWikiFixesGenerator(num),
    }

class RedirectsGenerator(object):

    def __init__(self):
        self.len = 1
        self.redirects = []
        self.cache = {}
        self.only_piped = False

    def __iter__(self):
        self.site = pywikibot.Site('cs', 'wikipedia')
        page = pywikibot.Page(self.site, u'Wikipedista:PastoriBot/narovnaná_přesměrování')
        pywikibot.output('Loading redirects')
        text = page.get()
        text = text[text.index('{{SHORTTOC}}') + len('{{SHORTTOC}}'):]
        pattern = r'\[\[([^[\]]+)\]\]'
        for line in text.splitlines():
            if line.strip() == '':
                continue
            if line.startswith('=='):
                continue
            self.redirects.append(line.strip())

        self.len = len(self.redirects)
        pywikibot.output('%s redirects loaded' % self.len)
        yield (pattern, self.replace)

    def replace(self, match):
        split = match.group(1).split('|')
        if len(split) > 2:
            return match.group()
        if len(split) == 1 and self.only_piped:
            return match.group()

        page_title = split[0].replace('_', ' ').strip()
        if page_title in self.redirects:
            if page_title not in self.cache:
                page = pywikibot.Page(self.site, page_title)
                if not page.exists():
                    pywikibot.warning('%s does not exist' % page.title())
                    self.redirects.remove(page_title)
                    return match.group()
                if not page.isRedirectPage():
                    pywikibot.warning('%s is not a redirect' % page.title())
                    self.redirects.remove(page_title)
                    return match.group()

                target = page.getRedirectTarget()
                title = target.title()
                if page_title[0] == page_title[0].lower():
                    self.cache[page_title] = title[0].lower() + title[1:]
                else:
                    self.cache[page_title] = title

            if len(split) == 1:
                options = []
                options_map = [
                    '[[%s]]' % page_title,
                    '[[%s]]' % self.cache[page_title],
                    '[[%s|%s]]' % (self.cache[page_title], page_title)
                ]
                for i, opt in enumerate(options_map, start=1):
                    options.append(
                        ('%s %s' % (i, opt), str(i))
                    )
                options.append(
                    ('Do not replace unpiped links', 'n')
                )

                pre = match.string[max(0, match.start() - 30):match.start()]
                post = match.string[match.end():match.end() + 30]
                pywikibot.output(pre +
                                 color_format(u'{lightred}{0}{default}', match.group()) +
                                 post)
                choice = pywikibot.input_choice('Replace this link?',
                                                options, default='1')
                if choice == 'n':
                    self.only_piped = True
                    return match.group()
                else:
                    return options_map[int(choice)-1]

            return '[[%s|%s]]' % (self.cache[page_title], split[-1])

        return match.group()

    def __len__(self):
        return self.len

fixes['redirects'] = {
    'regex': True,
    'msg': {
        '_default': u'narovnání přesměrování',
    },
    'replacements': RedirectsGenerator(),
}

class TemplatesGenerator(object):

    def __init__(self):
        self.len = 1

    def __len__(self):
        return self.len

    def __iter__(self):
        self.site = pywikibot.Site()
        self.cache = {}
        yield (r'(?P<before>\{\{\s*)(?P<template>[^{|}]+?)(?P<after>\s*[|}])',
               self.replace)

    def replace(self, match):
        template_name = match.group('template').replace('_', ' ').strip()
        template_name = template_name[0].upper() + template_name[1:]
        if template_name not in self.cache:
            template = pywikibot.Page(self.site, template_name, ns=10)
            if template.exists() and template.isRedirectPage():
                target = template.getRedirectTarget()
                self.cache[template_name] = target.title(withNamespace=False)
            else:
                self.cache[template_name] = None

        target = self.cache[template_name]
        if not target:
            return match.group()

        return match.expand('\g<before>%s\g<after>' % target)

fixes['templates'] = {
    'regex': True,
    'msg': {
        '_default': u'narovnání šablony',
    },
    'replacements': TemplatesGenerator()
}
