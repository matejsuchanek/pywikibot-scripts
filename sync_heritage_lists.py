#!/usr/bin/python
from collections import defaultdict

import mwparserfromhell
import pywikibot

from pywikibot import pagegenerators
from pywikibot.textlib import removeDisabledParts
from pywikibot.data.sparql import *

from .tools import get_best_statements


def get_sources(page):
    wiki = pywikibot.Claim(repo, 'P143', is_reference=True)
    wiki.setTarget(pywikibot.ItemPage(repo, 'Q191168'))
    url = pywikibot.Claim(repo, 'P4656', is_reference=True)
    url.setTarget('https:' + page.permalink())
    return [wiki, url]


def tidy(value) -> str:
    return removeDisabledParts(str(value), site=site).strip()


args = pywikibot.handle_args()

site = pywikibot.Site('cs', 'wikipedia')
repo = site.data_repository()
image_repo = site.image_repository()

genFactory = pagegenerators.GeneratorFactory(site=site)
genFactory.handle_arg('-ns:0')
genFactory.handle_args(args)
generator = genFactory.getCombinedGenerator(preload=True)
if not generator:
    genFactory.handle_arg('-ref:Template:Památky v Česku')
    generator = genFactory.getCombinedGenerator(preload=True)

ignore_images = {'Noimage 2-1.png'}

pywikibot.info('Loading all identifiers...')

query = 'SELECT * WHERE { ?item wdt:P762 ?id }'
obj = SparqlQuery(repo=repo)
result = obj.select(query, full_data=True)
#item_to_ids = defaultdict(set)
id_to_items = defaultdict(set)
for entry in result:
    item = entry['item'].getID()
    id_ = entry['id'].value
    #item_to_ids[item].add(id_)
    id_to_items[id_].add(item)
del result

for page in generator:
    pywikibot.info(page)
    code = mwparserfromhell.parse(page.text)
    change = False
    for template in code.ifilter_templates(
            matches=lambda t: t.name.matches('Památky v Česku')):
        item = None
        if template.has('Wikidata', ignore_empty=True):
            linked_item = tidy(template.get('Wikidata').value)
        else:
            linked_item = None
        if not linked_item and template.has('Id_objektu', ignore_empty=True):
            id_ = tidy(template.get('Id_objektu').value)
            items = id_to_items[id_]
            if len(items) == 1:
                item_id = items.pop()
                item = pywikibot.ItemPage(repo, item_id)
                items.add(item_id)
        elif linked_item:
            item = pywikibot.ItemPage(repo, linked_item)
        if not item:
            continue

        item.get(get_redirect=True)
        while item.isRedirectPage():
            item = item.getRedirectTarget()
            item.get(get_redirect=True)

        if item.exists():
            if item.getID() != linked_item:
                template.add('Wikidata', item.getID())
                change = True
##        else:
##            template.add('Wikidata', '')
##            change = change or bool(linked_item)
##            item = None

        if item and not template.has('Commons', ignore_empty=True):
            ccat = None
            best = get_best_statements(item.claims.get('P373', []))
            if best:
                ccat = best[0].getTarget()
            if not ccat:
                link = item.sitelinks.get('commonswiki')
                if link and link.namespace == 14:
                    ccat = link.title
            if ccat:
                template.add('Commons', ccat)
                change = True
            del best

        if item and not template.has('Článek', ignore_empty=True):
            article = item.sitelinks.get('cswiki')
            if article:
                template.add('Článek', article.ns_title())
                change = True

        if item and not (
            template.has('Zeměpisná_šířka', ignore_empty=True)
            and template.has('Zeměpisná_délka', ignore_empty=True)
        ):
            coord = None
            best = get_best_statements(item.claims.get('P625', []))
            if best:
                coord = best[0].getTarget()
            if coord:
                template.add('Zeměpisná_šířka', str(coord.lat))
                template.add('Zeměpisná_délka', str(coord.lon))
                change = True
            del best

        if item and template.has('Obrázek', ignore_empty=True):
            image = pywikibot.FilePage(
                image_repo, tidy(template.get('Obrázek').value))
            if (
                image.exists() and not image.isRedirectPage()
                and image.title(with_ns=False) not in ignore_images
                and not item.claims.get('P18')
            ):
                # todo: check unique
                claim = pywikibot.Claim(repo, 'P18')
                claim.setTarget(image)
                claim.addSources(get_sources(page))
                item.addClaim(claim, asynchronous=True)

    if change:
        page.text = str(code)
        page.save(summary='synchronizace s údaji na Wikidatech',
                  asynchronous=True)
