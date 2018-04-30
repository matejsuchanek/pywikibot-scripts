# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot

from pywikibot.pagegenerators import (
    page_with_property_generator,
    GeneratorFactory,
    NamespaceFilterPageGenerator,
)
from pywikibot.tools import first_lower
from .wikidata import WikidataEntityBot


class LabelSettingBot(WikidataEntityBot):

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'create': False,
        })
        super(LabelSettingBot, self).__init__(**kwargs)
        self.create_missing_item = self.getOption('create') is True

    def treat_page_and_item(self, page, item):
        title = page.properties().get('displaytitle')
        if not title:
            return
        page_title = page.title()
        if first_lower(page_title) != title:
            return
        lang = page.site.lang
        label = item.labels.get(lang)
        if not label or label == page_title:
            item.labels[lang] = title
            summary = 'importing [%s] label from displaytitle in %s' % (
                lang, page.title(asLink=True, insite=item.site))
            self.user_edit_entity(item, summary=summary, show_diff=False)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = GeneratorFactory(site=site)
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = page_with_property_generator('displaytitle', site=site)
    second_generator = genFactory.getCombinedGenerator()
    if second_generator:
        genFactory.gens = [second_generator]
        genFactory.intersect = True
        generator = genFactory.getCombinedGenerator(generator)
    elif genFactory.namespaces:
        generator = NamespaceFilterPageGenerator(
            generator, genFactory.namespaces, site=site)

    bot = LabelSettingBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()