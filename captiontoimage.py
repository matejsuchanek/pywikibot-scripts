# -*- coding: utf-8  -*-
import pywikibot

from pywikibot import pagegenerators
from pywikibot.bot import SkipPageError

from scripts.wikidata import WikidataEntityBot

class CaptionToImageBot(WikidataEntityBot):

    '''
    Bot re-adding file captions as qualifiers to the files on Wikidata

    Supported parameters:
    * -removeall - if a caption cannot be reused, remove it as well
    '''

    def __init__(self, site, **kwargs):
        self.availableOptions.update({
            'removeall': False
        })
        kwargs['bad_cache'] = ['P2096']
        super(CaptionToImageBot, self).__init__(site, **kwargs)

    def filterProperty(self, prop_page):
        return prop_page.type == "commonsMedia"

    def init_page(self, item):
        super(CaptionToImageBot, self).init_page(item)
        if 'P2096' not in item.claims.keys():
            raise SkipPageError(
                item,
                "Missing P2096 property"
            )

    def treat_page(self):
        item = self.current_page
        our_prop = 'P18'
        if our_prop not in item.claims.keys():
            our_prop = None
            for prop in item.claims.keys():
                if checkProperty(prop):
                    if our_prop is None:
                        our_prop = prop
                    else:
                        pywikibot.output("More than one media property used")
                        return

        remove_claims = []
        remove_all = self.getOption('removeall') is True
        if our_prop is None:
            pywikibot.output("No media property found")
            if remove_all:
                remove_claims.extend(item.claims['P2096'])
                self._save_page(item, self._save_entity, item.removeClaims,
                                remove_claims, summary="removing redundant property")
            return

        media_claim = item.claims[our_prop][0]
        if len(item.claims[our_prop]) > 1:
            pywikibot.output("Property %s has more than one value" % our_prop)
            return

        for caption in item.claims['P2096']:
            if 'P2096' in media_claim.qualifiers.keys():
                language = caption.getTarget().language
                has_same_lang = False
                for claim in media_claim.qualifiers['P2096']:
                    if claim.getTarget().language == language:
                        has_same_lang = True
                        break
                if has_same_lang is True:
                    pywikibot.output("Property %s already has a caption in language %s" % (our_prop, language))
                    if remove_all:
                        remove_claims.append(caption)
                    continue

            caption.isQualifier = True
            self._save_page(item, self._save_entity, media_claim.addQualifier,
                            caption)
            remove_claims.append(caption)

        if len(remove_claims) > 0:
            self._save_page(item, self._save_entity, item.removeClaims,
                            remove_claims, summary="removing redundant property")

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    QUERY = "SELECT DISTINCT ?item WHERE { ?item wdt:P2096 [] }"

    site = pywikibot.Site('wikidata', 'wikidata')

    options['generator'] = pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site)

    bot = CaptionToImageBot(site, **options)
    bot.run()

if __name__ == "__main__":
    main()
