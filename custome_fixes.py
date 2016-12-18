# -*- coding: utf-8 -*-
"""
Module holding fixes which can be applied to most articles.

For use in user_fixes.py, please add to the file:

from scripts.myscripts.custome_fixes import lazy_fixes
fixes.update(
    dict((key, fix.dictForUserFixes()) for key, fix in lazy_fixes.items())
)

"""
import pywikibot
import re

from pywikibot import textlib
from pywikibot.tools import first_lower, first_upper
from pywikibot.tools.formatter import color_format

from scripts.myscripts.checkwiki_errors import CheckWikiError, deduplicate
from scripts.myscripts.typoloader import TypoRule, TyposLoader

class FixGenerator(object):

    '''Iterable wrapper around replacements'''

    def __init__(self, fix):
        self.fix = fix
        self.len = 1

    def __iter__(self):
        self.len = 0
        self.fix.site = pywikibot.Site()
        for repl in self.fix.replacements():
            self.len += 1
            yield repl

    def __len__(self):
        return self.len

class Fix(object):

    '''Abstract class representing a wikitext fix'''

    key = None
    options = {}
    order = 0
    _exceptions = {}

    def __init__(self, **kwargs):
        options = self.options.copy()
        options.update(kwargs)
        for opt, value in options.items():
            setattr(self, opt, value)

    @property
    def site(self):
        if not hasattr(self, '_site'):
            self._site = pywikibot.Site() # todo: is this okay? should load?
        return self._site

    @site.setter
    def site(self, value):
        self._site = value
        self.load()

    def load(self):
        pass

    def generator(self):
        return (x for x in []) # empty

    def dictForUserFixes(self):
        raise NotImplementedError('Fixes for user-fixes.py must extend LazyFix')

    def apply(self, *args):
        raise NotImplementedError('All fixes must be applicable')

    def safeSub(self, text, find, replace):
        exceptions = self.exceptions
        return textlib.replaceExcept(
            text, find, replace,
            exceptions.get('inside', []) + exceptions.get('inside-tags', []),
            site=self.site)

    @property
    def exceptions(self):
        return self._exceptions

class LazyFix(Fix):

    '''Abstract class for fixes that can also be used for user-fixes.py'''

    _exceptions = {
        'inside': [],
        'inside-tags': ['comment', 'nowiki', 'pre', 'source'],
        'text-contains': [],
        'title': []
    }
    _summary = None

    def replacements(self):
        raise NotImplementedError(
            'Fixes extending LazyFix must provide some replacements')

    @classmethod
    def dictForUserFixes(cls):
        fix = cls()
        return {
            'regex': True,
            'msg': fix.message,
            'exceptions': fix.exceptions,
            'replacements': FixGenerator(fix),
        }

    @property
    def message(self):
        return { '_default': self._summary }

    def apply(self, page, summaries=[], callbacks=[]):
        old_text = page.text
        for find, replace in self.replacements():
            page.text = self.safeSub(page.text, find, replace)

        if page.text != old_text:
            summaries.append(self.summary)

    @property
    def summary(self):
        return self._summary

class AdataFix(Fix):

    '''
    Fix adding authority control to articles where it's missing

    Additinal arguments:
    * -minprops - minimal amount of supported properties the item
      should have to include authority control
    '''

    key = 'adata'
    options = {
        'minprops': 2
    }

    def load(self):
        self.props = frozenset(
            ['P213', 'P214', 'P227', 'P244', 'P245', 'P496', 'P691', 'P1051'])
        repo = self.site.data_repository()
        self.human_item = pywikibot.ItemPage(repo, 'Q5')

    def apply(self, page, summaries=[], callbacks=[]):
        text = page.text
        adata = u'{{Autoritní data}}'
        if adata.lower() in text.lower():
            return

        try:
            item = page.data_item()
        except pywikibot.NoPage:
            return

        item.get()
        if not any(st.target_equals(self.human_item)
                   for st in item.claims.get('P31', [])):
            return

        if len(self.props & set(item.claims.keys())) < self.minprops:
            return

        # fixme: l10n
        new_text = re.sub(r'(\{\{[Pp]ortály\|)', r'%s\n\1' % adata, text, count=1)
        if new_text == text:
            new_text = re.sub(r'(\{\{DEFAULTSORT:)', r'%s\n\n\1' % adata, text, count=1)
        if new_text == text:
            new_text = re.sub(r'(\[\[Kategorie:)', r'%s\n\n\1' % adata, text, count=1)
        if new_text != text:
            summaries.append(u'doplnění autoritních dat')
            page.text = new_text
        else:
            pywikibot.output('Failed to add authority control')

