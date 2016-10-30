# -*- coding: utf-8  -*-
import datetime
import pywikibot

from pywikibot import pagegenerators
from pywikibot.bot import (
    BaseBot, ExistingPageBot, NoRedirectPageBot, SingleSiteBot, SkipPageError
)

class ErrorReportingBot(BaseBot):

    def __init__(self, **kwargs):
        pywikibot.output("constructing bot")
        self.availableOptions.update({
            'interval': 5 * 60
        })
        file_name = kwargs.pop('file_name')
        page_pattern = kwargs.pop('page_pattern')
        super(ErrorReportingBot, self).__init__(**kwargs)
        self.availableOptions.update({
            'always': True
        })
        self.openFile(file_name)
        self.loadPage(page_pattern)
        self.saveFile()
        self.updateTimestamp()

    def openFile(self, file_name):
        pywikibot.output("opening file")
        try:
            file = open('..\%s' % file_name, 'x')
            file.close()
        except OSError:
            pass

        self.file = open('..\%s' % file_name, 'r+')

    def loadPage(self, pattern):
        pywikibot.output("loading page")
        self.log_page = pywikibot.Page(self.site, pattern % self.site.username())
        try:
            self.log_page.get()
        except pywikibot.NoPage:
            self.log_page.text = ''

    def addToFile(self, text):
        pywikibot.output("adding to file")
        for line in text.splitlines():
            self.file.write(line)

    def saveFile(self):
        read = ''.join(self.file.readlines())
        if len(read) > 1:
            read = read[0:] # fixme: some invisible character
            self.log_page.get(force=True)
            self.log_page.text += read
            self.log_page.save('update', async=True)
            self.log_file.seek(0)
            self.log_file.truncate()
            self.updateTimestamp()

    def checkSave(self):
        if (datetime.datetime.now() - self.timestamp).total_seconds() > self.getOption('interval'):
            self.saveFile()

    def updateTimestamp(self):
        self.timestamp = datetime.datetime.now()

    def exit(self):
        self.file.close()
        super(ErrorReportingBot, self).exit()

class DisambigsCheckingBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot, ErrorReportingBot):

    skip = ['enwiki', 'mkwiki', 'mznwiki', 'specieswiki', 'towiki']

    def __init__(self, **kwargs):
        kwargs['page_pattern'] = u'User:%s/Disambig_errors'
        kwargs['file_name'] = 'log_disambigs.txt'
        super(DisambigsCheckingBot, self).__init__(**kwargs)
        self.repo = self.site.data_repository()
        self.__disambig_item = pywikibot.ItemPage(self.repo, 'Q4167410')

    def init_page(self, item):
        item.get()
        if '[[%s]]' % item.title() in self.log_page.text:
            raise SkipPageError(
                item,
                "Already reported page"
            )

        for prop in item.claims:
            if prop == 'P31':
                for claim in item.claims[prop]:
                    if claim.target_equals(self.__disambig_item):
                        return

        raise SkipPageError(
            item,
            "Item is not a disambiguation"
        )

    def treat_page(self):
        item = self.current_page
        append_text = ''
        count = len(item.sitelinks)
        if count == 0:
            append_text += '\n** no sitelinks'
        for dbname in item.sitelinks.keys():
            if dbname in self.skip:
                continue
            apisite = pywikibot.site.APISite.fromDBName(dbname)
            page = pywikibot.Page(apisite, item.sitelinks[dbname])
            if not page.exists():
                args = []
                append_text += u"\n** {} – [[{}:{}]] – doesn't exist".format(
                    dbname, apisite.sitename(), page.title())
                continue
            if page.isRedirectPage():
                target = page.getRedirectTarget()
                try:
                    target_item = target.data_item()
                    target_id = '[[%s]]' % target_item.title()
                except pywikibot.NoPage:
                    target_id = "''no item''"
                if not target.isDisambig():
                    target_id += ', not a disambiguation'
                sitename = apisite.sitename()
                append_text += u"\n** {} – [[{}:{}]] – redirects to [[{}:{}]] ({})".format(
                    dbname, sitename, page.title(), sitename, target.title(), target_id)
                continue
            if not page.isDisambig():
                append_text += u"\n** {} – [[{}:{}]] – not a disambiguation".format(
                    dbname, apisite.sitename(), page.title())

        if append_text != '':
            prep = '\n* [[%s]]' % item.title()
            if count > 0:
                prep += ' (%s sitelink%s)' % (count, 's' if count > 1 else '')
            append_text = prep + append_text
            self.addToFile(append_text)

        self.checkSave()

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    QUERY = """SELECT DISTINCT ?item {
  ?item wdt:P31 wd:Q4167410;
        schema:dateModified ?date .
} ORDER BY ?date LIMIT 1000""".replace('\n', ' ')

    site = pywikibot.Site('wikidata', 'wikidata')

    generator = pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site)

    bot = DisambigsCheckingBot(site=site, generator=generator, **options)
    bot.run()

if __name__ == "__main__":
    main()
