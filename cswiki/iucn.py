import json
import re
from datetime import datetime

import pywikibot
import pywikibot.pagegenerators as pg
from pywikibot.exceptions import NoWikibaseEntityError
from pywikibot.page import PropertyPage

def get_revision_wrapper(item, rev_id: int):
    # https://github.com/matejsuchanek/wikidata-constraints/blob/11602b4050e4623c9f1e4e0b279cf2f6c14b2a53/retrieval.py#L131-L164
    cls = type(item)
    repo = item.repo
    entity_id = item.getID()

    rev = cls(repo, entity_id)
    data = json.loads(item.getOldVersion(rev_id))
    for key, val in data.items():
        # handle old serialization
        if val == []:
            data[key] = {}

    rev._content = data
    while True:
        try:
            rev.get()
        except (KeyError, NoWikibaseEntityError) as exc:
            # handle deleted properties
            if isinstance(exc, NoWikibaseEntityError):
                key = exc.entity.id
            else:
                key = exc.args[0]
            # in theory, this isn't needed
            if not PropertyPage.is_valid_id(key):
                raise

            if key.lower() in data['claims']:
                data['claims'].pop(key.lower())
            elif key.upper() in data['claims']:
                data['claims'].pop(key.upper())
            else:
                raise
        else:
            return rev


def is_different(old, new):
    if old == new:
        return False

    if old.getID() == 'Q11394' and new.getID() == 'Q96377276':
        return False

    return True


args = pywikibot.handle_args()

site = pywikibot.Site('cs', 'wikipedia')
repo = pywikibot.Site('wikidata', 'wikidata')

needle = re.compile(r'\b[Pp]141\b')

editions = {
    #'2012.1': '20120619',
    '2012.2': '20121017',
    '2013.1': '20130702',
    '2013.2': '20131126',
    '2014.1': '20140612',
    '2014.2': '20140724',
    '2014.3': '20141117',
    '2015.1': '20150603',
    '2015.2': '20150623',
    '2015.4': '20151119',
    '2016.2': '20160904',
    '2016.3': '20161208',
    '2017.2': '20170914',
    '2017.3': '20171205',
    '2018.1': '20180705',
    '2019.2': '20190718',
    '2019.3': '20191210',
    '2020.2': '20200709',
    '2020.3': '20201210',
    '2021.1': '20210325',
    '2021.2': '20210904',
    '2021.3': '20211209',
    '2022.1': '20220101',
    '2022.2': '20221209',
    '2023.1': '20231211',
}
stat_to_label = {
    'Q719675': 'téměř ohrožený',
    'Q211005': 'málo dotčený',
    'Q219127': 'kriticky ohrožený druh',
    'Q237350': 'vyhynulý',
    'Q239509': 'vyhynulý v přírodě',
    'Q278113': 'zranitelný',
    'Q719675': 'téměř ohrožený',
    'Q3245245': 'chybí údaje',
    'Q123509': 'vymírání',
    'Q11394': 'ohrožený',
    'Q96377276': 'ohrožený',
}
links = {
    pywikibot.Page(site, 'Kriticky_ohrožený_taxon'),
    pywikibot.Page(site, 'Málo_dotčený_taxon'),
    pywikibot.Page(site, 'O_taxonu_chybí_údaje'),
    pywikibot.Page(site, 'Nevyhodnocený_taxon'),
    pywikibot.Page(site, 'Ohrožený_taxon'),
    pywikibot.Page(site, 'Téměř_ohrožený_taxon'),
    pywikibot.Page(site, 'Zranitelný_taxon'),
    pywikibot.Page(site, 'Taxon vyhynulý v přírodě'),
    pywikibot.Page(site, 'Vyhynulý_taxon'),
}

lines = [
    '<div style="overflow-x: auto; max-width: 100%">',
    '{| class="wikitable sortable"',
    '! Č.',
    '! Taxon',
    '! class="unsortable" | Wikidata',
    '! Naposled',
    '! class="unsortable" | Odkazuje na',
]
lines.extend(f'! class="unsortable" | {ed}' for ed in editions)

i = 0

sparql = '''SELECT ?item WHERE {
  ?article schema:about ?item; schema:isPartOf <https://cs.wikipedia.org/> .
  ?item wdt:P141 ?iucn .
} ORDER BY ?item'''

gen = pg.PreloadingEntityGenerator(
    pg.WikidataSPARQLPageGenerator(sparql, site=repo)
)

for item in gen:
    if not item.claims.get('P141'):
        continue

    ts_to_status = {}
    cur = None

    for rev in item.revisions(reverse=True, content=False):
        if not rev.parentid:
            continue

        if not needle.search(rev.comment):
            continue

        if rev.comment.startswith('/* wbsetreference-set:'):
            continue

        if 'mw-reverted' in rev.tags:
            continue

        this = get_revision_wrapper(item, rev.revid)
        if this.claims.get('P141'):
            new = this.claims['P141'][0].getTarget()
            if cur is None or is_different(cur, new):
                key = rev.timestamp.strftime('%Y%m%d%H%M%S')
                ts_to_status[key] = new.getID()
                cur = new

    if len(ts_to_status) < 2:
        continue

    last_change = max(ts_to_status)

    new = item.claims['P141'][0].getTarget()
    if cur is None or is_different(cur, new):
        key = item.latest_revision.timestamp.strftime('%Y%m%d%H%M%S')
        ts_to_status[key] = new.getID()

    link = item.sitelinks[site]
    page = pywikibot.Page(link)
    created = page.oldest_revision.timestamp
    if created > datetime.strptime(last_change, '%Y%m%d%H%M%S'):
        continue

    per_edition = {}
    for ts, stat in ts_to_status.items():  # asc
        last_release_date = max(
            (date for date in editions.values() if date < ts),
            default=0
        )
        for ed, date in editions.items():
            if last_release_date <= date:
                per_edition[ed] = stat

    links_to = [
        other.title(as_link=True)
        for other in page.linkedPages(
            namespaces=0,
            content=False,
            follow_redirects=True
        )
        if other in links
    ]

    i += 1
    ymd = f'{last_change[:4]}-{last_change[4:6]}-{last_change[6:8]}'

    lines.append('|-')
    lines.append(f'| {i}')
    lines.append(f'| {link.astext()}')
    lines.append(f'| [[d:{item.getID()}|{item.getID()}]]')
    lines.append(f'| data-sort-value="{last_change}" | {ymd}')
    lines.append('| ' + ('<br>'.join(sorted(links_to))))

    last = '?'
    streak = 0
    for ed in editions:  # asc
        stat = per_edition.get(ed, '?')
        if stat == last:
            streak += 1
            continue

        if streak > 1:
            lines.append(
                f'| colspan="{streak}" align="center" | {stat_to_label.get(last, last)}'
            )
        elif streak == 1:
            lines.append(f'| {stat_to_label.get(last, last)}')

        last = stat
        streak = 1

    if streak > 1:
        lines.append(
            f'| colspan="{streak}" align="center" | {stat_to_label.get(last, last)}'
        )
    elif streak == 1:
        lines.append(f'| {stat_to_label.get(last, last)}')

lines.append('|}')
lines.append('</div>')

site.login()

output_page = pywikibot.Page(site, 'Wikipedie:WikiProjekt_Biologie/Status_ohrožení/vše')
output_page.text = '\n'.join(lines)
output_page.save(
    summary='tabulka', apply_cosmetic_changes=False, bot=False, minor=False
)
