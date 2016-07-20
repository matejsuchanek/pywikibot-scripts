# -*- coding: utf-8  -*-
import datetime
import pywikibot

from pywikibot import pagegenerators

start = datetime.datetime.now()

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

# hack: dummy clause to create the file if it doesn't exist
with open('..\log_disambigs.txt', 'w') as f:
    skip = ['enwiki', 'mkwiki', 'mznwiki', 'specieswiki', 'towiki']

save_rate = 5 * 60 # how often to save (seconds)
    
log_page = pywikibot.Page(site, u'User:%s/Disambig_errors' % site.username())
try:
    log_page.get()
except pywikibot.NoPage:
    log_page.text = ''

disambig_item = pywikibot.ItemPage(repo, 'Q4167410')

QUERY = """SELECT DISTINCT ?item {
  ?item wdt:P31 wd:Q4167410;
        schema:dateModified ?date .
} ORDER BY ?date LIMIT 10000""".replace('\n', ' ')

def save_file(log_page, last_saved):
    with open('..\log_disambigs.txt', 'r+') as log_file:
        read = ''.join([line.decode('utf8') for line in log_file.readlines()])
        if len(read) > 1:
            read = read[0:] # fixme: some invisible character
            log_page.get(force=True)
            log_page.text += read
            log_page.save('update', async=True)
            log_file.seek(0)
            log_file.truncate()
            return datetime.datetime.now()
    return last_saved

# clean the file in case there was a failure last time
last_saved = save_file(log_page, datetime.datetime.now())

for item in pagegenerators.WikidataSPARQLPageGenerator(QUERY, site=site):
    item_id = item.title()
    if item.isRedirectPage():
        pywikibot.output('%s is redirect' % item_id)
        continue

    if '* [[%s]]' % item_id in log_page.text:
        continue

    item.get()
    if not item.claims.has_key('P31'):
        continue

    for claim in item.claims['P31']:
        if claim.target_equals(disambig_item):
            break
    else:
        continue

    count = len(item.sitelinks.keys())
    if count == 0:
        append_text += '\n** no sitelinks'

    append_text = ''
    for dbname in item.sitelinks.keys():
        if dbname in skip:
            continue
        apisite = pywikibot.site.APISite.fromDBName(dbname)
        page = pywikibot.Page(apisite, item.sitelinks[dbname])
        if not page.exists():
            args = [dbname, apisite.sitename(), page.title()]
            append_text += u"\n** {} – [[{}:{}]] – doesn't exist".format(*args)
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
            args = [dbname, sitename, page.title(), sitename, target.title(), target_id]
            append_text += u"\n** {} – [[{}:{}]] – redirects to [[{}:{}]] ({})".format(*args)
            continue
        if not page.isDisambig():
            args = [dbname, apisite.sitename(), page.title()]
            append_text += u"\n** {} – [[{}:{}]] – not a disambiguation".format(*args)

    if append_text != '':
        with open('..\log_disambigs.txt', 'a') as log_file:
            prep = '\n* [[%s]]' % item_id
            if count > 0:
                prep += ' (%s sitelink%s)' % (count, 's' if count > 1 else '')
            append_text = prep + append_text
            pywikibot.output(append_text)
            log_file.write(append_text.encode('utf8'))

    if (datetime.datetime.now() - last_saved).total_seconds() > save_rate:
        last_saved = save_file(log_page, last_saved)

save_file(log_page, last_saved)

end = datetime.datetime.now()

pywikibot.output("Complete! Took %s seconds" % (end - start).total_seconds())
