# -*- coding: utf-8  -*-
import pywikibot

from pywikibot import pagegenerators
from pywikibot import textlib

from pywikibot.bot import SingleSiteBot

from scripts.checkwiki import CheckWiki
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
    ** -cw - fixes Check Wikipedia errors

    Planned:
    * redirects
    * template redirects
    * and more...
    '''

    def __init__(self, site, **kwargs):
        self.availableHooks = {
            'cw': self.initCheckWiki(),
            #'interwiki': self.loadInterwiki,
            'redirects': self.loadRedirects,
            'templates': self.loadTemplates,
            'typos': self.initTypos()
        }
        do_all = kwargs.pop('all', False)
        self.availableOptions.update(dict(zip(
            self.availableHooks.keys(),
            [do_all for i in range(0, len(self.availableHooks))]
        )))
        self.availableOptions.update({
            'maxsummarycw': 5,
            'maxsummarytypos': 5,
        })
        super(WikitextFixingBot, self).__init__(site, **kwargs)
        self.hooks = []
        self.initHooks(**kwargs)

    def initHooks(self, **kwargs):
        for opt, callback in self.availableHooks.items():
            if self.getOption(opt) is True:
                hook = callback(**kwargs)
                self.hooks.append(hook)

    def initCheckWiki(self):
        #self.availableOptions.update({})
        return self.loadCheckWiki

    def loadCheckWiki(self, **kwargs):
        return self.fixCheckWiki

    def fixCheckWiki(self, page, summary):
        replaced = []
        cw = CheckWiki(self.site)
        page.text = cw.applyErrors(page.text, replaced)
        if len(replaced) > 0: # todo: maxsummarycw
            summary += u'; [[WP:WCW|CheckWiki]]: %s' % ', '.join(replaced)
        return summary

    def initTypos(self):
        self.availableOptions.update({
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
        if page.namespace() != 0:
            return
        if page.title() in self.whitelist:
            return
        text = page.text
        replaced = []
        for rule in self.typoRules:
            text = rule.apply(text, replaced)
        page.text = text
        count = len(replaced)
        if count > 0:
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

    def loadRedirects(self, **kwargs):
        pass

    def loadTemplates(self, **kwargs):
        pass

##    def loadInterwiki(self, **kwargs):
##        return self.fixInterWiki

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

    def fix_wikitext(self, page, *data, **kwargs):
        for hook in self.hooks:
            kwargs['summary'] = hook(page, kwargs.pop('summary'))
        return page.save(*data, **kwargs)