class FilesFix(LazyFix):

    key = 'files'
    magic = ['img_alt', 'img_baseline', 'img_border', 'img_bottom',
             'img_center', 'img_class', 'img_framed', 'img_frameless',
             'img_lang', 'img_left', 'img_link', 'img_lossy', 'img_manualthumb',
             'img_middle', 'img_none', 'img_page', 'img_right', 'img_sub',
             'img_super', 'img_text_bottom', 'img_text_top', 'img_thumbnail',
             'img_top', 'img_upright', 'img_width']
    regex = r'\[\[\s*(?:%s)\s*:\s*[^]|[]+(?:\|(?:[^]|[]|\[\[[^]]+\]\])+)+\]\]'
    _summary = u'úpravy obrázků'

    def load(self):
        pywikibot.output("Please help fix [[phab:T148959]] for better wikisyntax parsing")
        self.file_regex = re.compile(
            self.regex % '|'.join(self.site.namespaces[6]))

        self.wordtokey = {}
        self.keytolocal = {}
        for magic in self.magic:
            words = self.site.getmagicwords(magic)
            self.keytolocal[magic] = words.pop(0)
            for word in words:
                self.wordtokey[word] = magic

    def apply(self, page, *args):
        for find, replace in self.replacements():
            page.text = self.safeSub(page.text, find, replace)

    def replacements(self):
        yield (self.file_regex.pattern, self.handleFile)

    def handleFile(self, match):
        if self.file_regex.search(match.group()[2:-2]):
            return match.group() # todo

##      if match.group().count('[[') != match.group().count(']]'):
##          return match.group()

        split = [x.strip() for x in match.group()[2:-2].split('|')]

        split[0] = pywikibot.page.url2unicode(split[0])
        split[0] = re.sub('[ _]+', ' ', split[0]).strip()
        i = 1
        while i < len(split):
            while (split[i].count('[[') != split[i].count(']]') or
                   split[i].count('{{') != split[i].count('}}')):
                split[i] += '|' + split[i+1]
                del split[i+1]

            if split[i].strip() == '':
                del split[i]
                continue

            if split[i] in self.wordtokey:
                split[i] = self.keytolocal[self.wordtokey[split[i]]]
                i += 1
                continue

            if re.match(r'\d*x?\d+(%s)$' %
                        '|'.join(x[2:] for x in self.wordtokey
                                 if x.startswith('$1')), split[i]):
                i += 1
                continue

            word, eq, rest = split[i].partition('=')
            if eq:
                for x, key in self.wordtokey.items():
                    if not x.endswith('=$1'):
                        continue
                    if not x.startswith(word + eq):
                        continue
                    word = self.keytolocal[key].partition('=')[0]
                    break
                else:
                    if rest.endswith('.'): # todo
                        pass

            split[i] = word + eq + rest
            i += 1

        deduplicate(split)

##      start, end = match.start(), match.end() # TODO
##      line_before = "\n" if (start > 0
##                             and match.string[start-1] != "\n") else ''
##      line_after = "\n" if match.string[end] != "\n" else ''
##      return '%s[[%s]]%s' % (line_before, '|'.join(split), line_after)

        return '[[' + '|'.join(split) + ']]'

