# -*- coding: utf-8 -*-
import pywikibot

from pywikibot import pagegenerators
from pywikibot.bot import SkipPageError

from .wikidata import WikidataEntityBot

class CaptionToImageBot(WikidataEntityBot):

    '''
    Bot re-adding file captions as qualifiers to the files on Wikidata

    Supported parameters:
    * -removeall - if a caption cannot be reused, remove it as well
    '''

    caption_property = 'P2096'
    image_property = 'P18'

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'removeall': False
        })
        kwargs['bad_cache'] = kwargs.get('bad_cache', []) + [self.caption_property]
        super(CaptionToImageBot, self).__init__(**kwargs)

    @property
    def generator(self):
        QUERY = ('SELECT DISTINCT ?item WHERE { ?item wdt:%s [] }'
                 % self.caption_property)
        return pagegenerators.PreloadingItemGenerator(
            pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=self.repo))

    def filterProperty(self, prop_page):
        return prop_page.type == 'commonsMedia'

    def init_page(self, item):
        super(CaptionToImageBot, self).init_page(item)
        if self.caption_property not in item.claims.keys():
            raise SkipPageError(
                item,
                'Missing %s property' % self.caption_property
            )

    def treat_page(self):
        item = self.current_page
        item.get() # fixme upstream
        our_prop = self.image_property
        if our_prop not in item.claims.keys():
            our_prop = None
            for prop in item.claims.keys():
                if self.checkProperty(prop):
                    if our_prop is None:
                        our_prop = prop
                    else:
                        pywikibot.output('More than one media property used')
                        return

        remove_claims = []
        remove_all = self.getOption('removeall') is True
        if our_prop is None:
            pywikibot.output('No media property found')
            if remove_all:
                remove_claims.extend(item.claims[self.caption_property])
                self._save_page(item, self._save_entity, item.removeClaims,
                                remove_claims, summary='removing redundant property')
            return

        media_claim = item.claims[our_prop][0]
        if len(item.claims[our_prop]) > 1:
            pywikibot.output('Property %s has more than one value' % our_prop)
            return

        for caption in item.claims[self.caption_property]:
            if self.caption_property in media_claim.qualifiers.keys():
                language = caption.getTarget().language
                has_same_lang = False
                for claim in media_claim.qualifiers[self.caption_property]:
                    if claim.getTarget().language == language:
                        has_same_lang = True
                        break
                if has_same_lang:
                    pywikibot.output('Property %s already has a caption in language %s' % (our_prop, language))
                    if remove_all:
                        remove_claims.append(caption)
                    continue

            caption.isQualifier = True
            if self._save_page(item, self._save_entity, media_claim.addQualifier,
                               caption):
                remove_claims.append(caption)

        if len(remove_claims) > 0:
            self._save_page(item, self._save_entity, item.removeClaims,
                            remove_claims, summary='removing redundant property')

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    bot = CaptionToImageBot(**options)
    bot.run()

if __name__ == '__main__':
    main()
