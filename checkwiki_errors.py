# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re
import requests

from pywikibot import textlib
from .tools import deduplicate


class CheckWikiError(object):

    '''Abstract class for each error to extend'''

    exceptions = ['ce', 'comment', 'graph', 'hiero', 'math', 'nowiki',
                  'pre', 'score', 'source', 'startspace']
    needsFirst = []
    url = 'https://tools.wmflabs.org/checkwiki/cgi-bin/checkwiki_bots.cgi'

    def __init__(self, checkwiki):
        self.checkwiki = checkwiki

    @property
    def site(self):
        return self.checkwiki.site

    @property
    def settings(self):
        return self.checkwiki.settings

    def loadError(self, limit=100):
        pywikibot.output('Loading pages with error #%s' % self.number)
        url = '%s?action=list&project=%s&id=%s&limit=%s' % (
            self.url, self.settings['project'], self.number, limit)
        for line in requests.get(url).iter_lines():
            page = pywikibot.Page(self.site, line.decode().replace('title=', '')) # fixme: b/c
            if not page.exists():
                self.markFixed(page)
                continue

            yield page

    def markFixed(self, page):
        data = {
            'action': 'mark',
            'id': self.number,
            'project': self.settings['project'],
            'title': page.title()
        }
        requests.post(self.url, data)

    def apply(self, text, page):
        return textlib.replaceExcept(text, self.pattern(), self.replacement,
                                     self.exceptions, site=page.site)

    def isForFixes(self): # todo: per subclass
        return hasattr(self, 'pattern') and hasattr(self, 'replacement')

    def toTuple(self):
        assert self.isForFixes()
        return (self.pattern().pattern, self.replacement)

    @property
    def priority(self):
        if not hasattr(self, '_priority'):
            for prio, errors in self.settings['priority'].items():
                if self.number in errors:
                    self._priority = prio # number?
                    break

        return self._priority

    def needsDecision(self): # todo: per subclass, user_interactor
        return False

    def handledByCC(self):
        return False

class CCHandledError(CheckWikiError):

    def handledByCC(self):
        return True

class HeaderError(CheckWikiError):

    summary = 'oprava nadpisu'

    def pattern(self):
        return re.compile('(?m)^(?P<start>==+)(?P<content>((?!==|= *$).)+?)(?P<end>==+) *$')

class TagReplacement(CheckWikiError):

    summary = 'odstranění zb. HTML tagu'
    tag = None # extend

    def pattern(self):
        return re.compile(r'(?s)<(?P<tag>%s)>(?P<content>.*?)</(?P=tag)>')

class EntityReplacement(CheckWikiError):

    entities_map = {}
    #needsFirst = [87]
    summary = 'substituce HTML entity'

    def pattern(self):
        return re.compile('&(?P<entity>%s);' % '|'.join(self.entities_map.keys()))

    def replacement(self, match):
        entity = match.group('entity')
        return self.entities_map[entity]

class DefaultsortError(CheckWikiError):

    summary = 'oprava DEFAULTSORTu'

    def pattern(self):
        magic = self.site.getmagicwords('defaultsort')
        return re.compile(r'\{\{ *(?P<magic>%s)(?P<key>[^}]+)\}\}' % '|'.join(magic))

class PrefixedTemplate(CheckWikiError):

    number = 1
    summary = 'odstranění prefixu šablony'

    def pattern(self):
        namespaces = self.site.namespaces[10]
        return re.compile(r'\{\{ *(%s) *: *' % (
            '|'.join(['[%s%s]%s' % (ns[0].upper(), ns[0].lower(), ns[1:]) for ns in namespaces])
            ))

    def replacement(self, match):
        return '{{'

