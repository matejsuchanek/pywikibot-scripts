# -*- coding: utf-8  -*-
import pywikibot
import re

from pywikibot import pagegenerators
from pywikibot import textlib

from scripts.deferred import DeferredCallbacksBot
from scripts.wikidata import WikidataEntityBot
from scripts.wikitext import WikitextFixingBot

class CommonscatCleaningBot(WikitextFixingBot, WikidataEntityBot, DeferredCallbacksBot):

    def __init__(self, site, **kwargs):
        self.availableOptions.update({
            'createnew': False,
        })
        super(CommonscatCleaningBot, self).__init__(site, **kwargs)
        self.commons = pywikibot.Site('commons', 'commons')

    def init_page(self, page):
        page.get()

    def treat_page(self):
        page = self.current_page
        item = pywikibot.ItemPage.fromPage(page)
        item.get()
        if 'P373' in item.claims.keys():
            self.addCallback(page.touch, botflag=True)
            pywikibot.output("Already has a category on Commons")
            return

        cat_name = None
        has_param = False
        for template, fielddict in textlib.extract_templates_and_params(
            page.text, remove_disabled_parts=True, strip=True):
            if template.lower() in ['commonscat', 'commons category']:
                cat_name = page.title(withNamespace=False)
                for key, value in fielddict.items():
                    if key == '1':
                        cat_name = value.strip()
                        if cat_name != '':
                            has_param = True
                        else:
                            cat_name = page.title(withNamespace=False)
                        break

        if cat_name is None:
            pywikibot.warning("Template not found")
            return

        commons_cat = pywikibot.Category(self.commons, cat_name)
        exists = commons_cat.exists()
        if not exists:
            if not commons_cat.isEmptyCategory():
                if self.getOption('createnew') is True:
                    commons_cat.text = u'{{Uncategorized}}'
                    exists = self.doWithCallback(
                        self._save_page, commons_cat, commons_cat.save,
                        summary=u'odstranění odkazu na neexistující kategorii na Commons')
                else:
                    pywikibot.warning(u'%s is not empty' % commons_cat.title())
                    return

        if not exists:
            regex = r'(?:[\n\r]?|^)(?:\* *)?\{\{ *[Cc]ommons(?:cat|[_ ]?category) *'
            if has_param is True:
                regex += r'\| *' + re.escape(cat_name).replace('\ ', '[_ ]')
            regex += r'[^\}]*\}\}'
            page_replaced_text = re.sub(regex, '', page.text, flags=re.M | re.U)
            if page_replaced_text == page.text:
                pywikibot.warning('No replacement done')
            else:
                templates = ('DEFAULTSORT:', u'[Pp]ahýl', '[Pp]osloupnost', u'[Aa]utoritní data', u'[Pp]ortály')
                el = u'Externí odkazy'
                page_replaced_text = re.sub(r'[\n\r]+==+\ ?' + el + r'\ ?==+\ *[\n\r]+(==|\{\{(?:' + '|'.join(templates) + r')|\[\[Kategorie:)',
                                            r'\n\n\1', page_replaced_text)
                if not self.getOption('always'):
                    pywikibot.showDiff(page.text, page_replaced_text)
                page.text = page_replaced_text
                self.doWithCallback(
                    self._save_page, page, self._save_article, page,
                    summary=u'odstranění odkazu na neexistující kategorii na Commons')
        else:
            claim = pywikibot.Claim(self.repo, 'P373')
            claim.setTarget(cat_name)
            pywikibot.output(u'Importing P373 from %s to %s' % (page.title(), item.getID()))
            ok = self._save_page(item, self._save_entity, item.addClaim, claim)
            if ok is True:
                old = self.getOption('always')
                self.options['always'] = True
                ref = self.getSource()
                self._save_page(item, self._save_entity, claim.addSource, ref)
                self.options['always'] = old
                self.addCallback(page.touch, botflag=True)

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    site = pywikibot.Site()
    repo = site.data_repository()
    item = pywikibot.ItemPage(repo, 'Q11925744')
    try:
        title = item.getSitelink(site)
    except pywikibot.NoPage:
        pywikibot.output("%s doesn't have an appropriate category" % site)
        return

    category = pywikibot.Category(site, title)
    gen_articles = category.articles(namespaces=0)
    gen_subcats = category.subcategories()
    gen_combined = pagegenerators.CombinedPageGenerator([gen_articles, gen_subcats])
    gen_filtered = pagegenerators.WikibaseItemFilterPageGenerator(gen_combined)

    options['generator'] = gen_filtered

    bot = CommonscatCleaningBot(site, **options)
    bot.run()

if __name__ == "__main__":
    main()
