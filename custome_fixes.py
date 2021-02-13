"""
Module holding fixes which can be applied to most articles.

For use in user_fixes.py, please add to the file:

from scripts.myscripts.custome_fixes import lazy_fixes
fixes.update((key, fix.dictForUserFixes()) for key, fix in lazy_fixes.items())
"""
import re

from collections import defaultdict
from itertools import chain
from operator import itemgetter, methodcaller

import pywikibot

from pywikibot import pagegenerators, textlib
from pywikibot.textlib import mwparserfromhell
from pywikibot.tools import first_lower, first_upper
from pywikibot.tools.formatter import color_format

from .checkwiki_errors import CheckWikiError
from .tools import deduplicate, FULL_ARTICLE_REGEX
from .typoloader import TypoRule, TyposLoader


class FixGenerator:

    '''Iterable wrapper around replacements'''

    def __init__(self, fix):
        self.fix = fix

    def __iter__(self):
        self.fix.site = pywikibot.Site()
        return iter(self.fix.replacements())

    def __len__(self):
        return 1

    def __nonzero__(self):
        return True


class BaseFix:

    '''Abstract class representing a wikitext fix'''

    key = None
    options = {}
    order = 0

    def __init__(self, **kwargs):
        options = self.options.copy()
        options.update(kwargs)
        for opt, value in options.items():
            setattr(self, opt, value)

    def apply(self, page, *args):
        raise NotImplementedError('All fixes must be applicable')

    @property
    def site(self):
        if not hasattr(self, '_site'):
            self._site = pywikibot.Site()  # todo: is this correct? should load?
        return self._site

    @site.setter
    def site(self, value):
        self._site = value
        self.load()

    def load(self):
        pass

    def generator(self):
        return (x for x in [])  # empty


class Fix(BaseFix):

    '''A wikitext fix that needs access to the page'''

    exceptions = {}

    def dictForUserFixes(self):
        raise NotImplementedError('Fixes for user-fixes.py must extend LazyFix')

    @property
    def exceptions(self):
        return self.exceptions


class LazyFix(BaseFix):

    '''Abstract class for fixes that can also be used for user-fixes.py'''

    exceptions = {
        'inside': [],
        'inside-tags': ['comment', 'nowiki', 'pre', 'syntaxhighlight'],
        'text-contains': [],
        'title': []
    }
    message = None
    nocase = False
    recursive = False

    def replacements(self):
        raise NotImplementedError(
            'Fixes extending LazyFix must provide some replacements')

    @classmethod
    def dictForUserFixes(cls):
        fix = cls()
        return {
            'exceptions': fix.exceptions,
            'msg': {
                '_default': fix.message,
            },
            'nocase': fix.nocase,
            'recursive': fix.recursive,
            'regex': True,
            'replacements': FixGenerator(fix),
        }

    def safeSub(self, text, find, replace):
        exceptions = self.exceptions
        return textlib.replaceExcept(
            text, find, replace,
            exceptions.get('inside', []) + exceptions.get('inside-tags', []),
            site=self.site)

    def apply(self, page, summaries=[], callbacks=[]):
        old_text = page.text
        for find, replace in self.replacements():
            page.text = self.safeSub(page.text, find, replace)

        if page.text != old_text and self.summary:
            summaries.append(self.summary)
        return page.text != old_text

    @property
    def summary(self):
        return self.message


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

    def generator(self):
        extra = {
            'common_wiki': 'wikidata',
            'templates_no': 'Autoritní data',  # l10n!
            'wikidata_source_sites': self.site.dbName(),
            'wikidata_item': 'with',
            'wikidata_prop_item_use': ','.join(self.props),
        }
        petscan = pagegenerators.PetScanPageGenerator(
            ['Muži', 'Ženy', 'Žijící_lidé'], subset_combination=False,
            site=self.site, namespaces=[0], extra_options=extra)  # l10n!
        items = pagegenerators.PreloadingItemGenerator(petscan)  # hack
        return pagegenerators.WikidataPageFromItemGenerator(items, self.site)

    def apply(self, page, summaries=[], callbacks=[]):
        text = page.text
        adata = '{{Autoritní data}}'  # fixme: l10n
        if adata.lower() in text.lower():  # fixme: with parameters
            return

        try:
            item = page.data_item()
        except pywikibot.NoPage:
            return

        claims = item.get().get('claims')
        if not any(st.target_equals(self.human_item)
                   for st in claims.get('P31', [])):
            return  # fixme: not mandatory

        if len(self.props & set(claims.keys())) < self.minprops:
            return

        new_text = re.sub(r'(\{\{[Pp]ortály\|)', r'%s\n\1' % adata, text,
                          count=1)  # fixme: l10n
        if new_text == text:
            new_text = re.sub(
                r'\{\{ *(%s)' % '|'.join(
                    map(re.escape, page.site.getmagicwords('defaultsort'))),
                r'%s\n\n{{\1' % adata, text, count=1)
        if new_text == text:
            new_text = re.sub(
                r'\[\[ *(%s)' % '|'.join(
                    map(re.escape, page.site.namespaces[14])),
                r'%s\n\n[[\1' % adata, text, count=1, flags=re.I)
        if new_text != text:
            summaries.append('doplnění autoritních dat')
            page.text = new_text
        else:
            pywikibot.output('Failed to add authority control')


