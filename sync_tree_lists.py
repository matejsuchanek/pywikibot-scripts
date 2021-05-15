#!/usr/bin/python
import re

import mwparserfromhell
import pywikibot

from pywikibot import pagegenerators
from pywikibot.tools import first_upper

args = pywikibot.handle_args()

site = pywikibot.Site('cs', 'wikipedia')
repo = site.data_repository()
#image_repo = site.image_repository()

genFactory = pagegenerators.GeneratorFactory(site=site)
genFactory.handle_arg('-ns:0')
for arg in args:
    genFactory.handle_arg(arg)
generator = genFactory.getCombinedGenerator(preload=True)
if not generator:
    genFactory.handle_arg('-cat:Seznamy památných stromů v Česku podle okresů')
    generator = genFactory.getCombinedGenerator(preload=True)

# todo: cache all in a single query
query = '''SELECT DISTINCT ?item {
  { ?item wdt:P3296 "%s" } UNION { ?item wdt:P677 "%s" }
} LIMIT 2'''

titleR = re.compile(r'(\s*)([^[|\]<>]+?)((?: *†| *\(x\))?\s*)')

for page in generator:
    pywikibot.output(page)
    code = mwparserfromhell.parse(page.text)
    change = False
    for table in code.ifilter_tags(matches=lambda t: t.tag == 'table'):
        rows = table.contents.ifilter_tags(matches=lambda t: t.tag == 'tr')
        first = next(rows)
        index = {key: None for key in ('název', 'obrázek', 'kód')}
        for i, cell in enumerate(first.contents.ifilter_tags(
                matches=lambda t: t.tag == 'th')):
            for key, value in index.items():
                if value is None and key in str(cell.contents).lower():
                    index[key] = i
                    break
        for key, value in index.items():
            if value is None:
                pywikibot.output("Couldn't determine column for '%s'" % key)
        if index['kód'] is None:
            continue
        for row in rows:
            cells = row.contents.filter_tags(matches=lambda t: t.tag == 'td')
            code_cell = cells[index['kód']]
            templates = code_cell.contents.filter_templates(
                matches=lambda t: t.name.matches('Pstrom'))
            if len(templates) != 1:
                continue
            template = templates[0]
            params = []
            for i in (1, 2, 3):
                if template.has_param(i, ignore_empty=True):
                    params.append(str(template.get(i)).strip())
                else:
                    params.append('')
            items = list(pagegenerators.WikidataSPARQLPageGenerator(
                query % tuple(params[:2]), site=repo))
            if len(items) != 1:
                pywikibot.output(
                    "Couldn't determine the item for values {}/{} ({} items)"
                    .format(params[0], params[1], len(items)))
                continue
            item = items.pop()
            if params[2] != item.getID():  # 3rd param is index 2
                template.add(3, item.getID())
                change = True
            if index['název'] is not None:
                title_cell = cells[index['název']]
                nodes = title_cell.contents.nodes
                # fixme: ignore &nbsp;
                #wikilinks = title_cell.contents.filter_wikilinks()
                #if not wikilinks:
                if len(nodes) == 1:
                    match = titleR.fullmatch(str(nodes[0]))
                    link = item.sitelinks.get(page.site)
                    if link and match:
                        groups = match.groups()
                        if first_upper(groups[1]) == link.title:
                            new = '{}[[{}]]{}'.format(*groups)
                        else:
                            new = '{1}[[{0}|{2}]]{3}'.format(
                                link.title, *groups)
                        title_cell.contents.replace(nodes[0], new)
                        change = True

    if change:
        page.text = str(code)
        page.save(summary='doplnění článků a/nebo položek na Wikidatech',
                  asynchronous=True)
