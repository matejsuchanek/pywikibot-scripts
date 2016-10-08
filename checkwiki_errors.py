# -*- coding: utf-8  -*-
import pywikibot
import re
import requests

from pywikibot import textlib

def deduplicate(array):
    for index, member in enumerate(array, start=1):
        while member in array[index:]:
            array.pop(index + array[index:].index(member))

class CheckWikiError(object):

    '''Abstract class for each error to extend'''

    base_exceptions = ['comment', 'math', 'nowiki', 'pre', 'source', 'startspace']
    exceptions = [] # for subclasses

    def __init__(self, site, settings, **kwargs):
        self.site = site
        self.settings = settings
        self.auto = kwargs.pop('auto', True)

    def loadError(self, limit=100):
        pywikibot.output('Loading pages with error #%s' % self.number)
        url = 'https://tools.wmflabs.org/checkwiki/cgi-bin/checkwiki_bots.cgi?action=list&project=%s&id=%s&limit=%s' % (
            self.settings['project'], self.number, limit)
        for line in requests.get(url).iter_lines():
            page = pywikibot.Page(self.site, line.decode().replace('title=', '')) # fixme: b/c
            if not page.exists():
                self.markFixed(page)
                continue
            yield page

    def markFixed(self, page):
        url = 'https://tools.wmflabs.org/checkwiki/cgi-bin/checkwiki_bots.cgi'
        data = {
            'action': 'mark',
            'id': self.number,
            'project': self.settings['project'],
            'title': page.title()
        }
        requests.post(url, data)

    def apply(self, text, page):
        return textlib.replaceExcept(text, self.pattern(), self.replacement,
                                     exceptions=self.base_exceptions,
                                     site=page.site)

    def isForFixes(self):
        return hasattr(self, 'pattern') and hasattr(self, 'replacement')

    def toTuple(self):
        return (self.pattern().pattern, self.replacement)

    def summary(self):
        pass # todo: abstract, fixme: static

    def needsFirst(self):
        return []

    @property
    def priority(self):
        if not hasattr(self, 'priority'):
            for p, errors in self.settings['priority'].items():
                if self.number in errors:
                    self.priority = p # number?
        return self.priority

    def needsDecision(self):
        return False

    def handledByCC(self):
        return False

class HeaderError(CheckWikiError):

    def pattern(self):
        return re.compile('(?m)^(?P<start>==+)(?P<content>((?!==|= *$).)+?)(?P<end>==+) *$')

class PrefixedTemplate(CheckWikiError):

    number = 1

    def pattern(self):
        namespaces = self.site.namespaces[10]
        return re.compile(r'\{\{ *(%s) *: *' % (
            '|'.join(['[%s%s]%s' % (ns[0].upper(), ns[0].lower(), ns[1:]) for ns in namespaces])
            ))

    def replacement(self, match):
        return '{{'

    def summary(self):
        return u'odstranění prefixu šablony'

class BrokenHTMLTag(CheckWikiError):

    number = 2
    tags = ('center', 'big', 'del', 'div', 'em', 'i', 'p', 's', 'small',
            'span', 'strike', 'sub', 'sup', 'table', 'td', 'th', 'tr')

    def pattern(self):
        return re.compile(r'< */ *([bh]r) */? *>')

    def replacement(self, match):
        return match.expand(r'<\1 />')

    def apply(self, text, page):
        param_regex = re.compile(
            '(?P<param>[a-z]+) *= *'
            '(?P<quote>[\'"])?'
            r'(?P<content>(?(quote)(?!(?P=quote)|>).|\w)+)'
            '(?(quote)(?P=quote)|)',
            re.U)

        def replaceTag(match):
            tag = match.group('tag')
            if match.group('params') is not None:
                params = []
                for p in param_regex.finditer(match.group('params')):
                    params.append(
                        (p.group('param'), p.group('content'))
                    )
                if len(params) == 1:
                    if params[0][0] == 'id':
                        return u'{{Kotva|%s}}' % params[0][1]
                    if params[0][0] in ('clear', 'style'):
                        for s in ('right', 'left'):
                            if s in params[0][1]:
                                return '{{Clear|%s}}' % s # fixme: from settings
                        return '{{Clear}}'

            else:
                tags_before = list(
                    re.finditer(r'<%s(?: (?P<params>[^>]+))?(?<!/)>' % tag,
                                match.string[:match.start()])
                    )
                if len(tags_before) > 0:
                    last = tags_before[-1]
                    if '</%s>' % tag not in match.string[last.end():match.start()]:
                        return '</%s>' % tag
                    else:
                        pass # previous and so on
                elif len(tags_before) == 0:
                    return ''

            return match.group()

        text = re.sub(
            '<(?P<tag>%s)(?: (?P<params>[^>]+?))? */>' % '|'.join(self.tags),
            replaceTag, text)

        return super(BrokenHTMLTag, self).apply(text, page)

    def summary(self):
        return u'oprava chybné syntaxe HTML tagu'

