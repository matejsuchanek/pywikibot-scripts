# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re

from pywikibot import i18n, pagegenerators, textlib

from scripts.myscripts.deferred import DeferredCallbacksBot
from scripts.myscripts.wikidata import WikidataEntityBot
from scripts.myscripts.wikitext import WikitextFixingBot

save_summary = {
    'cs': 'odstranění odkazu na neexistující kategorii na Commons',
    'en': 'removed link to a non-existing Commons category',
}

class CommonscatCleaningBot(WikitextFixingBot, WikidataEntityBot, DeferredCallbacksBot):

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'createnew': False,
            'noclean': False,
            'noimport': False,
        })
        super(CommonscatCleaningBot, self).__init__(**kwargs)
        self.commons = pywikibot.Site('commons', 'commons')

    def treat_page(self):
        page = self.current_page
        item = page.data_item()
        item.get()
        if 'P373' in item.claims.keys():
            self.addCallback(page.touch, botflag=True)
            pywikibot.output('Already has a category on Commons')
            return

        cat_name = None
        has_param = False
        for template, fielddict in textlib.extract_templates_and_params(
            page.text, remove_disabled_parts=True, strip=True):
            if template.lower() in ['commonscat', 'commons category']:
                cat_name = page.title(withNamespace=False)
                if '1' in fielddict:
                    value = fielddict['1'].strip()
                    if value:
                        has_param = True
                        cat_name = value
                break

        if cat_name is None:
            pywikibot.warning('Template not found')
            return

        commons_cat = pywikibot.Category(self.commons, cat_name)
        exists = commons_cat.exists()
        if not exists:
            if not commons_cat.isEmptyCategory():
                if self.getOption('createnew') is True:
                    commons_cat.text = '{{Uncategorized}}'
                    exists = self.doWithCallback(
                        self._save_page, commons_cat, commons_cat.save)
                else:
                    pywikibot.warning('%s is not empty' % commons_cat.title())
                    return

        if not exists:
            if self.getOption('noclean') is True:
                pywikibot.output('Category doesn\'t exist on Commons, '
                                 'cleanup restricted')
                return
            regex = r'(?:[\n\r]?|^)(?:\* *)?\{\{ *[Cc]ommons(?:cat|[_ ]?category) *'
            if has_param is True:
                regex += r'\| *' + re.escape(cat_name)
            regex += r'[^\}]*\}\}'
            page_replaced_text = re.sub(regex, '', page.text, flags=re.M | re.U)
            if page_replaced_text == page.text:
                pywikibot.warning('No replacement done')
            else:
                templates = (
                    '|'.join(map(re.escape, self.site.getmagicwords('defaultsort'))),
                    '[Pp]ahýl', '[Pp]osloupnost', '[Aa]utoritní data', '[Pp]ortály')
                page_replaced_text = re.sub(
                    r'\s*==+ ?Externí odkazy ?==+ *$\s*^(==|\{\{'
                    '(?:' + '|'.join(templates) + ')'
                    '|\[\[(?:%s):)' % '|'.join(self.site.namespaces[14]),
                    r'\n\n\1',
                    page_replaced_text,
                    flags=re.M | re.U)
                if not self.getOption('always'):
                    pywikibot.showDiff(page.text, page_replaced_text)
                page.text = page_replaced_text
                self.doWithCallback(
                    self._save_page, page, self.fix_wikitext, page,
                    summary=i18n.translate(self.site, save_summary))
        else:
            if self.getOption('noimport') is True:
                pywikibot.output('Category exists on Commons, import restricted')
                return
            claim = pywikibot.Claim(self.repo, 'P373')
            claim.setTarget(cat_name)
            pywikibot.output('Importing P373 to %s' % (page.title(), item.getID()))
            if self._save_page(item, self._save_entity, item.addClaim, claim):
                old = self.getOption('always')
                self.options['always'] = True
                ref = self.getSource()
                self._save_page(item, self._save_entity, claim.addSource, ref)
                self.options['always'] = old
                self.addCallback(page.touch, botflag=True)

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
    if not generator:
        site = pywikibot.Site()
        repo = site.data_repository()
        item = pywikibot.ItemPage(repo, 'Q11925744')
        try:
            title = item.getSitelink(site)
        except pywikibot.NoPage:
            pywikibot.output('%r doesn\'t have an appropriate category' % site)
            return

        category = pywikibot.Category(site, title)
        gen_articles = category.articles(namespaces=0)
        gen_subcats = category.subcategories()
        gen_combined = pagegenerators.CombinedPageGenerator([gen_articles,
                                                             gen_subcats])
        generator = pagegenerators.WikibaseItemFilterPageGenerator(gen_combined)

    bot = CommonscatCleaningBot(generator=generator, site=site, **options)
    bot.run()

if __name__ == "__main__":
    main()
