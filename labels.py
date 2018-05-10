# -*- coding: utf-8 -*-
import pywikibot

from pywikibot import pagegenerators

from .wikidata import WikidataEntityBot


class WikidataLabelsBot(WikidataEntityBot):

    use_from_page = False

    def __init__(self, generator, **kwargs):
        super(WikidataLabelsBot, self).__init__(**kwargs)
        self._generator = generator

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self._generator)

    def treat_page_and_item(self, page, item):
        data = None
        if self._add_missing_labels(item, data):
            self.user_edit_entity(item, data, summary='add missing labels')


def main(*args):
    options = {}
    genFactory = pagegenerators.GeneratorFactory()
    for arg in pywikibot.handle_args(args):
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    options['generator'] = genFactory.getCombinedGenerator()

    bot = WikidataLabelsBot(**options)
    bot.run()


if __name__ == '__main__':
    main()