class LowHeadersLevel(HeaderError):

    number = 7

    def apply(self, text, page):
        regex = self.pattern()
        min_level = 8
        for match in regex.finditer(text):
            start = match.group('start')
            end = match.group('end')
            if len(start) == len(end):
                min_level = min(min_level, len(start))
            else:
                return text

        if min_level > 2:
            text = regex.sub(
                lambda match: u'{eq} {content} {eq}'.format(
                    eq=match.group('start')[min_level-2:],
                    content=match.group('content').strip()),
                text)

        return text

    def needsFirst(self):
        return [8]

    def summary(self):
        return u'oprava úrovně nadpisů'

class MissingEquation(CheckWikiError): # TODO

    number = 8

    def needsDecision(self):
        return True

    def pattern(self):
        return re.compile('(?m)^(?P<start>=+)'
                          '(?P<content>((?!==|= *$).)+?)(?!(?P=start) *$)'
                          '(?P<end>=+) *$')

    def replacement(self, match):
        start = match.group('start')
        end = match.group('end')
        # todo
        return match.group()

    def summary(self):
        return u'oprava úrovně nadpisů'

class SingleLineCategories(CheckWikiError):

    number = 9

    def handledByCC(self):
        return True

class InvisibleChars(CheckWikiError):

    number = 16

    def handledByCC(self):
        return True

class DuplicateCategory(CheckWikiError):

    number = 17

    def apply(self, text, page):
        categories = textlib.getCategoryLinks(text)
        if len(categories) > len(set(categories)):
            deduplicate(categories)
            text = textlib.replaceCategoryLinks(text, categories, page.site)
        return text

    def summary(self):
        return u'odstranění duplicitní kategorie'

    def needsFirst(self):
        return [21]

class LowerCaseCategory(CheckWikiError):

    number = 18

    def handledByCC(self):
        return True

class EnglishCategory(CheckWikiError):

    number = 21

    def pattern(self):
        return re.compile(r'\[\[ *[Cc]ategory *: *')

    def replacement(self, match):
        ns = list(self.site.namespaces[14])
        ns.remove('Category')
        return u'[[%s:' % ns[0]

    def summary(self):
        return u'počeštění jmenného prostoru'

    def handledByCC(self):
        return True

class HeaderHierarchy(HeaderError):

    number = 25

    def apply(self, text, page):
        regex = self.pattern()
        new_text = text
        pos = 0
        prev_level = 8
        while True:
            match = regex.search(new_text, pos)
            if match is None:
                break

            level = len(match.group('start'))
            if level != len(match.group('end')):
                return text

            pos = match.end()
            if level - prev_level > 1:
                eq = '=' * (prev_level + 1)
                new_text = new_text[:match.start()] + u'{eq} {content} {eq}'.format(
                    eq=eq, content=match.group('content').strip()) + new_text[pos:]
            else:
                prev_level = level

        return new_text

    def summary(self):
        return u'oprava úrovně nadpisů'

class MultiplePipes(CheckWikiError):

    number = 32

    def pattern(self):
        return re.compile(r'\[\[([^[\]]+)\]\]')

    def replacement(self, match):
        split = [x.strip() for x in match.group(1).split('|')]
        if ':' in split[0]:
            return match.group()

        if len(split) > 2:
            if '' in split:
                split.remove('')
                return u'[[%s]]' % ('|'.join(split))

            dedup = set(split)
            if len(split) > len(dedup):
                deduplicate(split)
                return u'[[%s]]' % ('|'.join(split))

        return match.group()

    def summary(self):
        return 'oprava odkazu'

    def needsFirst(self):
        return [101]