class BrokenHTMLTag(CheckWikiError):

    number = 2
    summary = 'oprava chybné syntaxe HTML tagu'
    tags = ('abbr', 'b', 'big', 'blockquote', 'center', 'cite', 'del', 'div',
            'em', 'font', 'i', 'p', 's', 'small', 'span', 'strike', 'sub',
            'sup', 'table', 'td', 'th', 'tr', 'tt', 'u')

    def pattern(self):
        return re.compile(r'< */+ *([bh]r)[ /]*>')

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
                    params.append(p.group('param', 'content'))
                if len(params) == 1:
                    if params[0][0] == 'id':
                        return '{{Kotva|%s}}' % params[0][1] #fixme: l10n
                    if params[0][0] in ('clear', 'style'):
                        for s in ('right', 'left'):
                            if s in params[0][1]:
                                return '{{Clear|%s}}' % s # fixme: l10n from settings
                        return '{{Clear}}'

            else:
                tags_before = list(
                    re.finditer('<%s(?: (?P<params>[^>]+))?(?<!/)>' % tag,
                                match.string[:match.start()])
                    )
                if len(tags_before) > 0:
                    last = tags_before[-1]
                    if '</%s>' % tag not in match.string[last.end():match.start()]:
                        return '</%s>' % tag
                    else:
                        pass # previous and so on
                else:
                    return ''

            return match.group()

        text = re.sub(
            '<(?P<tag>%s)(?: (?P<params>[^>]+?))? */>' % '|'.join(self.tags),
            replaceTag, text)

        return super(BrokenHTMLTag, self).apply(text, page)

class LowHeadersLevel(HeaderError):

    number = 7
    needsFirst = [8]
    summary = 'oprava úrovní nadpisů'

    def apply(self, text, page):
        regex = self.pattern()
        min_level = 8
        for match in regex.finditer(text):
            start, end = match.group('start', 'end')
            if len(start) == len(end):
                min_level = min(min_level, len(start))
            else:
                return text

        if min_level > 2:
            text = regex.sub(
                lambda match: '{eq} {content} {eq}'.format(
                    eq=match.group('start')[min_level-2:],
                    content=match.group('content').strip()),
                text)

        return text

class MissingEquation(CheckWikiError):

    number = 8
    summary = 'oprava úrovně nadpisů'

    def pattern(self):
        return re.compile(
            '(?m)^(?P<start>=+)(?P<content>.+?)(?P<end>(?: *=+)*) *$')

    def replacement(self, match):
        start, content, end = match.group('start', 'content', 'end')
        if start == end.strip():
            return match.group()

        if end.count('=') != len(end):
            end = end.replace(' ', '')
            if start == end:
                return '%s %s %s' % (start, content.strip(), end)

        return match.group()

class SingleLineCategories(CCHandledError):

    number = 9

class NoEndSquareBrackets(CheckWikiError): # fixme

    exceptions = list(set(CheckWikiError.exceptions) - set(['startspace']))
    needsFirst = [86, 103]
    number = 10
    summary = 'oprava syntaxe odkazu'
    tags = ('pre', 'ref')

    def pattern(self):
        return re.compile(r'(?i)\[\[(?P<inside>(?:(?!\[\[|\]\]|<(?:%s)[ >]).)*)'
                          r'(?P<after>\[\[|\]\])?' % '|'.join(self.tags))

    def replacement(self, match):
        inside, after = match.group('inside', 'after')
        if any(inside.lstrip().lower().startswith(
            '%s:' % x) for x in list(self.site.namespaces[6])):
            return match.group()

        if after == ']]':
            if match.string[match.end():].startswith(']') and '[' in inside:
                return match.group()

            if '|' not in inside:
                if '[' in inside:
                    if inside.startswith('['):
                        return '[[%s]]' % inside.replace('[', '')
                    else:
                        return '[[%s]]' % inside.replace('[', '|')

                elif ']' in inside:
                    return '[[%s]]' % inside.replace(']', '|')
            else:
                return '[[%s]]' % re.sub('[][]', '', inside)

        else:
            if ']' in inside:
                split = inside.split(']', 1)
                return '[[%s%s' % (']]'.join(split), after or '')

            if after == '[[':
                if match.string[match.end():].find(']]') > match.string[match.end():].find('[['):
                    return '[[%s]]' % inside

            if '|' in inside:
                link = inside[:inside.index('|')]
                text = inside[inside.index('|'):]
                space_after = ' ' if text.endswith(' ') else ''
                split_link = link.split()
                split_text = text.split()
                for i, word in enumerate(split_link):
                    if word.lower().startswith(split_link[-1].lower()): # todo: better comparison
                        text = ' '.join(split_text[:i+1])
                        text_after = ' '.join(split_text[i+1:])
                        return '[[%s|%s]] %s%s%s' % (
                            link, text, text_after, space_after, after or '')

                return match.group() # todo: same words in link and text

            if not after and inside.endswith(']'):
                return match.group() + ']'

            #return match.group()[2:]

        return match.group()

