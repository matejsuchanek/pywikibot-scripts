#!/usr/bin/python
import pywikibot

from pywikibot import pagegenerators
from pywikibot.backports import removeprefix

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class LabelsFixingBot(WikidataEntityBot):

    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.available_options.update({
            'always': True,
            'limit': 50,
        })
        super().__init__(**kwargs)
        self.store = QueryStore()
        self._generator = generator or self.custom_generator()
        self.summary = 'remove prefix from [en] label'

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self._generator)

    def custom_generator(self):
        query = self.store.build_query('commons_labels',
                                       limit=self.opt['limit'])
        return pagegenerators.WikidataSPARQLPageGenerator(query, site=self.repo)

    def treat_page_and_item(self, page, item):
        if any(cl.target_equals('Q4167836') for cl in item.claims.get('P31', [])):
            return
        if item.getSitelink('commonswiki').startswith('Category:'):
            if item.labels['en'].startswith('Category:'):
                data = {'en': removeprefix(item.labels['en'], 'Category:')}
                self.user_edit_entity(item, {'labels': data},
                                      summary=self.summary)


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
    bot = LabelsFixingBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