class CategoriesFix(LazyFix):

    '''
    Fixes category sortkeys
    '''

    key = 'categories'
    message = 'oprava řazení kategorií'

    def generator(self):
        pass  # incategory:"Muži|Ženy|Žijící lidé" insource:/\[\[Kategorie:[^]|[]+\|[^],]+,/

    def load(self):
        magic_words = map(re.escape, self.site.getmagicwords('defaultsort'))
        self.defaultsortR = re.compile(
            r'\{\{(?:%s)([^}]+)\}\}' % '|'.join(magic_words))

    def replacements(self):
        yield (FULL_ARTICLE_REGEX, self.duplicateSortKey)
        yield (FULL_ARTICLE_REGEX, self.harvestSortKey)

    def sort_category(self, category):
        MAIN_CATEGORY = 0
        REGULAR_CATEGORY = 1
        BIRTH_CATEGORY = 10
        DEATH_CATEGORY = 20
        PLACE = 0
        CENTURY = 1
        YEAR = 2
        DATE = 3
        LIVING_CATEGORY = 30
        MAINTENANCE_CATEGORY = 50
        GENDER_CATEGORY = 100
        if category.sortKey == ' ':
            return MAIN_CATEGORY

        title = category.title(with_ns=False, insite=category.site)
        split = title.split()
        if title.startswith('Údržba:'):
            return MAINTENANCE_CATEGORY
        if title == 'Žijící lidé':
            return LIVING_CATEGORY
        if title in ('Muži', 'Ženy'):
            return GENDER_CATEGORY

        index = REGULAR_CATEGORY
        if split[0] in ('Narození', 'Úmrtí'):
            if title.startswith('Narození'):
                index = BIRTH_CATEGORY
            elif title.startswith('Úmrtí'):
                index = DEATH_CATEGORY

            if 'století' in split:
                index += CENTURY
            elif 'v' in split or 've' in split:
                index += PLACE
            elif split[1] == split[-1] and split[-1].isdigit():
                index += YEAR
            else:
                index += DATE

        return index

    def tidy_sortkey(self, sortkey):
        if sortkey:
            return ', '.join(re.split(r', *', sortkey.strip()))
        return sortkey

    def duplicateSortKey(self, match):
        text = match.group()
        matches = list(self.defaultsortR.finditer(text))
        if not matches:
            return text

        defaultsort = matches.pop().group(1).strip()
        categories = textlib.getCategoryLinks(text, site=self.site)
        changed = False
        for category in categories:
            if self.tidy_sortkey(category.sortKey) == defaultsort:
                category.sortKey = None
                changed = True

        if changed:
            categories.sort(key=self.sort_category)
            before, _, after = textlib.replaceCategoryLinks(
                text, categories, self.site).rpartition('\n\n')  # fixme: safer
            return before + '\n' + after
        else:
            return text

    def harvestSortKey(self, match):
        text = match.group()
        if self.defaultsortR.search(text):
            return text

        keys = defaultdict(lambda: 0.0)
        categories = textlib.getCategoryLinks(text, site=self.site)
        if not any(category.title(with_ns=False) in (
                'Muži', 'Žijící lidé', 'Ženy') for category in categories):
            return text

        for category in categories:
            key = category.sortKey
            if key:
                key = self.tidy_sortkey(key)
                if not key.strip():
                    continue
                keys[key] += 1
                if len(keys) > 1:
                    return text

        if not keys:
            return text

        if sum(keys.values()) < 4:
            return text

        key = list(keys.keys()).pop()
        for category in categories:
            if category.sortKey is not None:
                if self.tidy_sortkey(category.sortKey) == key:
                    category.sortKey = None

        categories.sort(key=self.sort_category)
        text = textlib.removeCategoryLinks(text, self.site)
        text += '\n\n{{DEFAULTSORT:%s}}' % key
        before, _, after = textlib.replaceCategoryLinks(
            text, categories, self.site).rpartition('\n\n')  # fixme: safer
        return before + '\n' + after

    def apply(self, page, summaries=[], *args):
        result = super().apply(page, summaries, *args)
        if result:
            categories = textlib.getCategoryLinks(page.text, site=self.site)
            categories.sort(key=self.sortCategories)
            page.text = textlib.replaceCategoryLinks(page.text, categories,
                                                     self.site)
        return result