class HTMLEntity(EntityReplacement):

    # grave pm centerdot half div rsquor lsquor rdquor ldquor ddagger bullet
    # mldr ap approx leq geq
    entities_map = {
        'acute': '´', 'times': '×', 'sbquo': '‚',
        'prime': '′', 'Prime': '″', 'minus': '−',

        'aacute': 'á', 'Aacute': 'Á', 'acirc': 'â', 'Acirc': 'Â',
        'aelig': 'æ', 'AElig': 'Æ', 'agrave': 'à', 'Agrave': 'À',
        'alpha': 'α', 'aring': 'å', 'Aring': 'Å', 'asymp': '≈',
        'atilde': 'ã', 'Atilde': 'Ã', 'auml': 'ä', 'Auml': 'Ä',
        'beta': 'β', 'bdquo': '„', 'brvbar': '¦', 'bull': '•',
        'ccedil': 'ç', 'Ccedil': 'Ç', 'cent': '¢', 'chi': 'χ',
        'clubs': '♣', 'copy': '©', 'crarr': '↵', 'darr': '↓', 'dArr': '⇓',
        'deg': '°', 'delta': 'δ', 'Delta': 'Δ', 'diams': '♦',
        'divide': '÷', 'eacute': 'é', 'Eacute': 'É', 'ecirc': 'ê',
        'Ecirc': 'Ê', 'egrave': 'è', 'Egrave': 'È', 'epsilon': 'ε',
        'equiv': '≡', 'eta': 'η', 'eth': 'ð', 'ETH': 'Ð', 'euml': 'ë',
        'Euml': 'Ë', 'euro': '€', 'fnof': 'ƒ', 'frac12': '½',
        'frac14': '¼', 'frac34': '¾', 'frasl': '⁄', 'gamma': 'γ',
        'Gamma': 'Γ', 'ge': '≥', 'harr': '↔', 'hArr': '⇔', 'hearts': '♥',
        'hellip': '…', 'iacute': 'í', 'Iacute': 'Í', 'icirc': 'î',
        'Icirc': 'Î', 'iexcl': '¡', 'igrave': 'ì', 'Igrave': 'Ì',
        'infin': '∞', 'int': '∫', 'iota': 'ι', 'Iota': 'Ι', 'iquest': '¿',
        'iuml': 'ï', 'Iuml': 'Ï', 'lambda': 'λ', 'Lambda': 'Λ',
        'laquo': '«', 'larr': '←', 'lArr': '⇐', 'ldquo': '“', 'le': '≤',
        'loz': '◊', 'lsaquo': '‹', 'lsquo': '‘', 'micro': 'µ',
        'middot': '·', 'mu': 'μ', 'ne': '≠', 'not': '¬', 'ntilde': 'ñ',
        'Ntilde': 'Ñ', 'oacute': 'ó', 'Oacute': 'Ó', 'ocirc': 'ô',
        'Ocirc': 'Ô', 'oelig': 'œ', 'OElig': 'Œ', 'ograve': 'ò',
        'Ograve': 'Ò', 'oline': '‾', 'omega': 'ω', 'Omega': 'Ω',
        'ordf': 'ª', 'ordm': 'º', 'oslash': 'ø', 'Oslash': 'Ø',
        'otilde': 'õ', 'Otilde': 'Õ', 'ouml': 'ö', 'Ouml': 'Ö',
        'para': '¶', 'part': '∂', 'permil': '‰', 'phi': 'φ', 'Phi': 'Φ',
        'pi': 'π', 'Pi': 'Π', 'piv': 'ϖ', 'plusmn': '±', 'pound': '£',
        'prod': '∏', 'psi': 'ψ', 'Psi': 'Ψ', 'radic': '√', 'raquo': '»',
        'rarr': '→', 'rArr': '⇒', 'rdquo': '”', 'reg': '®', 'rho': 'ρ',
        'raquo': '»', 'rsaquo': '›', 'rsquo': '’', 'scaron': 'š',
        'Scaron': 'Š', 'sect': '§', 'sigma': 'σ', 'Sigma': 'Σ',
        'sigmaf': 'ς', 'spades': '♠', 'sum': '∑', 'sup1': '¹', 'sup2': '²',
        'sup3': '³', 'szlig': 'ß', 'tau': 'τ', 'theta': 'θ', 'Theta': 'Θ',
        'thetasym': 'ϑ', 'thorn': 'þ', 'THORN': 'Þ', 'tilde': '˜',
        'trade': '™', 'uacute': 'ú', 'Uacute': 'Ú', 'uarr': '↑',
        'uArr': '⇑', 'ucirc': 'û', 'Ucirc': 'Û', 'ugrave': 'ù',
        'Ugrave': 'Ù', 'upsih': 'ϒ', 'upsilon': 'υ', 'uuml': 'ü',
        'Uuml': 'Ü', 'xi': 'ξ', 'Xi': 'Ξ', 'yacute': 'ý', 'Yacute': 'Ý',
        'yen': '¥', 'yuml': 'ÿ', 'Yuml': 'Ÿ', 'zeta': 'ζ', 'Zeta': 'Ζ',
        #'quot': '"',
    }
    number = 11

    def pattern(self):
        return re.compile('&(?P<entity>[A-Za-z0-9]+);')

    def replacement(self, match):
        entity = match.group('entity')
        if entity in self.entities_map:
            return self.entities_map[entity]

        if entity not in ['amp', 'dagger', 'Dagger', 'gt', 'lt', 'mdash',
                          'ndash', 'nbsp', 'quot']:
            pywikibot.output('Unrecognized HTML entity "%s"' % match.group())

        return match.group()

