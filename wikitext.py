# -*- coding: utf-8 -*-
import pywikibot
import re

from pywikibot import pagegenerators

from pywikibot.bot import SingleSiteBot, ExistingPageBot

#from scripts.myscripts.checkwiki_errors import deduplicate
from scripts.myscripts.custome_fixes import all_fixes

class WikitextFixingBot(SingleSiteBot, ExistingPageBot):

    '''
    Class for bots that save wikitext. It uses all demanded fixes from
    custome_fixes.py and applies them before cosmetic changes are
    executed.

    You can enable each fix by using its name as a command line argument
    or all fixes using -all (then, each used fix is excluded).
    '''

    def __init__(self, **kwargs):
        do_all = kwargs.pop('all', False) is True
        self.fixes = []
        for fix, cls in all_fixes.items():
            in_args = fix in kwargs
            demand = do_all ^ in_args
            #((in_args and not do_all) or (do_all and not (in_args and bool(kwargs[fix]))))
            if in_args:
                kwargs.pop(fix)
            if demand:
                options = {}
                for opt in cls.options.keys():
                    if opt in kwargs:
                        options[opt] = kwargs.pop(opt)
                self.fixes.append(cls(**options))

        self.fixes.sort(key=lambda fix: fix.order)

        super(WikitextFixingBot, self).__init__(**kwargs)
        for fix in self.fixes:
            fix.site = self.site

    def init_page(self, page):
        super(WikitextFixingBot, self).init_page(page)
        page.get()

    def treat_page(self):
        summaries = []
        page = self.current_page
        old_text = page.text
        callbacks = self.applyFixes(page, summaries)
        if len(summaries) < 1:
            pywikibot.output('No replacements worth saving')
            return
        pywikibot.showDiff(old_text, page.text)
        callback = lambda _, exc: [cb() for cb in callbacks if not exc]
        self._save_page(page, page.save, callback=callback,
                        summary='; '.join(summaries))

    def applyFixes(self, page, summaries=[]):
        callbacks = []
        for fix in self.fixes:
            fix.apply(page, summaries, callbacks)
        return callbacks

    def fix_wikitext(self, page, *data, **kwargs):
        summaries = [kwargs['summary']]
        callbacks = self.applyFixes(page, summaries)

        kwargs['summary'] = '; '.join(summaries)
        kwargs['callback'] = lambda _, exc: [cb() for cb in callbacks
                                             if not exc]
        page.save(*data, **kwargs)

def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    if generator:
        bot = WikitextFixingBot(generator=generator, **options)
        bot.run()
    else:
        pass # todo: output

if __name__ == "__main__":
    main()