class FilesFix(LazyFix):

    key = 'files'
    magic = ('img_alt', 'img_baseline', 'img_border', 'img_bottom',
             'img_center', 'img_class', 'img_framed', 'img_frameless',
             'img_lang', 'img_left', 'img_link', 'img_lossy', 'img_manualthumb',
             'img_middle', 'img_none', 'img_page', 'img_right', 'img_sub',
             'img_super', 'img_text_bottom', 'img_text_top', 'img_thumbnail',
             'img_top', 'img_upright', 'img_width')
    message = 'úpravy obrázků'
    regex = r'\[\[\s*(?:%s)\s*:\s*[^]|[]+(?:\|(?:[^]|[]|\[\[[^]]+\]\])+)+\]\]'

    def load(self):
        self.file_regex = re.compile(
            self.regex % '|'.join(self.site.namespaces[6]))

        self.wordtokey = {}
        self.keytolocal = {}
        for magic in self.magic:
            words = self.site.getmagicwords(magic)
            self.keytolocal[magic] = words[0]
            for word in words[1:]:
                self.wordtokey[word] = magic

    @property
    def summary(self):
        return None  # ??

    def replacements(self):
        yield (self.file_regex.pattern, self.handleFile)

    def handleFile(self, match):
        inner = match.group()[2:-2]
        if self.file_regex.search(inner):
            return match.group() # todo

##      if match.group().count('[[') != match.group().count(']]'):
##          return match.group()

        split = inner.split('|')

        split[0] = pywikibot.page.url2unicode(split[0].strip())
        split[0] = re.sub('[ _]+', ' ', split[0]).strip()
        i = 1
        while i < len(split):
            while (split[i].count('[[') != split[i].count(']]') or
                   split[i].count('{{') != split[i].count('}}')):
                split[i] += '|' + split[i+1]
                split.pop(i+1)

            split[i] = split[i].strip()
            if split[i] == '':
                split.pop(i)
                continue

            if split[i] in self.wordtokey:
                split[i] = self.keytolocal[self.wordtokey[split[i]]]
                i += 1
                continue

            regex = re.compile(r'\d*x?\d+(%s)' % '|'.join(
                re.escape(word[2:]) for word in self.wordtokey
                if word.startswith('$1')))
            if regex.fullmatch(split[i]):
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
                    # if rest.endswith('.'): todo
                    pass

            split[i] = word + eq + rest
            i += 1

        deduplicate(split)

        return '[[%s]]' % '|'.join(split)