class InvisibleChars(CCHandledError):

    number = 16

class DuplicateCategory(CheckWikiError):

    needsFirst = [21]
    number = 17
    summary = 'odstranění duplicitní kategorie'

    def apply(self, text, page):
        categories = textlib.getCategoryLinks(text)
        if len(categories) > len(set(categories)):
            deduplicate(categories)
            text = textlib.replaceCategoryLinks(text, categories, page.site)
        return text

class LowerCaseCategory(CCHandledError):

    number = 18

class SingleEquationHeader(HeaderError):

    needsFirst = [8]
    number = 19
    summary = 'oprava úrovně nadpisu'

    def pattern(self):
        return re.compile(r'(?m)^=([^\n=]+)= *$')

    def replacement(self, match):
        return '== %s ==' % match.group(1).strip()

class Dagger(EntityReplacement):

    entity_map = {
        'dagger': '†',
        'Dagger': '‡',
    }
    number = 20

class EnglishCategory(CCHandledError):

    number = 21
    summary = 'počeštění jmenného prostoru'

    def pattern(self):
        return re.compile(r'\[\[ *[Cc]ategory *: *')

    def replacement(self, match):
        ns = list(self.site.namespaces[14])
        ns.remove('Category')
        return '[[%s:' % ns[0]

class CategoryWithSpace(CheckWikiError):

    number = 22
    summary = 'odstranění bílých znaků z kategorie'

    def pattern(self):
        return textlib._get_regexes(['category'], self.site).pop()

    def replacement(self, match):
        prefix, _, rest = match.group().strip('[]').partition(':')
        content, key_sep, key = rest.partition('|')

        has_key = bool(key_sep)
        new_prefix = prefix.strip()
        new_content = content.strip()
        new_key = key

        if has_key:
            new_key = key.rstrip()
            if not new_key:
                new_key = ' '

        if (prefix != new_prefix or content != new_content
            or (has_key and key != new_key)):
            if has_key:
                return '[[%s:%s|%s]]' % (new_prefix, new_content, new_key)
            else:
                return '[[%s:%s]]' % (new_prefix, new_content)

        return match.group()

class HeaderHierarchy(HeaderError):

    needsFirst = [8]
    number = 25
    summary = 'oprava úrovně nadpisu'

    def apply(self, text, page):
        regex = self.pattern()
        levels = []
        for match in regex.finditer(text):
            level = len(match.group('start'))
            if level != len(match.group('end')):
                return text
            levels.append(level)

        count = len(levels)
        i = 0
        while count not in (i, i + 1):
            level = levels[i]
            index = i + 1
            while levels[i+1] - level > 1:
                index = count
                for j in range(level, levels[i+1]):
                    if j in levels[i+1:]:
                        index = min(index, levels.index(j, i + 1))

                levels[i+1:index] = list(map(lambda x: x - 1, levels[i+1:index]))
            i = index

        i = 0
        pos = 0
        while True:
            match = regex.search(text, pos)
            if match is None:
                break

            level = len(match.group('start'))
            pos = match.end()
            if level != levels[i]:
                eq = '=' * levels[i]
                text = text[:match.start()] + '{eq} {content} {eq}'.format(
                    eq=eq, content=match.group('content').strip()) + text[pos:]
            i += 1

        return text

