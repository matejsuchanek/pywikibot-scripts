#!/usr/bin/python
import pywikibot

from pywikibot.pagegenerators import (
    page_with_property_generator,
    GeneratorFactory,
    NamespaceFilterPageGenerator,
)
from pywikibot.tools import first_lower

from wikidata import WikidataEntityBot


class LabelSettingBot(WikidataEntityBot):

    def __init__(self, **kwargs):
        self.available_options.update({
            'create': False,
        })
        super().__init__(**kwargs)
        self.create_missing_item = self.opt['create'] is True

    def stripped(self, title):
        if title.endswith(')'):
            return title.partition(' (')[0]
        else:
            return title

    def treat_page_and_item(self, page, item):
        title = page.properties().get('displaytitle')
        if not title:
            return
        page_title = page.title()
        if first_lower(page_title) != title:
            return
        lang = page.site.lang
        label = item.labels.get(lang)
        if not label or self.stripped(label) == self.stripped(page_title):
            item.labels[lang] = first_lower(label) if label else title
            link = page.title(as_link=True, insite=item.site)
            summary = f'importing [{lang}] label from displaytitle in {link}'
            self.user_edit_entity(item, summary=summary)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = GeneratorFactory(site=site)
    for arg in genFactory.handle_args(local_args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    if not generator:
        generator = page_with_property_generator('displaytitle', site=site)
        if genFactory.namespaces:
            generator = NamespaceFilterPageGenerator(
                generator, genFactory.namespaces, site=site)

    bot = LabelSettingBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
