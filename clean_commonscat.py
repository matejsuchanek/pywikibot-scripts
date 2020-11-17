# -*- coding: utf-8 -*-
import itertools
import re

import pywikibot

from pywikibot import i18n, pagegenerators, textlib
from pywikibot.exceptions import UnknownExtension

from .deferred import DeferredCallbacksBot
from .wikidata import WikidataEntityBot
from .wikitext import WikitextFixingBot


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
        super().__init__(**kwargs)
        self.commons = pywikibot.Site('commons', 'commons')

    def setup(self):
        super().setup()
        self.cacheSources()

    def treat_page(self):  # todo: treat_page_and_item
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
            # todo: l10n
            if template.lower() in ['commonscat', 'commons category']:
                cat_name = page.title(with_ns=False)
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
                    exists = self.doWithCallback(
                        self.userPut, commons_cat, '', '{{Uncategorized}}',
                        asynchronous=False)
                else:
                    pywikibot.warning('%s is not empty' % commons_cat.title())
                    return

        if not exists:
            if self.getOption('noclean') is True:
                pywikibot.output('Category doesn\'t exist on Commons, '
                                 'cleanup restricted')
                return
            regex = r'(?:[\n\r]?|^)(?:\* *)?\{\{ *[Cc]ommons(?:cat|[_ ]?category) *'
            if has_param:
                regex += r'\| *' + re.escape(cat_name)
            regex += r'[^\}]*\}\}'
            page_replaced_text = re.sub(
                regex, '', page.text, flags=re.M, count=1)
            if page_replaced_text != page.text:
                # todo: l10n etc.
                templates = (
                    '|'.join(map(re.escape, page.site.getmagicwords('defaultsort'))),
                    '[Pp]ahýl', '[Pp]osloupnost', '[Aa]utoritní data', '[Pp]ortály')
                page_replaced_text = re.sub(
                    r'\s*==+ ?Externí odkazy ?==+ *$\s*^(==|\{\{'
                    '(?:' + '|'.join(templates) + ')'
                    r'|\[\[(?:%s):)' % '|'.join(page.site.namespaces[14]),
                    r'\n\n\1',
                    page_replaced_text, flags=re.M, count=1)

            # fixme
            self.doWithCallback(
                self.put_current, page_replaced_text,
                summary=i18n.translate(page.site, save_summary))
        else:
            if self.getOption('noimport') is True:
                pywikibot.output('Category exists on Commons, import restricted')
                return
            claim = pywikibot.Claim(self.repo, 'P373')
            claim.setTarget(cat_name)
            pywikibot.output('Category missing on Wikidata')
            self.user_add_claim(item, claim, page.site, asynchronous=True)
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

    generator = genFactory.getCombinedGenerator(preload=True)
    site = pywikibot.Site()
    if not generator:
        try:
            category = site.page_from_repository('Q11925744')
        except (NotImplementedError, UnknownExtension) as e:
            pywikibot.error(e)
            return

        if not category:
            pywikibot.output("%s doesn't have an appropriate category" % site)
            return

        gen_combined = itertools.chain(
            category.articles(namespaces=0), category.subcategories())
        generator = pagegenerators.WikibaseItemFilterPageGenerator(gen_combined)

    bot = CommonscatCleaningBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