class Bold(CCHandledError, TagReplacement):

    needsFirst = [2]
    number = 26
    tag = 'b'

    def replacement(self, match):
        return match.expand("'''\g<content>'''")

class Unicode(CheckWikiError): # todo

    number = 27

class MultiplePipes(CheckWikiError):

    needsFirst = [103]
    number = 32
    summary = 'oprava odkazu'

    def pattern(self):
        return re.compile(r'\[\[([^|[:]+\|[^]|[]*\|[^][]*)\]\]')

    def replacement(self, match):
        split = [x.strip() for x in match.group(1).split('|')]
        if ':' in split[0]:
            return match.group()

        if len(split) > 2:
            if '' in split:
                split.remove('')
                return '[[%s]]' % '|'.join(split)

            if len(set(split)) == 2:
                deduplicate(split)
                return '[[%s]]' % '|'.join(split)

        return match.group()

class MagicWords(CheckWikiError):

    exceptions = CheckWikiError.exceptions[:] + ['gallery', 'ref'] # todo: etc.
    magic_templates = (
        'fullpagename', 'sitename', 'namespace', 'basepagename', 'pagename',
        'subpagename', 'namespacenumber', 'talkpagename', 'fullpagenamee')
    number = 34
    summary = 'odstranění kouzelných slov'

    def pattern(self):
        return re.compile(r'(?:\{\{([^}|]+)\}\}|\{\{\{[^}]+\}\}\})')

    def replacement(self, match):
        if match.group().startswith('{{{'):
            return match.group().strip('{}').partition('|')[2]
        else:
            template, sep, value = match.group().strip('{}').partition(':')
            if template.strip() in self.magic_templates:
                return '{{subst:%s}}' % match.group(1)

        return match.group()

class Italics(CCHandledError, TagReplacement):

    needsFirst = [2]
    number = 38
    tag = 'i'

    def replacement(self, match):
        return match.expand("''\g<content>''")

class StrikedText(TagReplacement):

    needsFirst = [2]
    number = 42
    tag = 'strike'

    def replacement(self, match):
        return match.expand('<s>\g<content></s>')

class BoldHeader(HeaderError):

    #needsFirst = [26]
    number = 44
    summary = 'odtučnění nadpisu'

    def replacement(self, match, *args):
        content = match.group('content')
        if "'''" in content:
            content = content.replace("'''", '')
            return ' '.join([match.group('start'), content.strip(), match.group('end')])
        else:
            return match.group()

class SelfLink(CheckWikiError):

    needsFirst = [103]
    number = 48
    summary = 'odstranění odkazu na sebe'

    def replacement(self, match, title):
        split = match.group('inside').split('|')
        if len(split) > 2:
            return match.group()

        if title == split[0].replace('_', ' ').strip():
            before = match.group('before') or ''
            after = match.group('after') or ''
            if before != '' or after != '':
                return before + split[-1] + after

            index = match.string.replace('&nbsp;', ' ').find(
                "'''%s'''" % title)
            if index < 0 or match.end() < index:
                return "'''%s'''" % split[-1]
            else:
                return split[-1]

        return match.group()

    def apply(self, text, page):
        exceptions = list(set(self.exceptions + [
            'imagemap', 'includeonly', 'timeline']) - set(['startspace']))
        title = page.title()
        return textlib.replaceExcept(
            text, r"(?P<before>''')?\[\[(?P<inside>[^]]+)\]\](?P<after>''')?",
            lambda m: self.replacement(m, title), exceptions, site=page.site)

class HTMLHeader(CCHandledError):

    number = 49

class EntitesAsDashes(EntityReplacement):

    entities_map = {
        'mdash': '—',
        'ndash': '–',
    }
    number = 50

class InterwikiBeforeHeader(CCHandledError):

    number = 51

class CategoriesBeforeHeader(CCHandledError):

    number = 52

class InterwikiBeforeCategory(CCHandledError):

    number = 53

