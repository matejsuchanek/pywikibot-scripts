#!/usr/bin/python
import pywikibot

from pywikibot import pagegenerators

from query_store import QueryStore
from wikidata import WikidataEntityBot


class CaptionToImageBot(WikidataEntityBot):

    '''
    Bot re-adding file captions as qualifiers to the files on Wikidata

    Supported parameters:
    * -removeall - if a caption cannot be reused, remove it as well
    '''

    caption_property = 'P2096'
    image_property = 'P18'
    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.available_options.update({
            'removeall': False
        })
        kwargs.setdefault('bad_cache', []).append(self.caption_property)
        super().__init__(**kwargs)
        self.store = QueryStore()
        self._generator = generator or self.custom_generator()

    def custom_generator(self):
        query = self.store.build_query('captions', prop=self.caption_property)
        return pagegenerators.WikidataSPARQLPageGenerator(query, site=self.repo)

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self._generator)

    def filterProperty(self, prop_page):
        return prop_page.type == 'commonsMedia'

    def skip_page(self, item):
        return super().skip_page(item) or (
            self.caption_property not in item.claims)

    def _save_entity(self, func, *args, **kwargs):
        # fixme upstream
        if 'asynchronous' in kwargs:
            kwargs.pop('asynchronous')
        return func(*args, **kwargs)

    def treat_page_and_item(self, page, item):
        our_prop = self.image_property
        if our_prop not in item.claims:
            our_prop = None
            for prop in item.claims:
                if self.checkProperty(prop):
                    if our_prop is None:
                        our_prop = prop
                    else:
                        pywikibot.info('More than one media property used')
                        return

        remove_claims = []
        remove_all = self.opt['removeall'] is True
        if our_prop is None:
            pywikibot.info('No media property found')
            if remove_all:
                remove_claims.extend(item.claims[self.caption_property])
                self._save_page(item, self._save_entity, item.removeClaims,
                                remove_claims, summary='removing redundant property')
            return

        media_claim = item.claims[our_prop][0]
        if len(item.claims[our_prop]) > 1:
            pywikibot.info(f'Property {our_prop} has more than one value')
            return

        for caption in item.claims[self.caption_property]:
            if self.caption_property in media_claim.qualifiers:
                language = caption.getTarget().language
                has_same_lang = any(
                    claim.getTarget().language == language
                    for claim in media_claim.qualifiers[self.caption_property])
                if has_same_lang:
                    pywikibot.info(f'Property {our_prop} already has '
                                   f'a caption in language {language}')
                    if remove_all:
                        remove_claims.append(caption)
                    continue

            qualifier = caption.copy()
            qualifier.isQualifier = True
            if self._save_page(item, self._save_entity, media_claim.addQualifier,
                               qualifier):
                remove_claims.append(caption)

        if remove_claims:
            self._save_page(item, self._save_entity, item.removeClaims,
                            remove_claims, summary='removing redundant property')


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
    bot = CaptionToImageBot(generator=generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