class MagicWords(CheckWikiError): # TODO

    magic_templates = ('PAGENAME')
    number = 34

    def pattern(self):
        return re.compile(r'(?:\{\{([^}|]+)\}\}|\{\{\{([^}]+)\}\}\})')

    def replacement(self, match):
        if match.group().startswith('{{{'):
            param, sep, value = match.group(2).partition('|')
            return value
##        else:
##            template, sep, value = match.group(1).partition(':')
##            if template.strip() in self.magic_templates:
##                return '{{subst:%s}}' % match.group(1)
        return match.group()

    def apply(self, text, page):
        #regex = textlib.NESTED_TEMPLATE_REGEX
        new_text = text
        while '{{#' in new_text:
            start = new_text.index('{{#')
            index = start + 3
            level = 1
            while level > 0:
                match = re.match(r'(\{\{#?|\}\})', new_text, index)
                if match is None:
                    break
                index = match.end()
                if match.group() == '{{':
                    break
                if match.group == '{{#':
                    level += 1
                else:
                    level = level - 1

            if level == 0:
                to_expand = new_text[start:index]
                expanded = page.site.expand_text(to_expand, page.title())
                if '{{#' in expanded:
                    break
                new_text = new_text[:start] + expanded + new_text[index:]
            else:
                break

        return super(MagicWords, self).apply(text, page)

    def summary(self):
        return u'odstranění kouzelných slov'

class BoldHeader(HeaderError):

    number = 44

    def replacement(self, match, *args):
        content = match.group('content')
        if "'''" in content:
            content = content.replace("'''", '')
            return match.expand(u'\g<start> %s \g<end>' % content.strip())
        else:
            return match.group()

    def summary(self):
        return u'odtučnění nadpisu'

class SelfLink(CheckWikiError):

    number = 48

    def apply(self, text, page):
        page_title = page.title()
        def replace(match):
            split = match.group('inside').split('|')
            if len(split) > 2:
                return match.group()

            if page_title == split[0].replace('_', ' ').strip():
                before = match.group('before') or ''
                after = match.group('after') or ''
                if before != '' or after != '':
                    return before + split[-1] + after

                index = text.replace('&nbsp;', ' ').find(u"'''%s'''" % page_title)
                if index < 0 or match.end() < index:
                    return u"'''%s'''" % split[-1]
                else:
                    return split[-1]

            return match.group()

        return re.sub(r"(?P<before>''')?\[\[(?P<inside>[^\]]+)\]\](?P<after>''')?", replace, text)

    def summary(self):
        return u'odstranění odkazu na sebe'

class InterwikiBeforeHeader(CheckWikiError):

    number = 51

    def handledByCC(self):
        return True

class CategoriesBeforeHeader(CheckWikiError):

    number = 52

    def handledByCC(self):
        return True

class InterwikiBeforeCategory(CheckWikiError):

    number = 53

    def handledByCC(self):
        return True

class ListWithBreak(CheckWikiError):

    list_chars = ':*#'
    number = 54

    def pattern(self):
        return re.compile(r'(?m)^[%s]+.*$' % self.list_chars)

    def replacement(self, match):
        line = match.group()
        if len(re.findall('{{', line)) == len(re.findall('}}', line)):
            return re.sub(r'(?: *<[ /\\]*br[ /\\]*> *)+$', '', line)
        else:
            return line

    def summary(self):
        return u'odstranění zb. zalomení'

class HeaderWithColon(HeaderError):

    number = 57

    def replacement(self, match):
        content = match.group('content').strip()
        if content.endswith(':'):
            return match.expand(u'\g<start> %s \g<end>' % content[:-1].strip())
        else:
            return match.group()

    def summary(self):
        return u'odstranění dvojtečky v nadpisu'