class ListWithBreak(CheckWikiError):

    list_chars = ':*#'
    number = 54
    summary = 'odstranění zb. zalomení'

    def pattern(self):
        return re.compile(r'(?m)^[%s]+.*$' % self.list_chars)

    def replacement(self, match):
        line = match.group()
        if line.count('{{') == line.count('}}'):
            return re.sub(r'(?: *<[ /\\]*br[ /\\]*> *)+$', '', line)
        else:
            return line

class HeaderWithColon(HeaderError):

    number = 57
    summary = 'odstranění dvojtečky v nadpisu'

    def replacement(self, match):
        content = match.group('content').strip()
        if content.endswith(':'):
            return ' '.join([match.group('start'), content[:-1].strip(), match.group('end')])
        else:
            return match.group()

class ParameterWithBreak(CheckWikiError):

    number = 59
    regex = re.compile(r'(?: *<[ /]*br[ /]*> *)+(?P<after>\s*)$')
    summary = 'odstranění zb. zalomení'

    def replacement(self, match):
        if match.group('unhandled_depth'):
            return match.group()

        for template, fielddict in textlib.extract_templates_and_params(
            match.group(), remove_disabled_parts=False, strip=False):
            if template.strip() == match.group('name'):
                changed = False
                name_part = match.group().split('|', 1)[0]
                space_before = re.match(r'\{\{(\s*)', name_part).group(1)
                space_after = re.search(r'(\s*)$', name_part).group(1)
                new_template = '{{' + space_before + template + space_after
                for param, value in fielddict.items():
                    new_value = self.regex.sub(r'\g<after>', value)
                    if new_value != value:
                        changed = True
                    if param.isdigit():
                        return match.group()
                    else:
                        new_template += '|%s=%s' % (param, new_value)

                if changed:
                    return new_template + '}}'

        return match.group()

    def apply(self, text, page):
        return textlib.NESTED_TEMPLATE_REGEX.sub(self.replacement, text)

class RefBeforePunctuation(CheckWikiError):

    number = 61
    punct = '.,:;'
    summary = 'oprava interpunkce'

    # note that this is in general very controversial "error"
    # this algorithm only fixes punctuation when it's both before and after reference
    def apply(self, text, page):
        ref_regex = re.compile('[%s]+ *(?:<ref(?= |>)[^>]*'
                               '(?: ?/|>(?:(?!</?ref).)+</ref)>[%s ]*)+' % (
                                   self.punct, self.punct),
                               re.S)
        return ref_regex.sub(self.replacement, text)

    def replacement(self, match):
        if match.group().startswith(';') and match.string[match.start()-1] == '\n':
            return match.group()

        regex = re.compile('[%s ]+$' % self.punct)
        positions = []
        all_punct = []
        for ref in re.finditer('<ref', match.group()):
            prev_end = start = ref.start()
            before = regex.search(ref.string[:start])
            if before:
                all_punct.append(before.group().strip())
                prev_end -= len(before.group())
            positions.extend([prev_end, start])

        after = regex.search(match.group())
        end = match.end()
        if after:
            all_punct.append(after.group().strip())
            end = after.start()

        positions.pop(0)
        positions.append(end)

        if '' in all_punct:
            all_punct.remove('')

        if (len(all_punct) == 1
            and match.group().lstrip().startswith(all_punct[0])):
            return match.group()

        distinct = set(''.join(all_punct))
        if len(distinct) == 1:
            init = distinct.pop()
        elif any(x.endswith(':') for x in all_punct):
            if '.' in all_punct[0]:
                init = '.:'
            else:
                init = ':'
##        elif any('.' in x for x in all_punct):
##            init = '.'
        elif any(';' in x for x in all_punct):
            init = ';'
        else:
            return match.group()

        space_after = ' ' if match.group().endswith(' ') else ''
        return init + ''.join(match.group()[start:end] for start, end in zip(
            positions[::2], positions[1::2])) + space_after

class SmallInsideTags(CheckWikiError):

    number = 63
    summary = 'oprava zmenšení textu uvnitř jiných značek'
    tags = ('ref', 'sub', 'sup')

    def pattern(self):
        return re.compile('<(?P<tag>%s)(?P<params> [^>]*)?>'
                          '(?P<content>(?:(?!</(?P=tag)>).)*?'
                          '</?small>(?:(?!</(?P=tag)>).)*?)'
                          '</(?P=tag)>' % '|'.join(self.tags))

    def replacement(self, match):
        content = match.group('content')
        new_content = re.sub('</?small>', '', content)
        if new_content != content:
            content = new_content.strip()
        return '<{tag}{params}>{content}</{tag}>'.format(
            tag=match.group('tag'), content=content,
            params=match.group('params') or '')

