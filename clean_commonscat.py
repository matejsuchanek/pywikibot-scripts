#!/usr/bin/python
import itertools
import re

import pywikibot

from pywikibot import i18n, pagegenerators, textlib
from pywikibot.exceptions import UnknownExtensionError

from .deferred import DeferredCallbacksBot
from .wikidata import WikidataEntityBot
from .wikitext import WikitextFixingBot


save_summary = {
    'cs': 'odstranění odkazu na neexistující kategorii na Commons',
    'en': 'removed link to a non-existing Commons category',
}


class CommonscatCleaningBot(WikitextFixingBot, WikidataEntityBot, DeferredCallbacksBot):

    def __init__(self, **kwargs):
        self.available_options.update({
            'createnew': False,
            'noclean': False,
            'noimport': False,
        })
        super().__init__(**kwargs)
        self.commons = pywikibot.Site('commons', 'commons')

    def setup(self):
        super().setup()
        self.cacheSources()
        # todo: l10n etc.
        templates = itertools.chain(
            map(re.escape, self.site.getmagicwords('defaultsort')),
            ('[Pp]ahýl', '[Pp]osloupnost', '[Aa]utoritní data', '[Pp]ortály'))
        templates = '|'.join(templates)
        ns = '|'.join(self.site.namespaces[14])
        self.empty_sectionR = re.compile(
            r'\s*\n==+ *Externí odkazy *==+ *\n\s*'
            r'^(?:==|\{\{(?:{templates})|\[\[(?:{ns}):)'
            .format(templates=templates, ns=ns),
            flags=re.M)

    def treat_page(self):  # todo: treat_page_and_item
        page = self.current_page
        item = page.data_item()
        if 'P373' in item.claims:
            self.addCallback(page.touch)
            pywikibot.info('Already has a category on Commons')
            return

        cat_name = None
        has_param = False
        for template, fielddict in page.raw_extracted_templates:
            # todo: l10n
            if template.lower() in ['commonscat', 'commons category']:
                cat_name = page.title(with_ns=False)
                value = fielddict.get('1', '').strip()
                if value:
                    has_param = True
                    cat_name = value
                break

        if cat_name is None:
            pywikibot.warning('Template not found')
            return

        commons_cat = pywikibot.Category(self.commons, cat_name)
        exists = commons_cat.exists()
        if not exists and not commons_cat.isEmptyCategory():
            if self.opt['createnew'] is not True:
                pywikibot.warning(f'{commons_cat.title()} is not empty')
                return

            exists = self.doWithCallback(
                self.userPut, commons_cat, '', '{{Uncategorized}}',
                asynchronous=False)

        if not exists:
            if self.opt['noclean'] is True:
                pywikibot.info(
                    "Category doesn't exist on Commons, cleanup restricted")
                return
            regex = r'(?:\n?|^)(?:\* *)?\{\{ *[Cc]ommons(?:cat|[_ ]?category)'
            if has_param:
                regex += r' *\| *' + re.escape(cat_name)
            regex += r' *\}\}'
            page_replaced_text = re.sub(
                regex, '', page.text, flags=re.M, count=1)
            if page_replaced_text != page.text:
                page_replaced_text = self.empty_sectionR.sub(
                    r'\n\n\1', page_replaced_text, count=1)

            # fixme
            self.doWithCallback(
                self.put_current, page_replaced_text,
                summary=i18n.translate(page.site, save_summary))
        else:
            if self.opt['noimport'] is True:
                pywikibot.info('Category exists on Commons, import restricted')
                return
            claim = pywikibot.Claim(self.repo, 'P373')
            claim.setTarget(cat_name)
            pywikibot.info('Category missing on Wikidata')
            self.user_add_claim(item, claim, page.site, asynchronous=True)
            self.addCallback(page.touch)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    for arg in genFactory.handle_args(local_args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator(preload=True)
    site = pywikibot.Site()
    if not generator:
        try:
            category = site.page_from_repository('Q11925744')
        except (NotImplementedError, UnknownExtensionError) as e:
            pywikibot.error(e)
            return

        if not category:
            pywikibot.info(f"{site} doesn't have an appropriate category")
            return

        generator = itertools.chain(
            category.articles(namespaces=0),
            category.subcategories())

    generator = pagegenerators.WikibaseItemFilterPageGenerator(generator)
    bot = CommonscatCleaningBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