class CheckWikiFix(LazyFix):

    '''
    Fixes errors detected by Check Wikipedia project

    Additional arguments:
    * -maxsummarycw - (not fully supported yet)
    '''

    key = 'checkwiki'
    options = {
        'maxsummarycw': 5
    }
    _exceptions = {
        'inside-tags': CheckWikiError.exceptions[:],
    }
    _summary = u'opravy dle [[WP:WCW|CheckWiki]]'

    def load(self):
        from scripts.myscripts.checkwiki import CheckWiki
        self.checkwiki = CheckWiki(self.site) # fixme: **kwargs

    def replacements(self):
        for error in self.checkwiki.iter_errors([], forFixes=True):
            pair = error.toTuple()
            yield pair

    def apply(self, page, summaries=[], callbacks=[]):
        replaced = []
        fixed = []
        page.text = self.checkwiki.applyErrors(page.text, page, replaced, fixed)
        if len(replaced) > 0: # todo: maxsummarycw
            summaries.append(u'[[WP:WCW|CheckWiki]]: %s' % ', '.join(replaced))
            callbacks.append(lambda: self.checkwiki.markFixed(fixed, page))

class InterwikiFix(Fix):

    '''Fix removing interwiki links that are on Wikidata'''

    key = 'iw'

    def apply(self, page, summaries=[], callbacks=[]):
        iw_links = textlib.getLanguageLinks(page.text, page.site)
        if len(iw_links) == 0:
            return

        try:
            item = page.data_item()
            item.get()
        except pywikibot.NoPage:
            return

        sitelinks = item.iterlinks(family=page.site.family)
        new_sites = set(iw_links.keys()) - set(page.site for page in sitelinks)
        if len(new_sites) == len(iw_links):
            return

        new_links = dict((site, iw_links[site]) for site in new_sites)

        page.text = textlib.replaceLanguageLinks(page.text, new_links, page.site)
        summaries.append(u'odstranění interwiki')

class RedirectFix(LazyFix):

    '''
    Fixing redirects

    Additional arguments:
    * -onlypiped - only fix links which include "|" (overriden by -always)
    '''

    key = 'redirects'
    options = {
        'onlypiped': False,
    }
    page_title = u'Wikipedista:PastoriBot/narovnaná přesměrování'
    _exceptions = {
        'inside-tags': ['comment', 'nowiki', 'pre', 'source'],
        'text-contains': [u'{{Rozcestník', u'{{rozcestník'],
    }
    _summary = u'narovnání přesměrování'

    def load(self):
        self.redirects = []
        self.cache = {}
        pywikibot.output('Loading redirects')
        page = pywikibot.Page(self.site, self.page_title)
        text = page.get().partition('{{SHORTTOC}}\n')[2]
        for line in text.splitlines():
            if line.strip() == '':
                continue
            if line.startswith('=='):
                continue
            self.redirects.append(line.strip())

        pywikibot.output('%s redirects loaded' % len(self.redirects))

    def replacements(self):
        yield (r'\[\[([^][]+)\]\]', self.replace)

    def replace(self, match):
        split = match.group(1).split('|')
        if len(split) > 2:
            return match.group()
        if len(split) == 1 and self.onlypiped:
            return match.group()
        if split[0].startswith('Kategorie:'): # fixme: l10n
            return match.group()

        page_title = split[0].replace('_', ' ').strip()
        if page_title not in self.redirects:
            return match.group()

        if page_title not in self.cache:
            page = pywikibot.Page(self.site, page_title)
            if not page.exists():
                pywikibot.warning('%s does not exist' % page.title())
                self.redirects.remove(page_title) # fixme: both cases
                return match.group()
            if not page.isRedirectPage():
                pywikibot.warning('%s is not a redirect' % page.title())
                self.redirects.remove(page_title) # fixme: both cases
                return match.group()

            target = page.getRedirectTarget()
            title = target.title()
            if page_title == first_lower(page_title):
                self.cache[page_title] = first_lower(title)
            else:
                self.cache[page_title] = title

        if len(split) == 1:
            options = []
            options_list = [
                '[[%s]]' % page_title,
                '[[%s]]' % self.cache[page_title],
                '[[%s|%s]]' % (self.cache[page_title], page_title)
            ]
            for i, opt in enumerate(options_list, start=1):
                options.append(
                    ('%s %s' % (i, opt), str(i))
                )
            options.append(
                ('Do not replace unpiped links', 'n')
            )

            pre = match.string[max(0, match.start() - 30):match.start()]
            post = match.string[match.end():match.end() + 30]
            pywikibot.output(pre + color_format(u'{lightred}{0}{default}',
                                                match.group()) + post)
            choice = pywikibot.input_choice('Replace this link?',
                                            options, default='1')
            if choice == 'n':
                self.onlypiped = True
                return match.group()
            else:
                return options_list[int(choice)-1]

        # fixme: let CC decide about whitespace
        return '[[%s|%s]]' % (self.cache[page_title], split[-1])