class BadListStructure(CheckWikiError): # todo

    list_chars = ':*#'
    number = 75
    summary = 'oprava odsazení seznamu'

    def replace(self, match, levels):
        line = match.group()
        if not any(line.startswith(char) for char in self.list_chars):
            levels[:] = ['']
            return line

        this, rest = re.match('([%s]+)(.*)$' % self.list_chars, line).groups()

        for old, new in levels[1:]:
            if this.startswith(old):
                this = new + this[len(old):]

        for pair in set(levels[1:]): # move above?
            if len(this) < len(pair[1]):
                levels.remove(pair)

        prev = levels[0]
        if len(this) >= len(prev): # this needs todo
            if not this.startswith(prev):
                if len(this) == len(prev):
                    levels.append(
                        (this, prev + this[-1])
                    )
                    this = prev + this[-1]
                else:
                    levels.append(
                        (this, prev + this[len(prev):])
                    )
                    this = prev + this[len(prev):]

            if len(this) - len(prev) > 1:
                levels.append(
                    (this, prev + this[-1])
                )
                this = prev + this[-1]

        levels[0] = this

        return this + rest

    def apply(self, text, page):
        levels = ['']
        regex = re.compile('^.*$', re.M)
        return textlib.replaceExcept(
            text, regex, lambda match: self.replace(match, levels),
            self.exceptions[:], site=self.site)

class NoSpace(CheckWikiError): # todo

    number = 76

class BrokenExternalLink(CheckWikiError): # todo

    number = 80
    summary = 'oprava externího odkazu'

    def pattern(self):
        return re.compile(r'\[(?P<link>https?://[^][\n<]+)'
                          r'(?P<stop>\]|</?ref|\n|\[)')

    def replacement(self, match):
        link, stop = match.group('link', 'stop')
        if stop == ']':
            return match.group()

        if ' ' not in link:
            return match.expand(r'[\g<link>]\g<stop>')

        if stop in ('<ref', '</ref'):
            return match.expand(r'[\g<link>]\g<stop>')

        return match.group()

