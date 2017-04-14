# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
import codecs
import pywikibot
import threading

from pywikibot import pagegenerators
from pywikibot.bot import BaseBot, SkipPageError

from .wikidata import WikidataEntityBot

class ErrorReportingBot(BaseBot):

    file_name = None
    page_pattern = None

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'interval': 5 * 60,
        })
        super(ErrorReportingBot, self).__init__(**kwargs)
        self.open()
        self.load_page()
        self.stop = False
        self.save_file()
        #self.update_time()

    def open(self):
        try:
            open('..\%s' % self.file_name, 'x').close()
        except OSError:
            pass

    def load_page(self):
        self.log_page = pywikibot.Page(self.site,
                                       self.pattern % self.site.username())
        try:
            self.log_page.get()
        except pywikibot.NoPage:
            self.log_page.text = ''

    def append(self, text):
        with codecs.open('..\%s' % self.file_name, 'r+', 'utf-8') as f:
            f.read() # jump to the end
            f.write(text)

    def save_file(self):
        if self.stop:
            return
        with codecs.open('..\%s' % self.file_name, 'r+', 'utf-8') as f:
            f.seek(0) # jump to the beginning
            read = '\n'.join(f.read().splitlines()) # multi-platform
            if read:
                self.log_page.text += read
                self.log_page.save('update')
                f.seek(0) # jump to the beginning
                f.truncate() # and delete everything
                #self.update_time()
        threading.Timer(self.getOption('interval'), self.save_file).start() # fixme

    def check_time(self):
        if (datetime.datetime.now() - self.timestamp).total_seconds() > self.getOption('interval'):
            self.save_file()

    def update_time(self):
        self.timestamp = datetime.datetime.now()

    def exit(self):
        self.stop = True
        super(ErrorReportingBot, self).exit()
        pywikibot.output('Waiting for the second thread to stop') #fixme

class DisambigsCheckingBot(WikidataEntityBot, ErrorReportingBot):

    disambig_item = 'Q4167410'
    file_name = 'log_disambigs.txt'
    page_pattern = 'User:%s/Disambig_errors'
    skip = ['enwiki', 'igwiki', 'mkwiki', 'mznwiki', 'specieswiki', 'towiki']

    def __init__(self, **kwargs):
        super(DisambigsCheckingBot, self).__init__(**kwargs)

    def init_page(self, item):
        super(DisambigsCheckingBot, self).init_page(item)
        if '[[%s]]' % item.title() in self.log_page.text:
            raise SkipPageError(item, 'Already reported page')

        for prop in item.claims:
            if prop == 'P31':
                for claim in item.claims[prop]:
                    if claim.target_equals(self.disambig_item):
                        return

        raise SkipPageError(item, 'Item is not a disambiguation')

    @property
    def generator(self):
        QUERY = '''
SELECT DISTINCT ?item {
  ?item wdt:P31 wd:%s .
  BIND( SHA512( CONCAT( STR( ?item ), STR( RAND() ) ) ) AS ?hash ) .
} ORDER BY ?hash LIMIT 500'''.replace('\n', ' ') % self.disambig_item

        return pagegenerators.PreloadingItemGenerator(
            pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=self.site))

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
                append_text += '\n** {} – {} – doesn\'t exist'.format(
                    dbname, page.title(asLink=True, insite=self.site))
                continue
            if page.isRedirectPage():
                target = page.getRedirectTarget()
                try:
                    target_item = target.data_item()
                except pywikibot.NoPage:
                    target_id = "''no item''"
                else:
                    target_id = '[[%s]]' % target_item.title()
                if not target.isDisambig():
                    target_id += ', not a disambiguation'
                sitename = apisite.sitename()
                append_text += '\n** {} – {} – redirects to {} ({})'.format(
                    dbname, page.title(asLink=True, insite=self.site),
                    target.title(asLink=True, insite=self.site), target_id)
                continue
            if not page.isDisambig():
                append_text += '\n** {} – {} – not a disambiguation'.format(
                    dbname, page.title(asLink=True, insite=self.site))

        if append_text != '':
            prep = '\n* [[%s]]' % item.title()
            if count > 0:
                prep += ' (%s sitelink%s)' % (count, 's' if count > 1 else '')
            append_text = prep + append_text
            self.append(append_text)

        #self.check_time()

def main(*args):
    options = {}
    for arg in pywikibot.handle_args(args):
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    clearonly = options.pop('clearonly', False)
    site = pywikibot.Site('wikidata', 'wikidata')
    bot = DisambigsCheckingBot(site=site, **options)
    if not clearonly:
        bot.run()

if __name__ == '__main__':
    main()