class StyleFix(Fix):

    key = 'mos' # style?
    order = 2 # after CheckWiki

    def load(self):
        self.regex_single = re.compile(
            '<ref(?:(?: name *=([^/=>]+))?>(?:(?!</ref>).)+</ref|'
            ' name *=([^/=>]+)/)>', re.S)
        self.regex_adjacent = re.compile(
            r'(?:\s*<ref(?:(?: name *=[^/=>]+)?>(?:(?!</ref>).)+</ref|'
            ' name *=[^/=>]+/)>){2,}', re.S)

    def sortRef(self, ref, all_names, start):
        name = ref.group(1) or ref.group(2)
        if name:
            name = name.strip('" \'')
            for i, (j, s) in enumerate(all_names):
                if j == name and start + ref.start() > s:
                    return i

        return len(all_names)

    def replaceRefs(self, match, all_names):
        refs = list(self.regex_single.finditer(match.group()))
        assert len(refs) > 1
        refs.sort(key=lambda ref: self.sortRef(ref, all_names, match.start()))
        space_before = match.group()[
            :len(match.group()) - len(match.group().lstrip())]
        return space_before + ''.join(map(lambda ref: ref.group(), refs))

    def sortCategory(self, cat):
        split = cat.title(withNamespace=False, insite=cat.site).split()
        if any(x.isdigit() for x in split): # year
            return 2
        elif u'století' in split: # century
            return 2
        elif 'v' in split or 've' in split: # place
            return 1
        elif any(x.rstrip('.').isdigit() for x in split): # date
            return 3
        return 0

    def apply(self, page, *args):
        # remove empty list items
        page.text = re.sub(r'^\* *\n', '', page.text, flags=re.M)
        # sort adjacent references
        if 'group=' not in page.text and '<references>' not in page.text:
            all_names = []
            for match in self.regex_single.finditer(page.text):
                name = match.group(1) or match.group(2)
                if not name:
                    continue
                name = name.strip('" \'')
                for i, _ in all_names:
                    if i == name:
                        break
                else:
                    all_names.append((name, match.start()))

            if len(all_names) > 0:
                 page.text = self.regex_adjacent.sub(
                     lambda match: self.replaceRefs(match, all_names),
                     page.text)

        # sort categories
        categories = textlib.getCategoryLinks(page.text, site=page.site)
        defaultsort = page.defaultsort()
        category_men = pywikibot.Category(page.site, u'Muži')
        category_women = pywikibot.Category(page.site, u'Ženy')
        category_living = pywikibot.Category(page.site, u'Žijící lidé')
        if any(x in categories for x in (category_men, category_women,
                                         category_living)):
            main_category = None
            birth_categories = []
            death_categories = []
            maint_categories = []
            for cat in categories[:]:
                if defaultsort == cat.sortKey:
                    cat.sortKey = None
                title = cat.title(withNamespace=False, insite=page.site)
                if title.startswith(u'Narození '):
                    birth_categories.append(cat)
                elif title.startswith(u'Úmrtí '):
                    death_categories.append(cat)
                elif title.startswith(u'Údržba:'):
                    maint_categories.append(cat)
                elif cat.sortKey == ' ':
                    main_category = cat
                else:
                    continue
                categories.remove(cat) # fixme: duplicate categories could break this

            is_man = category_men in categories
            is_woman = category_women in categories
            is_alive = category_living in categories
            if is_man:
                categories.remove(category_men)
            if is_woman:
                categories.remove(category_women)
            if is_alive:
                categories.remove(category_living)

            birth_categories.sort(key=self.sortCategory)
            death_categories.sort(key=self.sortCategory)

            if main_category:
                categories.insert(0, main_category)
            categories.extend(birth_categories)
            categories.extend(death_categories)
            categories.extend(maint_categories)
            if is_alive and len(death_categories) == 0:
                categories.append(category_living)
            if is_man:
                categories.append(category_men)
            if is_woman:
                categories.append(category_women)

            page.text = textlib.replaceCategoryLinks(
                page.text, categories, page.site)

        page.text = re.sub(r'(\{\{DEFAULTSORT:[^}]+\}\}\n)\n(\[\[Kategorie:)',
                           r'\1\2', page.text) # fixme: l10n

