#!/usr/bin/python
import pywikibot

from pywikibot import pagegenerators

from wikidata import WikidataEntityBot
from wikidata_cleanup_toolkit import WikidataCleanupToolkit


class WikidataCleanupBot(WikidataEntityBot):

    use_from_page = False

    def __init__(self, generator, fix, **kwargs):
        super().__init__(**kwargs)
        self._generator = generator
        self.fix = fix
        self.my_kit = WikidataCleanupToolkit([self.fix])

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self._generator)

    @property
    def summary(self):
        return {
            'add_missing_labels': 'import labels from sitelinks',
            'cleanup_labels': 'strip labels',
            'deduplicate_aliases': 'remove duplicate aliases',
            'deduplicate_claims': 'merge duplicate claims',
            'deduplicate_references': 'remove duplicate references',
            'fix_HTML': 'resolve HTML entities',
            'fix_languages': 'resolve invalid languages',
            'fix_quantities': 'remove explicit bounds',
            'replace_invisible': 'replace invisible characters',
        }[self.fix]

    def treat_page_and_item(self, page, item):
        data = None  # seems to work more reliably than empty dict
        if self.my_kit.cleanup(item, data):
            self.user_edit_entity(item, data, summary=self.summary)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = pagegenerators.GeneratorFactory(site=site)
    for arg in genFactory.handle_args(local_args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator()
    bot = WikidataCleanupBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
