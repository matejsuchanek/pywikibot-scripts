# -*- coding: utf-8  -*-
import pywikibot
import re

from pywikibot import pagegenerators
#from pywikibot import textlib

from pywikibot.bot import SingleSiteBot
from pywikibot.tools.formatter import color_format

from scripts.checkwiki_errors import deduplicate
from scripts.typoloader import TyposLoader

class WikitextFixingBot(SingleSiteBot):

    '''
    Class for bots that save wikitext. Applies regular expressions
    provided by other interfaces on the wikitext before cosmetic changes
    are executed. Exposes the whole page object and edit summary.

    Features:
    * -typos - fixing common typos
    ** -maxsummarytypos - how many typo replacements to show
       in edit summary at most?
    * -cw - fixes Check Wikipedia errors
    ** -maxsummarycw
    * -redirects - fixes common redirects
    ** -onlypiped - only fix links which include "|"
    * -templates - fixes redirected templates
    * -adata - adds authority control to articles
    ** -minprops - minimal amount of properties the item
       should have to include authority control

    Planned:
    * commonscat
    * manual of style
    * interwiki
    * and more...
    '''

    FILE_LINK_REGEX = r'\[\[\s*(?:%s)\s*:\s*[^]|[]+(?:\|(?:[^]|[]|\[\[[^]]+\]\])+)+\]\]'

    def __init__(self, site, **kwargs):
        pywikibot.output("Please help fix [[phab:T148959]] for better wikisyntax parsing")
        self.availableHooks = {
            'adata': self.initAdata(),
            #'commonscat': self.loadCommonscat,
            'cw': self.initCheckWiki(),
            'files': self.loadFiles,
            #'interwiki': self.loadInterwiki,
            'redirects': self.initRedirects(),
            'templates': self.loadTemplates,
            'typos': self.initTypos()
        }
        do_all = kwargs.pop('all', False) is True
        self.availableOptions.update(dict(zip(
            self.availableHooks.keys(),
            [do_all for i in range(0, len(self.availableHooks))]
        )))
        super(WikitextFixingBot, self).__init__(site, **kwargs)
        self.initHooks(**kwargs)

    def initHooks(self, **kwargs):
        self.hooks = []
        for opt, callback in self.availableHooks.items():
            if self.getOption(opt) is True:
                hook = callback(**kwargs)
                self.hooks.append(hook)

    def fix_wikitext(self, page, *data, **kwargs):
        summaries = [kwargs['summary']]
        callbacks = []
        for hook in self.hooks:
            callback = hook(page, summaries)
            if callable(callback):
                callbacks.append(callback)

        kwargs['summary'] = '; '.join(summaries)
        kwargs['callback'] = lambda _, exc: [cb() for cb in callbacks if not exc]
        page.save(*data, **kwargs)

    def initCheckWiki(self):
        self.availableOptions.update({
            'maxsummarycw': 5
        })
        return self.loadCheckWiki

    def loadCheckWiki(self, **kwargs):
        from scripts.checkwiki import CheckWiki
        self.checkwiki = CheckWiki(self.site) #**kwargs
        return self.fixCheckWiki

    def fixCheckWiki(self, page, summaries):
        replaced = []
        fixed = []
        page.text = self.checkwiki.applyErrors(page.text, page, replaced, fixed)
        if len(replaced) > 0: # todo: maxsummarycw
            summaries.append(u'[[WP:WCW|CheckWiki]]: %s' % ', '.join(replaced))
            return lambda: self.checkwiki.markFixed(fixed, page)

    def initTypos(self):
        self.availableOptions.update({
            'maxsummarytypos': 5,
            'typospage': None,
            'whitelistpage': None,
        })
        return self.loadTypos

    def loadTypos(self, **kwargs):
        kwargs['allrules'] = False
        loader = TyposLoader(self.site, **kwargs)
        self.typoRules = loader.loadTypos()
        self.whitelist = loader.loadWhitelist()
        return self.fixTypos

    def fixTypos(self, page, summaries):
        if page.namespace() != 0: # todo: generalize
            return
        if page.title() in self.whitelist:
            return
        text = page.text
        replaced = []
        for rule in self.typoRules:
            text = rule.apply(text, replaced)
        page.text = text
        count = len(replaced)
        if count > 0: # todo: separate function
            if count > 1:
                max_typos = self.getOption('maxsummarytypos')
                summary = u'oprava překlepů: %s' % ', '.join(replaced[:5])
                if count > max_typos:
                    if count - max_typos > 1:
                        summary += u' a %s dalších' % (count - max_typos)
                    else:
                        summary += u' a jednoho dalšího'
            else:
                summary = u'oprava překlepu: %s' % replaced[0]

            summaries.append(summary)

    def initRedirects(self, **kwargs):
        self.availableOptions.update({
            'onlypiped': False
        })
        return self.loadRedirects

    def loadRedirects(self, **kwargs):
        self.redirects = []
        self.redirect_cache = {}
        page = pywikibot.Page(self.site, u'Wikipedista:PastoriBot/narovnaná_přesměrování')
        pywikibot.output('Loading redirects')
        text = page.get()
        _, __, text = text.partition('{{SHORTTOC}}')
        for line in text.splitlines():
            if line.strip() == '':
                continue
            if line.startswith('=='):
                continue
            self.redirects.append(line.strip())

        pywikibot.output('%s redirects loaded' % len(self.redirects))
        return self.fixRedirects

    def fixRedirects(self, page, summaries):

        def replace(match):
            split = match.group(1).split('|')
            if len(split) > 2:
                return match.group()
            if len(split) == 1 and\
               (self.getOption('onlypiped') or self.getOption('always')):
                return match.group()
            if split[0].startswith('Kategorie:'):
                return match.group()

            page_title = split[0].replace('_', ' ').strip()
            if page_title in self.redirects:
                if page_title not in self.redirect_cache:
                    link_page = pywikibot.Page(self.site, page_title)
                    if not link_page.exists():
                        pywikibot.warning('%s does not exist' % link_page.title())
                        self.redirects.remove(page_title)
                        return match.group()
                    if not link_page.isRedirectPage():
                        pywikibot.warning('%s is not a redirect' % link_page.title())
                        self.redirects.remove(page_title)
                        return match.group()

                    target = link_page.getRedirectTarget()
                    title = target.title()
                    if page_title[0].islower():
                        self.redirect_cache[page_title] = title[0].lower() + title[1:]
                    else:
                        self.redirect_cache[page_title] = title

                if len(split) == 1:
                    options = []
                    options_map = [
                        '[[%s]]' % page_title,
                        '[[%s]]' % self.redirect_cache[page_title],
                        '[[%s|%s]]' % (self.redirect_cache[page_title], page_title)
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
                    pywikibot.output(
                        pre +
                        color_format(u'{lightred}{0}{default}', match.group()) +
                        post)

                    choice = pywikibot.input_choice('Replace this link?',
                                                    options, default='1')
                    if choice == 'n':
                        self.availableOptions.update({
                            'onlypiped': True
                        })
                        return match.group()
                    else:
                        return options_map[int(choice)-1]

                return '[[%s|%s]]' % (self.redirect_cache[page_title], split[-1])

            return match.group()

        pattern = re.compile(r'\[\[([^][]+)\]\]')
        text = pattern.sub(replace, page.text)
        if page.text != text:
            summaries.append(u'narovnání přesměrování')
            page.text = text

    def loadTemplates(self, **kwargs):
        self.template_cache = {}
        return self.fixTemplates

    def fixTemplates(self, page, summaries):

        def replace(match):
            template_name = match.group('template').replace('_', ' ').strip()
            if template_name.startswith('DEFAULTSORT:'):
                return match.group()

            template_name_norm = template_name[0].upper() + template_name[1:]
            if template_name_norm not in self.template_cache:
                template = pywikibot.Page(self.site, template_name_norm, ns=10)
                if template.exists() and template.isRedirectPage():
                    target = template.getRedirectTarget()
                    self.template_cache[template_name_norm] = target.title(withNamespace=False)
                else:
                    self.template_cache[template_name_norm] = None

            target = self.template_cache[template_name_norm]
            if not target:
                return match.group()

            if template_name[0].islower():
                target = target[0].lower() + target[1:]

            return match.group('before') + target + match.group('after')

        pattern = re.compile(r'(?P<before>\{\{\s*)(?P<template>[^#{|}]+?)(?P<after>\s*[|}])')
        text = pattern.sub(replace, page.text)
        if page.text != text:
            summaries.append(u'narovnání šablon')
            page.text = text

    def initAdata(self):
        self.availableOptions.update({
            'minprops': 2
        })
        return self.loadAdata

    def loadAdata(self, **kwargs):
        self.props = set(['P213', 'P214', 'P227', 'P244', 'P245', 'P496', 'P691', 'P1051'])
        self.repo = self.site.data_repository()
        return self.addAdata

    def addAdata(self, page, summaries):
        text = page.text
        adata = u'{{Autoritní data}}'
        if adata.lower() in text.lower():
            return

        try:
            item = page.data_item()
        except pywikibot.NoPage:
            return

        item.get()
        human_item = pywikibot.ItemPage(self.repo, 'Q5')
        if not any(st.target_equals(human_item) for st in item.claims.get('P31', [])):
            return

        if len(self.props & set(item.claims.keys())) < self.getOption('minprops'):
            return

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

    def loadCommonscat(self, **kwargs):
        return self.addCommonscat

    def addCommonscat(self, page, summaries):
        text = page.text

    def loadFiles(self, **kwargs):
##        self.file_regex = re.compile(
##            textlib.FILE_LINK_REGEX % '|'.join(self.site.namespaces[6]),
##            re.VERBOSE)
        self.file_regex = re.compile(
            self.FILE_LINK_REGEX % '|'.join(self.site.namespaces[6]))
        return self.fixFiles

    def fixFiles(self, page, summaries):
        magic_map = {
            'border': 'okraj',
            'center': u'střed',
            'frame': u'rám',
            'framed': u'rám',
            'frameless': u'bezrámu',
            'left': 'vlevo',
            'none': u'žádné',
            'right': 'vpravo',
            'thumb': u'náhled',
            'thumbnail': u'náhled',
        }
        def handleFile(match):
            if self.file_regex.search(match.group()[2:-2]):
                return match.group() # todo
##
##            if match.group().count('[[') != match.group().count(']]'):
##                return match.group()

            split = [x.strip() for x in match.group()[2:-2].split('|')]

            split[0] = split[0].replace('_', ' ').strip()
            i = 1
            while i < len(split):
                while split[i].count('[[') != split[i].count(']]'):
                    split[i] += '|' + split[i+1]
                    del split[i+1]

                if split[i] in magic_map:
                    split[i] = magic_map[split[i]]

                elif split[i].startswith('alt='):
                    pass
                elif split[i].startswith('jazyk=') or split[i].startswith('lang='):
                    pass
                elif split[i].startswith('link='):
                    pass
                elif split[i].startswith('upright'):
                    pass
                elif re.match(r'\d+px$', split[i][0]):
                    pass
                else:
                    if split[i].endswith('.'):
                        pass

                i += 1

            deduplicate(split)

            return '[[' + '|'.join(split) + ']]'

        new_text = self.file_regex.sub(handleFile, page.text)
        if new_text != page.text:
            page.text = new_text
            #summaries.append()

##    def loadInterwiki(self, **kwargs):
##        return self.fixInterWiki
##
##    def fixInterwiki(self, page, summaries):
##        iwlinks = page.interwiki()
##        if len(iwlinks) < 1:
##            return
##        try:
##            item = pywikibot.ItemPage.fromPage(page)
##            sitelinks = item.get().sitelinks
##            #for site in iwlinks:
##        except pywikibot.NoPage:
##            return