class CheckWikiFix(LazyFix):  # todo: make abstract and split

    '''
    Fixes errors detected by Check Wikipedia project

    Additional arguments:
    * -maxsummarycw - (not supported yet)
    '''

    key = 'checkwiki'
    message = 'opravy dle [[WP:WCW|CheckWiki]]'
    options = {
        'maxsummarycw': 5  # todo: really support
    }
    exceptions = {
        'inside-tags': CheckWikiError.exceptions[:],  # fixme: split
    }

    def load(self):
        from .checkwiki import CheckWiki  # fixme
        self.checkwiki = CheckWiki(self.site)

    #def generator(self): todo

    def replacements(self):
        for error in self.checkwiki.iter_errors(only_for_fixes=True):
            pair = error.toTuple()
            yield pair

    def apply(self, page, summaries=[], callbacks=[]):
        replaced = []
        fixed = []
        page.text = self.checkwiki.apply(page.text, page, replaced, fixed)
        if replaced:  # todo: maxsummarycw
            summaries.append('[[WP:WCW|CheckWiki]]: %s' % ', '.join(replaced))
            callbacks.append(
                lambda: self.checkwiki.mark_as_fixed_multiple(page, fixed))


class InterwikiFix(Fix):

    '''Fix removing interwiki links that are on Wikidata'''

    key = 'iw'

    def apply(self, page, summaries=[], callbacks=[]):
        iw_links = textlib.getLanguageLinks(page.text, page.site)
        if not iw_links:
            return

        try:
            item = page.data_item()
            item.get()
        except pywikibot.NoPage:
            return

        sitelinks = item.iterlinks(family=page.site.family)
        new_sites = set(iw_links.keys()) - {page.site for page in sitelinks}
        if len(new_sites) == len(iw_links):
            return

        new_links = {site: iw_links[site] for site in new_sites}

        page.text = textlib.replaceLanguageLinks(page.text, new_links, page.site)
        summaries.append('odstranění interwiki')


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
    page_title = 'Wikipedista:PastoriBot/narovnaná přesměrování'
    exceptions = {
        'inside-tags': ['comment', 'nowiki', 'pre', 'syntaxhighlight'],
        'text-contains': ['{{Rozcestník', '{{rozcestník'],
    }
    message = 'narovnání přesměrování'

    def generator(self):
        for title in self.redirects:
            yield from pywikibot.Page(self.site, title).backlinks(
                followRedirects=False, filterRedirects=False, namespaces=0)

    def get_redirects(self):
        redirects = []  # todo: set?
        pywikibot.output('Loading redirects')
        page = pywikibot.Page(self.site, self.page_title)
        text = page.text.partition('{{SHORTTOC}}\n')[2]
        for line in text.splitlines():
            if line.strip() == '':
                continue
            if line.startswith('=='):
                continue
            redirects.append(line.strip())

        return redirects

    def load(self):
        self.cache = {}
        self.redirects = self.get_redirects()
        pywikibot.output('%d redirects loaded' % len(self.redirects))

    def from_cache(self, link):
        link = link.replace('_', ' ').strip()  # todo: normalize completely
        if link not in self.redirects:
            return False

        if link not in self.cache:
            page = pywikibot.Page(self.site, link)
            if not page.exists():
                pywikibot.warning('%s does not exist' % page.title())
                self.redirects.remove(link)  # fixme: both cases
                return False
            if not page.isRedirectPage():
                pywikibot.warning('%s is not a redirect' % page.title())
                self.redirects.remove(link)  # fixme: both cases
                return False

            target = page.getRedirectTarget()
            title = target.title()
            if link == first_lower(link):
                self.cache[link] = first_lower(title)
            else:
                self.cache[link] = title

        return self.cache[link]

    def replacements(self):
        yield (r'\[\[([^]|[<>]+)\|', self.replace1)
        yield (r'\[\[([^]|[<>]+)\]\](%s)?' % self.site.linktrail(),
               self.replace2)

    def replace1(self, match):
        link = match.group(1)
        target = self.from_cache(link)
        if not target:
            return match.group()

        left_spaces = len(link) - len(link.lstrip())
        right_spaces = len(link) - len(link.rstrip())
        return '[[%s%s%s|' % (left_spaces * ' ', target, right_spaces * ' ')

    def replace2(self, match):
        link = match.group(1)
        trail = match.group(2) or ''
        target = self.from_cache(link)
        if not target:
            return match.group()

        left_spaces = len(link) - len(link.lstrip())
        right_spaces = len(link) - len(link.rstrip())
        if (link.lstrip() + trail).startswith(target):
            rest = (link.lstrip() + trail)[len(target):]
            return '[[%s%s]]%s' % (' ' * left_spaces, target, rest)

        if self.onlypiped is True:  # todo: user_interactor
            return match.group()

        options_list = [match.group()]
        if not trail:
            options_list.append(
                '[[%s%s%s]]' % (left_spaces * ' ', target, right_spaces * ' ')
            )
        options_list.append(
            '[[%s|%s%s]]' % (target, link, trail)
        )

        options = [
            ('%d %s' % (i, opt), str(i))
            for i, opt in enumerate(options_list, start=1)
        ] + [('Do not replace unpiped links', 'n')]

        pre = match.string[max(0, match.start() - 30):match.start()].rpartition('\n')[2]
        post = match.string[match.end():match.end() + 30].partition('\n')[0]
        pywikibot.output(color_format('{0}{lightred}{1}{default}{2}',
                                      pre, match.group(), post))
        choice = pywikibot.input_choice('Replace this link?', options,
                                        default='1', automatic_quit=False)
        if choice == 'n':
            self.onlypiped = True
            choice = 1

        return options_list[int(choice)-1]


