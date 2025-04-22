#!/usr/bin/python
import pywikibot

from pywikibot import pagegenerators
from pywikibot.exceptions import NoPageError

from error_reporting import ErrorReportingBot
from wikidata import WikidataEntityBot


class DisambigsCheckingBot(WikidataEntityBot, ErrorReportingBot):

    disambig_items = {'Q4167410', 'Q22808320', 'Q61996773'}
    file_name = 'log_disambigs.txt'
    page_pattern = 'User:%s/Disambig_errors'
    skip = {
        'brwiki',
        'enwiki',
        'hakwiki',
        'igwiki',
        'mkwiki',
        'mznwiki',
        'specieswiki',
        'towiki',
    }
    use_from_page = False

    def __init__(self, generator=None, **kwargs):
        self.available_options.update({
            'limit': 1000,
            'min_sitelinks': 1,
            'offset': 0,
            #'only': None, todo
        })
        super().__init__(**kwargs)
        self.generator = pagegenerators.PreloadingEntityGenerator(
            generator or self.custom_generator()
        )

    def skip_page(self, item):
        return super().skip_page(item) or (
            item.title(as_link=True, insite=self.repo) in self.log_page.text
            or not self.is_disambig(item))

    def is_disambig(self, item):
        for claim in item.claims.get('P31', []):
            if any(claim.target_equals(cls) for cls in self.disambig_items):
                return True
        return False

    def custom_generator(self):
        # todo: move to store
        QUERY = '''SELECT ?item WITH {
  SELECT DISTINCT ?item {
    ?item wdt:P31 wd:%s; wikibase:sitelinks ?links .
    FILTER( ?links >= %i ) .
    MINUS { ?item wdt:P31 wd:Q101352 } .
  } OFFSET %i LIMIT %i
} AS %%disambig WHERE {
  INCLUDE %%disambig .
  BIND( MD5( CONCAT( STR( ?item ), STR( RAND() ) ) ) AS ?hash ) .
} ORDER BY ?hash''' % (self.disambig_item, self.opt['min_sitelinks'],
                       self.opt['offset'], self.opt['limit'])

        return pagegenerators.WikidataSPARQLPageGenerator(
            QUERY, site=self.repo, result_type=list)

    def treat_page_and_item(self, page, item):
        append_text = ''
        count = len(item.sitelinks)
        if count == 0:
            append_text += '\n** no sitelinks'
        for dbname in item.sitelinks:
            if dbname in self.skip:
                continue
            page = pywikibot.Page(item.sitelinks[dbname])
            if not page.exists():
                append_text += "\n** {} – {} – doesn't exist".format(
                    dbname, page.title(as_link=True, insite=self.repo))
                continue
            if page.isRedirectPage():
                target = page.getRedirectTarget()
                try:
                    target_item = target.data_item()
                except NoPageError:
                    link = "''no item''"
                else:
                    link = target_item.title(as_link=True, insite=self.repo)
                if not target.isDisambig():
                    link += ', not a disambiguation'
                append_text += '\n** {} – {} – redirects to {} ({})'.format(
                    dbname, page.title(as_link=True, insite=self.repo),
                    target.title(as_link=True, insite=self.repo), link)
                continue
            if not page.isDisambig():
                append_text += '\n** {} – {} – not a disambiguation'.format(
                    dbname, page.title(as_link=True, insite=self.repo))

        if append_text:
            prep = '\n* %s' % item.title(as_link=True, insite=self.repo)
            if count > 0:
                prep += f' ({count} sitelink' + ('s' if count > 1 else '') + ')'
            append_text = prep + append_text
            self.append(append_text)


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

    bot = DisambigsCheckingBot(site=site, generator=generator, **options)
    bot.run()


if __name__ == '__main__':
    main()
