# -*- coding: utf-8  -*-
import pywikibot

from pywikibot import pagegenerators

from pywikibot.bot import BaseBot

from scripts.typoloader import TyposLoader

class WikitextFixingBot(BaseBot):

    '''
    Class for bots that save wikitext. Applies regular expressions
    provided by other interfaces on the wikitext before cosmetic changes
    are executed. Exposes the whole page object and edit summary.

    Features:
    * -typos - fixing common typos
    ** -maxsummarytypos - how many typo replacements to show
       in edit summary at most?

    Planned:
    * CheckWiki
    * redirects
    * template redirects
    * and more...
    '''

    def __init__(self, site, **kwargs):
        self.availableHooks = {
            'cw': self.initCheckWiki(),
            'redirects': self.loadRedirects,
            'templates': self.loadTemplates,
            'typos': self.initTypos()
        }
        self.availableOptions.update(dict(zip(
            self.availableHooks.keys(),
            [False for i in range(0, len(self.availableHooks))]
        )))
        self.availableOptions.update({
            'maxsummarytypos': 5
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
        self.cwrules = []
        return self.fixCheckWiki

    def fixCheckWiki(self, page, summary):
        replaced = []
        text = page.text
        for rule in self.cwrules:
            text = rule.apply(text, replaced)
        page.text = text
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
                summary += '; oprava překlepů: %s' % ', '.join(replaced[:5])
                if count > max_typos:
                    summary += ' a %s další' % (count - max_typos)
                    if count - max_typos > 1:
                        summary += 'ch'
                    else:
                        summary += 'ho'
            else:
                summary += '; oprava překlepu: %s' % replaced[0]
        return summary

    def loadRedirects(self, **kwargs):
        pass

    def loadTemplates(self, **kwargs):
        pass

    def _save_article(self, page, func, *data, **kwargs):
        for hook in self.hooks:
            kwargs['summary'] = hook(page, kwargs.pop('summary'))
        return super(WikitextFixingBot, self)._save_page(page, func, *data, **kwargs)