class RedirectsFromFileFix(RedirectFix):

    key = 'redirects-file'

    def get_redirects(self):
        return [page.title() for page in pagegenerators.TextfilePageGenerator(
            site=self.site)]
        

class RefSortFix(LazyFix):

    '''
    Fix that reorders references in text
    '''

    key = 'sortref'
    message = 'seřazení referencí'
    order = 2  # after checkwiki

    def load(self):
        self.regex_single = re.compile(
            '<ref(?:(?: name *=([^/=>]+))?>(?:(?!</ref>).)+</ref|'
            ' name *=([^/=>]+)/)>', re.S)
        self.regex_adjacent = re.compile(
            r'(?:\s*<ref(?:(?: name *=[^/=>]+)?>(?:(?!</ref>).)+</ref|'
            ' name *=[^/=>]+/)>){2,}', re.S)

    def sortkey(self, ref, all_names, start):
        name = ref.group(1) or ref.group(2)
        if name:
            name = name.strip('" \'')
            for i, (j, s) in enumerate(all_names):
                if j == name and start + ref.start() > s:
                    return i

        return len(all_names)

    def replace_refs(self, match, all_names):
        refs = list(self.regex_single.finditer(match.group()))
        assert len(refs) > 1
        refs.sort(key=lambda ref: self.sortkey(ref, all_names, match.start()))
        space_before = match.group()[
            :len(match.group()) - len(match.group().lstrip())]
        return space_before + ''.join(map(methodcaller('group'), refs))

    def replacements(self):
        yield (FULL_ARTICLE_REGEX, self.replace)

    def replace(self, match):
        text = match.group()
        if 'group=' in text or '<references>' in text: # todo
            return text

        all_names = []
        for match in self.regex_single.finditer(text):
            name = match.group(1) or match.group(2)
            if not name:
                continue
            name = name.strip('" \'')
            for i, _ in all_names:
                if i == name:
                    break
            else:
                all_names.append((name, match.start()))

        if all_names:
            callback = lambda match: self.replace_refs(match, all_names)
            text = self.regex_adjacent.sub(callback, text)

        return text