class SmallInsideTags(CheckWikiError):

    number = 63
    tags = ('ref', 'sub', 'sup')

    def pattern(self):
        return re.compile(r'<(?P<tag>%s)(?P<params> [^>]*)?>'
                      '(?P<content>(?:(?!</(?P=tag)>).)*?)'
                      '</(?P=tag)>' % '|'.join(self.tags))

    def replacement(self, match):
        content = match.group('content')
        new_content = re.sub('</?small>', '', content)
        if new_content != content:
            content = new_content.strip()
        return u'<{tag}{params}>{content}</{tag}>'.format(
            tag=match.group('tag'), content=content,
            params=match.group('params') or '')

    def summary(self):
        return u'oprava zmenšení textu uvnitř jiných značek'

class BadListStructure(CheckWikiError): # TODO

    list_chars = ':*#'
    number = 75

    def apply(self, text, page):
        step = ''
        prep = ''
        trunc = 0
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not any(line.startswith(char) for char in self.list_chars):
                step = ''
                prep = ''
                to_left = 0
                continue

            level = re.match('[%s]+' % self.list_chars, line).group()
            if trunc > len(level):
                pass
            elif len(level) - len(step) > 1:
                trunc = len(level) - len(step) - 1

            if len(level) > len(step):
                step = level = step + level[-1]
                to_left = 0
            elif len(level) == len(step):
                level = step
            else:
                step = level = step[:len(level)]
                to_left = 0

            lines[i] = level + line[len(level):]

        return '\n'.join(lines)

    def summary(self):
        return u'oprava odsazení seznamu'

class DuplicateReferences(CheckWikiError):

    number = 81

    def apply(self, text, page):
        ref_regex = re.compile(
            '<ref(?= |>)(?P<params>[^>]*)(?: ?/|>(?P<content>(?:(?!</?ref).)+)</ref)>',
            re.S | re.U)

        param_regex = re.compile(
            '(?P<param>[a-z]+) *= *'
            '(?P<quote>[\'"])?'
            r'(?P<content>(?(quote)(?!(?P=quote)|>).|\w)+)'
            '(?(quote)(?P=quote)|)',
            re.U)

        named_contents = {}
        duplicate_named_contents = {}
        unnamed_contents = {}
        duplicate_unnamed_contents = {}
        names = {}
        destroyed_names = {}
        i = {}

        def getParams(params):
            name = ''
            group = ''
            for match in param_regex.finditer(params):
                if match.group('param') == 'group':
                    group = match.group('content').strip()
                elif match.group('param') == 'name':
                    name = match.group('content').strip()
            return (name, group)

        for match in ref_regex.finditer(text):
            if match.group('content') is None:
                continue
            content = match.group('content').strip()
            name, group = getParams(match.group('params'))

            if group not in named_contents:
                named_contents[group] = [] # the order is important!
                duplicate_named_contents[group] = set()
                unnamed_contents[group] = set()
                duplicate_unnamed_contents[group] = set()
                names[group] = set()
                destroyed_names[group] = {}
                i[group] = 1

            if name == '':
                if content in unnamed_contents[group]:
                    duplicate_unnamed_contents[group].add(content)
                else:
                    unnamed_contents[group].add(content)
            else:
                names[group].add(name)
                if (name, content) not in named_contents[group]:
                    named_contents[group].append(
                        (name, content)
                    )

        def replaceRef(match):
            if match.group('content') is None:
                return match.group()

            content = match.group('content').strip()
            name, group = getParams(match.group('params'))
            if name != '':
                if name in destroyed_names[group]:
                    return match.group() # do in the second round

                for ref_name, ref_content in duplicate_named_contents[group]:
                    if ref_content == content:
                        if ref_name != name:
                            destroyed_names[group][name] = ref_name
                        return u'<ref name="%s"%s />' % (
                            ref_name, (u' group="%s"' % group) if group != '' else '')

                for ref_name, ref_content in named_contents[group]:
                    if ref_content == content:
                        if ref_name == name:
                            named_contents[group].remove(
                                (name, content)
                            )
                            duplicate_named_contents[group].add(
                                (name, content)
                            )
                        else:
                            destroyed_names[group][name] = ref_name
                        return match.group()
                    if ref_name == name:
                        pass # this should not happen!

            else:
                for ref_name, ref_content in named_contents[group] + list(duplicate_named_contents[group]):
                    if ref_content == content:
                        return u'<ref name="%s"%s />' % (
                            ref_name, (u' group="%s"' % group) if group != '' else '')

                if content in duplicate_unnamed_contents[group]:
                    new_name = 'rfr%s' % i[group]
                    while new_name in names[group]:
                        i[group] += 1
                        new_name = 'rfr%s' % i[group]
                    names[group].add(new_name)
                    duplicate_named_contents[group].add(
                        (new_name, content)
                    )
                    return u'<ref name="%s"%s>%s</ref>' % (
                        new_name, (u' group="%s"' % group) if group != '' else '', content)

            return match.group()

        def repairNamesAndTidy(match):
            content = match.group('content')
            params = match.group('params')
            name, group = getParams(params)
            if name.isdigit() and name not in destroyed_names[group]:
                new_name = 'rfr%s' % i[group]
                while new_name in names[group]:
                    i[group] += 1
                    new_name = 'rfr%s' % i[group]
                names[group].add(new_name)
                destroyed_names[group][name] = new_name

            if name in destroyed_names[group]:
                if content is None:
                    return u'<ref name="%s"%s />' % (
                        destroyed_names[group][name],
                        (u' group="%s"' % group) if group != '' else '')
                else:
                    return u'<ref name="%s"%s>%s</ref>' % (
                        destroyed_names[group][name],
                        (u' group="%s"' % group) if group != '' else '',
                        content.strip())

            ref = '<ref'
            for param_match in param_regex.finditer(params):
                param = param_match.group('param')
                quote = param_match.group('quote') or '"'
                param_content = param_match.group('content').strip()
                ref += ' {param}={quote}{content}{quote}'.format(
                    param=param, quote=quote, content=param_content)
            if content is not None:
                return ref + u'>%s</ref>' % content.strip()
            else:
                return ref + ' />'

        new_text = ref_regex.sub(replaceRef, text)
        if new_text != text:
            text = ref_regex.sub(repairNamesAndTidy, new_text)
        return text

    def summary(self):
        return u'oprava duplicitních referencí'

    def needsFirst(self):
        return [104]