class DuplicateReferences(CheckWikiError):

    # fixme: we don't know what this could cause
    exceptions = CheckWikiError.exceptions[:] + ['references']
    needsFirst = [104]
    number = 81
    summary = 'oprava duplicitních referencí'

    def apply(self, text, page):
        ref_regex = re.compile(
            '<ref(?= |>)(?P<params>[^>]*)'
            '(?: ?/|>(?P<content>(?:(?!</?ref).)+)</ref)>',
            re.S | re.U)

        param_regex = re.compile(
            '(?P<param>[a-z]+) *= *'
            '(?P<quote>[\'"])?'
            r'(?P<content>(?(quote)(?!(?P=quote)|>).|[\w-])+)'
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

            named_contents.setdefault(group, [])
            duplicate_named_contents.setdefault(group, set())
            unnamed_contents.setdefault(group, set())
            duplicate_unnamed_contents.setdefault(group, set())
            names.setdefault(group, set())
            destroyed_names.setdefault(group, {})
            i.setdefault(group, 1)

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
                        return '<ref name="%s"%s />' % (
                            ref_name, (' group="%s"' % group)
                            if group != '' else '')

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
                        pass # fixme: this should not happen!

            else:
                for ref_name, ref_content in named_contents[group] + list(duplicate_named_contents[group]):
                    if ref_content == content:
                        return '<ref name="%s"%s />' % (
                            ref_name, (' group="%s"' % group)
                            if group != '' else '')

                if content in duplicate_unnamed_contents[group]:
                    new_name = 'rfr%s' % i[group]
                    while new_name in names[group]:
                        i[group] += 1
                        new_name = 'rfr%s' % i[group]
                    names[group].add(new_name)
                    duplicate_named_contents[group].add(
                        (new_name, content)
                    )
                    return '<ref name="%s"%s>%s</ref>' % (
                        new_name, (' group="%s"' % group)
                        if group != '' else '', content)

            return match.group()

        def repairNamesAndTidy(match):
            content, params = match.group('content', 'params')
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
                    return '<ref name="%s"%s />' % (
                        destroyed_names[group][name],
                        (' group="%s"' % group) if group != '' else '')
                else:
                    return '<ref name="%s"%s>%s</ref>' % (
                        destroyed_names[group][name],
                        (' group="%s"' % group) if group != '' else '',
                        content.strip())

            ref = '<ref'
            for param_match in param_regex.finditer(params):
                param = param_match.group('param')
                quote = param_match.group('quote') or '"'
                param_content = param_match.group('content').strip()
                ref += ' {param}={quote}{content}{quote}'.format(
                    param=param, quote=quote, content=param_content)
            if content is not None:
                return ref + '>%s</ref>' % content.strip()
            else:
                return ref + ' />'

        new_text = ref_regex.sub(replaceRef, text)
        if new_text != text:
            text = ref_regex.sub(repairNamesAndTidy, new_text)
        return text

class EmptyTag(CheckWikiError):

    number = 85
    summary = 'odstranění prázdného tagu'
    tags = ('center', 'code', 'div', 'gallery', 'includeonly', 'noinclude',
            'onlyinclude', 'pre', 'ref', 'span')

    def pattern(self):
        # todo: add attributes and whitelist some of them
        return re.compile(r'<(%s)>(\s*)</\1>' % '|'.join(self.tags))

    def replacement(self, match):
        return match.expand(r'\2')

class ExternalLinkLikeInternal(CCHandledError):

    number = 86
    summary = 'oprava syntaxe odkazu'

class DefaultsortSpace(DefaultsortError):

    number = 88

    def replacement(self, match):
        magic, key = match.group('magic', 'key')
        if key.startswith(' '):
            return '{{%s%s}}' % (magic, key.strip())

        return match.group()

class DefaultsortComma(DefaultsortError):

    number = 89

    def replacement(self, match):
        magic, key = match.group('magic', 'key')
        if ',' in key and ', ' not in key:
            split = key.split(',')
            return '{{%s%s}}' % (magic, ', '.join(x.strip() for x in split))

        return match.group()

class InternalLink(CCHandledError):

    number = 90
    summary = 'oprava odkazu'
    # todo: inside files

class DoubleHttp(CheckWikiError):

    exceptions = list(set(CheckWikiError.exceptions) - set(['startspace']))
    number = 93
    summary = 'oprava externího odkazu'

    def pattern(self):
        return re.compile('(?i)(?:https?:*/*){2,}')

    def replacement(self, match):
        return match.group()[match.group().rfind('http'):]

class Ordinals(CheckWikiError):

    needsFirst = [81]
    number = 101
    summary = 'oprava řadových číslovek'

    def pattern(self):
        return re.compile(r'(?i)([1-9]\d*)<sup>(st|nd|rd|th)</sup>')

    def replacement(self, match):
        return match.expand(r'\1\2')

class SuperfluousPipe(CheckWikiError):

    number = 103
    summary = 'odstranění zb. kouzelných slov'

    def pattern(self):
        return re.compile(r'\[\[([^]|[{}]+)\{\{!\}\}([^]|[{}]+)\]\]')

    def replacement(self, match):
        return match.expand(r'[[\1|\2]]')

class ReferenceQuotes(CheckWikiError):

    number = 104
    summary = 'oprava uvozovek v referencích'

    def pattern(self):
        return re.compile('<ref (?P<params>((?! */>)[^>])+?)(?P<slash> ?/)?>')

    def replacement(self, match):
        def handleParam(p):
            starts = p.group('starts') or ''
            ends = p.group('ends') or ''
            if starts == ends and len(starts) < 2 and len(ends) < 2:
                return p.group() # could tidy but not our business now

            if len(starts) > 1:
                starts = '"' if '"' in starts else "'"
            if len(ends) > 1:
                ends = '"' if '"' in ends else "'"

            quote = starts
            if starts != ends and len(starts) == 0:
                quote = ends

            return '{param}={quote}{content}{quote}'.format(
                content=p.group('content').strip(),
                quote=quote, param=p.group('param'))

        params = re.sub('(?P<param>[a-z]+) *= *(?P<starts>[\'"])?'
                        '(?(starts)(?P=starts)*)'
                        '(?P<content>(?:(?!(?(starts)(?P=starts)|[\'"=])).)*)'
                        '(?P<ends>[\'"]+)?',
                        handleParam, match.group('params'))

        return '<ref %s%s>' % (params, match.group('slash') or '')