class SectionsFix(LazyFix):

    '''
    This fix reorders and cleans up closing sections (those with references,
    external links etc.)
    '''

    key = 'sections'
    bad_headers = ('Zdroj', 'Zdroje',)
    replace_headers = {
        'Externí odkaz': 'Externí odkazy',
        'Externí zdroj': 'Externí odkazy',
        'Externí zdroje': 'Externí odkazy',
        'Podívejte se také na': 'Související články',
        'Podobné články': 'Související články',
        'Související stránka': 'Související články',
        'Související stránky': 'Související články',
        'Viz též': 'Související články',
    }
    root_header = 'Odkazy'
    headers_in_order = ('Poznámky',
                        'Reference',
                        'Literatura',
                        'Související články',
                        'Externí odkazy',
                        )
    message = 'standardizace závěrečných sekcí'
    order = 3

    def load(self):
        self.parser = mwparserfromhell
        self.can_load = not isinstance(self.parser, Exception)

    def replacements(self):
        if self.can_load:
            yield (FULL_ARTICLE_REGEX, self.replace)
        else:
            pywikibot.error('Cannot run SectionsFix when mwparserfromhell '
                            'is not installed')

    def iter_all_headers(self):
        return chain(self.headers_in_order, self.bad_headers, [self.root_header])

    def add_contents(self, sections, code):
        next_index = code.nodes.index(sections[0]['nodes'][-1])
        for i in range(1, len(sections)):
            this_index = code.nodes.index(sections[i-1]['nodes'][0])
            next_index = code.nodes.index(sections[i]['nodes'][0], this_index+1)
            sections[i-1]['nodes'].extend(code.nodes[this_index+1:next_index])

        index = next_index + 1
        for index, node in enumerate(code.nodes[index:], start=index):
            if isinstance(node, self.parser.nodes.wikilink.Wikilink):
                text = str(node)[2:-2]
                link = pywikibot.Link(text, self.site)
                try:
                    diff_site = link.site != self.site
                except Exception:
                    diff_site = True
                if diff_site:
                    break
                if link.namespace == 14:
                    break
            elif isinstance(node, self.parser.nodes.template.Template):
                if node.name.startswith(
                    tuple(self.site.getmagicwords('defaultsort'))):
                    break
                if any(node.name.matches(x) for x in ('Překlad', 'ID autority')):
                    pass
                elif str(code.nodes[index-1]).endswith('\n'):
                    break
            sections[-1]['nodes'].append(node)
        else:
            index += 1

        return index

    def deduplicate(self, sections, code):
        do_more = False
        for name in {sect['name'] for sect in sections}:
            dupes = [sect for sect in sections if sect['name'] == name]
            if len(dupes) == 1:
                continue
            do_more = True
            i = len(dupes) - 2
            while i > -1:
                dupes[-1]['nodes'][1:1] = dupes[i]['nodes'][1:]
                dupes.pop(i)
                i -= 1

        for sect in sections:
            old_title = sect['nodes'][0].title
            left_spaces = len(old_title) - len(old_title.lstrip())
            right_spaces = len(old_title) - len(old_title.rstrip())
            sect['nodes'][0].title = '%s%s%s' % (left_spaces * ' ',
                                                 sect['name'],
                                                 right_spaces * ' ')
        return do_more

    def sortkey(self, sect):
        if sect['name'] == self.root_header:
            return -1
        if sect['name'] in self.headers_in_order:
            return self.headers_in_order.index(sect['name'])
        pywikibot.warning('Found unknown header: "%s"' % sect['name'])
        return len(self.headers_in_order)

    def check_levels(self, sections, code):
        do_more = False
        mixed_levels = {2, 3} <= {sect['nodes'][0].level for sect in sections}
        if mixed_levels:
            if self.root_header not in map(itemgetter('name'), sections):
                new_header = '== %s ==\n' % self.root_header
                sections.insert(0, {
                    'name': self.root_header,
                    'nodes': self.parser.parse(new_header).nodes
                })
                for sect in sections[1:]:
                    sect['nodes'][0].level = 3
                do_more = True

        return do_more

    def reorganize(self, sections, code):
        pass

    def clean_empty(self, sections, code, do_more):
        to_remove = []
        for sect in sections[:-1]:  # todo
            if sect['name'] == self.root_header:
                continue
            if not ''.join(map(str, sect['nodes'][1:])).strip():
                to_remove.append(sect)
        for sect in to_remove:
            sections.remove(sect)
            do_more = True
        if do_more:
            for sect in sections:
                if sect['name'] == self.root_header:
                    continue
                sect['nodes'][-1] = sect['nodes'][-1].rstrip() + '\n\n'

    def replace(self, match):
        text = match.group()
        code = self.parser.parse(text, skip_style_tags=True)
        sections = []
        for header in code.ifilter_headings():
            name = header.title.strip()
            if name in self.replace_headers:
                name = self.replace_headers[name]
            if name in self.iter_all_headers():
                sections.append({
                    'name': first_upper(name),
                    'nodes': [header],
                })
            else:
                sections[:] = []
        if not sections:
            return text

        do_more = False
        first_index = min(code.nodes.index(sect['nodes'][0])
                          for sect in sections)
        last_index = self.add_contents(sections, code)
        do_more = self.deduplicate(sections, code) or do_more
        do_more = self.check_levels(sections, code) or do_more
        if do_more:
            sections.sort(key=self.sortkey)
        self.reorganize(sections, code)
        self.clean_empty(sections, code, do_more)
        code.nodes[first_index:last_index] = [node for sect in sections
                                              for node in sect['nodes']]
        return str(code)


