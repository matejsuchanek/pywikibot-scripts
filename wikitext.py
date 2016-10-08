# -*- coding: utf-8  -*-
import pywikibot
import re

from pywikibot import pagegenerators
from pywikibot import textlib

from pywikibot.bot import SingleSiteBot
from pywikibot.tools.formatter import color_format

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
    * -redirects - fixes commons redirects
    * -templates - fixes redirected templates

    Planned:
    * interwiki
    * and more...
    '''

    def __init__(self, site, **kwargs):
        self.availableHooks = {
            'cw': self.initCheckWiki(),
            #'interwiki': self.loadInterwiki,
            'redirects': self.initRedirects(),
            'templates': self.loadTemplates,
            'typos': self.initTypos()
        }
        do_all = kwargs.pop('all', False)
        self.availableOptions.update(dict(zip(
            self.availableHooks.keys(),
            [do_all for i in range(0, len(self.availableHooks))]
        )))
        super(WikitextFixingBot, self).__init__(site, **kwargs)
        self.hooks = []
        self.initHooks(**kwargs)

    def initHooks(self, **kwargs):
        for opt, callback in self.availableHooks.items():
            if self.getOption(opt) is True:
                hook = callback(**kwargs)
                self.hooks.append(hook)

    def fix_wikitext(self, page, *data, **kwargs):
        for hook in self.hooks:
            kwargs['summary'] = hook(page, kwargs.pop('summary'))
        return page.save(*data, **kwargs)

    def initCheckWiki(self):
        self.availableOptions.update({
            'maxsummarycw': 5
        })
        return self.loadCheckWiki

    def loadCheckWiki(self, **kwargs):
        from scripts.checkwiki import CheckWiki
        self.checkwiki = CheckWiki(self.site)
        return self.fixCheckWiki

    def fixCheckWiki(self, page, summary):
        replaced = []
        page.text = self.checkwiki.applyErrors(page.text, page, replaced)
        if len(replaced) > 0: # todo: maxsummarycw
            summary += u'; [[WP:WCW|CheckWiki]]: %s' % ', '.join(replaced)
        return summary

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

    def fixTypos(self, page, summary):
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
                summary += u'; oprava překlepů: %s' % ', '.join(replaced[:5])
                if count > max_typos:
                    summary += u' a %s další' % (count - max_typos)
                    if count - max_typos > 1:
                        summary += 'ch'
                    else:
                        summary += 'ho'
            else:
                summary += u'; oprava překlepu: %s' % replaced[0]
        return summary

    def initRedirects(self, **kwargs):
        self.availableOptions.update({
            'onlypiped': False
        })
        return self.loadRedirects

    def loadRedirects(self, **kwargs):
        self.redirects = []
        self.redirect_cache = {}
        site = pywikibot.Site('cs', 'wikipedia')
        page = pywikibot.Page(site, u'Wikipedista:PastoriBot/narovnaná_přesměrování')
        pywikibot.output('Loading redirects')
        text = page.get()
        text = text[text.index('{{SHORTTOC}}') + len('{{SHORTTOC}}'):]
        for line in text.splitlines():
            if line.strip() == '':
                continue
            if line.startswith('=='):
                continue
            self.redirects.append(line.strip())

        pywikibot.output('%s redirects loaded' % len(self.redirects))
        return self.fixRedirects

    def fixRedirects(self, page, summary):

        def replace(match):
            split = match.group(1).split('|')
            if len(split) > 2:
                return match.group()
            if len(split) == 1 and self.getOption('onlypiped'):
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
                    if page_title[0] == page_title[0].lower():
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

        pattern = re.compile(r'\[\[([^[\]]+)\]\]')
        text = pattern.sub(replace, page.text)
        if page.text != text:
            summary += u'; narovnání přesměrování'
            page.text = text
        return summary

    def loadTemplates(self, **kwargs):
        self.template_cache = {}
        return self.fixTemplates

    def fixTemplates(self, page, summary):

        def replace(match):
            template_name = match.group('template').replace('_', ' ').strip()
            template_name = template_name[0].upper() + template_name[1:]
            if template_name not in self.template_cache:
                template = pywikibot.Page(self.site, template_name, ns=10)
                if template.exists() and template.isRedirectPage():
                    target = template.getRedirectTarget()
                    self.template_cache[template_name] = target.title(withNamespace=False)
                else:
                    self.template_cache[template_name] = None

            target = self.template_cache[template_name]
            if not target:
                return match.group()

            return match.expand('\g<before>%s\g<after>' % target)

        pattern = re.compile(r'(?P<before>\{\{\s*)(?P<template>[^{|}]+?)(?P<after>\s*[|}])')
        text = pattern.sub(replace, page.text)
        if page.text != text:
            summary += u'; narovnání šablon'
            page.text = text
        return summary

##    def loadInterwiki(self, **kwargs):
##        return self.fixInterWiki
##
##    def fixInterwiki(self, page, summary):
##        iwlinks = page.interwiki()
##        if len(iwlinks) < 1:
##            return
##        try:
##            item = pywikibot.ItemPage.fromPage(page)
##            sitelinks = item.get().sitelinks
##            #for site in iwlinks:
##        except pywikibot.NoPage:
##            return
