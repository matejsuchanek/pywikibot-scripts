#!/usr/bin/python
import math
from collections import defaultdict

import mwparserfromhell
import pywikibot

from pywikibot import Coordinate, pagegenerators
from pywikibot.textlib import removeDisabledParts
from pywikibot.data.sparql import *
from tqdm import tqdm

from tools import get_best_statements


def tidy(value) -> str:
    return removeDisabledParts(str(value), site=site).strip()


def distance(coord1: Coordinate, coord2: Coordinate):
    lat1, lon1 = coord1.lat, coord1.lon
    lat2, lon2 = coord2.lat, coord2.lon
    radius = 6372.795

    cosValue = \
             math.sin(math.radians(lat1)) * math.sin(math.radians(lat2)) \
             + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))

    if cosValue > 1:
        return 0
    elif cosValue < -1:
        return radius * math.pi
    else:
        return radius * math.acos(cosValue)


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
id_to_items = defaultdict(set)
for entry in result:
    item = entry['item'].getID()
    id_ = entry['id'].value
    id_to_items[id_].add(item)
del result

entries = []

for page in tqdm(generator):
    code = mwparserfromhell.parse(page.text)
    for template in code.ifilter_templates(
            matches=lambda t: t.name.matches('Památky v Česku')):
        item = None
        id_ = None
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

        if template.has('Zeměpisná_šířka', ignore_empty=True) \
           or template.has('Zeměpisná_délka', ignore_empty=True):
            best = get_best_statements(item.claims.get('P625', []))
            if best and best[0].getTarget():
                coord_wd = best[0].getTarget()
                coord_list = Coordinate(
                    lat=float(str(template.get('Zeměpisná_šířka').value)),
                    lon=float(str(template.get('Zeměpisná_délka').value)),
                    site=repo)
                dist = distance(coord_list, coord_wd)
                if dist > 0.05:
                    entries.append((
                        page.title(),
                        item.getID(),
                        coord_list,
                        coord_wd,
                        dist,
                    ))

entries.sort(key=lambda t: t[-1], reverse=True)

text = '{| class="wikitable"'
text += '\n! Seznam'
text += ' !! Položka na WD'
text += ' !! Souřadnice v seznamu'
text += ' !! Souřadnice na WD'
text += ' !! Vzdálenost [km]'
for title, item_id, coord_list, coord_wd, dist in entries:
    text += '\n|-'
    text += f"\n| [[{title}|{title.removeprefix('Seznam kulturních památek ')}]]"
    text += f'\n| [[d:{item_id}|{item_id}]]'
    text += '\n| {{Souřadnice|%f|%f}}' % (coord_list.lat, coord_list.lon)
    text += '\n| {{Souřadnice|%f|%f}}' % (coord_wd.lat, coord_wd.lon)
    text += f'\n| {dist:.4f}'
text += '\n|}'

out_page = pywikibot.Page(site, 'Matěj Suchánek/Reports/Souřadnice', ns=2)
out_page.text = text
out_page.save(summary='seznam', botflag=False)