class StyleFix(Fix):  # todo: split and delete

    key = 'mos'
    order = 2  # after checkwiki

    def apply(self, page, *args):
        # remove empty list items
        page.text = re.sub(r'^\* *\n', '', page.text, flags=re.M)

        # sort categories
        categories = textlib.getCategoryLinks(page.text, site=page.site)
        category_living = pywikibot.Category(page.site, 'Žijící lidé')
        if category_living in categories:
            if any(cat.title(with_ns=False).startswith('Úmrtí ')
                   for cat in categories):
                categories.remove(category_living)
                page.text = textlib.replaceCategoryLinks(
                    page.text, categories, page.site)

        page.text = re.sub(
            r'(\{\{ *(?:%s)[^}]+\}\}\n)\n(\[\[(?:%s))' % (
                '|'.join(map(re.escape, self.site.getmagicwords('defaultsort'))),
                '|'.join(self.site.namespaces[14])),
            r'\1\2', page.text)


class TemplateFix(LazyFix):

    '''Fixes redirected templates'''

    key = 'templates'
    message = 'narovnání šablon'

    def load(self):
        self.cache = {}
        self.defaultsort = self.site.getmagicwords('defaultsort')

    def replacements(self):
        yield (
            r'(?P<before>\{\{\s*)(?P<template>[^<>#{|}]+?)(?P<after>\s*[|}])',
            self.replace,
        )

    def replace(self, match):
        template_name = match.group('template').replace('_', ' ').strip()
        if template_name.startswith(tuple(self.defaultsort)):
            return match.group()

        template_name_norm = first_upper(template_name).partition('<!--')[0]
        if template_name_norm not in self.cache:
            template = pywikibot.Page(self.site, template_name_norm, ns=10)
            try:
                do_replace = template.exists() and template.isRedirectPage()
            except pywikibot.exceptions.InvalidTitle:
                do_replace = False
            except pywikibot.exceptions.InconsistentTitleReceived:
                do_replace = False
            if do_replace:
                target = template.getRedirectTarget()
                self.cache[template_name_norm] = target.title(with_ns=False)
            else:
                self.cache[template_name_norm] = None

        target = self.cache[template_name_norm]
        if not target:
            return match.group()

        if template_name != first_upper(template_name):
            if all(part.islower() for part in target.partition(' ')[0][1:]
                   if part.isalpha()):
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
    exceptions = {  # todo: whitelist
        'inside-tags': TypoRule.exceptions[:],  # fixme: split
    }
    message = 'oprava překlepů'
    order = 1  # after redirects

    def load(self):
        loader = TyposLoader(self.site)
        self.typoRules = loader.loadTypos()
        self.whitelist = loader.loadWhitelist()

    def generator(self):
        return chain.from_iterable(
            map(methodcaller('querySearch'),
                filter(methodcaller('canSearch', self.typoRules))))

    def replacements(self):
        return ((rule.find.pattern, rule.replacements[0])
                for rule in self.typoRules)

    def apply(self, page, summaries=[], callbacks=[]):
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
        if count > 0:  # todo: separate function
            if count > 1:
                max_typos = self.maxsummarytypos
                summary = 'oprava překlepů: %s' % ', '.join(replaced[:max_typos])
                if count > max_typos:
                    if count - max_typos > 1:
                        summary += ' a %s dalších' % (count - max_typos)
                    else:
                        summary += ' a jednoho dalšího'
            else:
                summary = 'oprava překlepu: %s' % replaced[0]

            summaries.append(summary)


lazy_fixes = {fix.key: fix for fix in (
    CategoriesFix, CheckWikiFix, FilesFix, RedirectFix, RedirectsFromFileFix,
    RefSortFix, SectionsFix, TemplateFix, TypoFix)}
all_fixes = {fix.key: fix for fix in (AdataFix, InterwikiFix, StyleFix)}
all_fixes.update(lazy_fixes)

if __name__ == '__main__':
    pywikibot.error('Run wikitext.py instead')