class TemplateFix(LazyFix):

    '''Fixes redirected templates'''

    key = 'templates'
    _summary = u'narovnání šablon'

    def load(self):
        self.cache = {}
        self.defaultsort = self.site.getmagicwords('defaultsort')

    def replacements(self):
        yield (r'(?P<before>\{\{\s*)(?P<template>[^#{|}]+?)(?P<after>\s*[|}])',
               self.replace)

    def replace(self, match):
        template_name = match.group('template').replace('_', ' ').strip()
        if any(template_name.startswith(x) for x in self.defaultsort):
            return match.group()

        template_name_norm = first_upper(template_name).partition('<!--')[0]
        if template_name_norm not in self.cache:
            template = pywikibot.Page(self.site, template_name_norm, ns=10)
            if template.exists() and template.isRedirectPage():
                target = template.getRedirectTarget()
                self.cache[template_name_norm] = target.title(withNamespace=False)
            else:
                self.cache[template_name_norm] = None

        target = self.cache[template_name_norm]
        if not target:
            return match.group()

        if template_name not in (first_upper(template_name), "n/a"): # todo
            target = first_lower(target)

        return match.group('before') + target + match.group('after')

class TypoFix(LazyFix):

    '''
    Fixing common typos

    Additional arguments:
    * -maxsummarytypos - how many typo replacements to show in edit
      summary at most?
    * -typospage
    * -whitelistpage
    '''

    key = 'typos'
    options = {
        'maxsummarytypos': 5,
        'typospage': None,
        'whitelistpage': None,
    }
    _exceptions = { # todo: whitelist
        'inside-tags': TypoRule.exceptions[:],
    }
    _summary = u'oprava překlepů'
    order = 1 # after redirects

    def load(self):
        loader = TyposLoader(self.site)
        self.typoRules = loader.loadTypos()
        self.whitelist = loader.loadWhitelist()

    def replacements(self):
        return map(
            lambda rule: (rule.find.pattern, rule.replacements[0]),
            self.typoRules)

    def apply(self, page, summaries=[], callbacks=[]):
        if page.namespace() != 0: # todo: generalize
            return
        title = page.title()
        if title in self.whitelist:
            return
        text = page.text
        replaced = []
        for rule in self.typoRules:
            if rule.matches(title):
                continue
            text = rule.apply(text, replaced)
        page.text = text
        count = len(replaced)
        if count > 0: # todo: separate function
            if count > 1:
                max_typos = self.maxsummarytypos
                summary = u'oprava překlepů: %s' % ', '.join(replaced[:max_typos])
                if count > max_typos:
                    if count - max_typos > 1:
                        summary += u' a %s dalších' % (count - max_typos)
                    else:
                        summary += u' a jednoho dalšího'
            else:
                summary = u'oprava překlepu: %s' % replaced[0]

            summaries.append(summary)

lazy_fixes = dict((fix.key, fix) for fix in [
    CheckWikiFix, FilesFix, RedirectFix, TemplateFix, TypoFix])
all_fixes = dict((fix.key, fix) for fix in [
    AdataFix, InterwikiFix, StyleFix])
all_fixes.update(lazy_fixes)

def main(*args):
    pass