class Ordinals(CheckWikiError):

    number = 101

    def pattern(self):
        return re.compile(r'(?i)([1-9]\d*)<sup>(st|nd|rd|th)</sup>')

    def replacement(self, match):
        return match.expand(r'\1\2')

    def summary(self):
        return u'oprava řadových číslovek'

    def needsFirst(self):
        return [81]

class SuperfluousPipe(CheckWikiError):

    number = 103

    def pattern(self):
        return re.compile(r'\[\[([^\]|[{}]+)\{\{!\}\}([^\]|[{}]+)\]\]')

    def replacement(self, match):
        return match.expand(r'[[\1|\2]]')

    def summary(self):
        return u'odstranění zb. kouzelných slov'

class ReferenceQuotes(CheckWikiError):

    number = 104

    def pattern(self):
        return re.compile(r'<ref (?P<params>((?! */>)[^>])+?)(?P<slash> ?/)?>')

    def replacement(self, match):
        def handleParam(p):
            starts = p.group('starts') or ''
            ends = p.group('ends') or ''
            if starts == ends:
                return p.group() # could tidy but not our business now

            if len(starts) > 1:
                starts = '"' if '"' in starts else "'"
            if len(ends) > 1:
                ends = '"' if '"' in ends else "'"
            if starts != ends:
                if len(starts) == 0:
                    starts = ends
                else:
                    ends = starts

            return u'{param}={starts}{content}{ends}'.format(
                content=p.group('content').strip(),
                starts=starts, ends=ends, param=p.group('param'))

        params = re.sub('(?P<param>[a-z]+) *= *(?P<starts>[\'"]+)?'
                        '(?P<content>[^=\'"]*)(?!=)(?P<ends>[\'"]+)?',
                        handleParam, match.group('params'))
        return u'<ref %s%s>' % (params, match.group('slash') or '')

    def summary(self):
        return u'oprava uvozovek v referencích'
