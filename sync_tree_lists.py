#!/usr/bin/python
import re

import mwparserfromhell
import pywikibot

from pywikibot import pagegenerators
from pywikibot.textlib import FILE_LINK_REGEX
from pywikibot.tools import first_upper


def get_sources(page):
    wiki = pywikibot.Claim(repo, 'P143', is_reference=True)
    wiki.setTarget(pywikibot.ItemPage(repo, 'Q191168'))
    url = pywikibot.Claim(repo, 'P4656', is_reference=True)
    url.setTarget('https:' + page.permalink())
    return [wiki, url]


args = pywikibot.handle_args()

site = pywikibot.Site('cs', 'wikipedia')
repo = site.data_repository()
image_repo = site.image_repository()

genFactory = pagegenerators.GeneratorFactory(site=site)
genFactory.handle_arg('-ns:0')
genFactory.handle_args(args)
generator = genFactory.getCombinedGenerator(preload=True)
if not generator:
    genFactory.handle_arg('-cat:Seznamy památných stromů v Česku podle okresů')
    generator = genFactory.getCombinedGenerator(preload=True)

ignore_images = {'Noimage 2-1.png'}

# todo: cache all in a single query
query = '''SELECT DISTINCT ?item {
  { ?item wdt:P3296 "%s" } UNION { ?item wdt:P677 "%s" }
} LIMIT 2'''

titleR = re.compile(r'(\s*)([^[|\]<>]+?)((?: *†| *\(x\))?\s*)')
fileR = re.compile(FILE_LINK_REGEX % '|'.join(site.namespaces[6]), re.VERBOSE)

for page in generator:
    pywikibot.info(page)
    code = mwparserfromhell.parse(page.text)
    change = False
    for table in code.ifilter_tags(matches=lambda t: t.tag == 'table'):
        rows = table.contents.ifilter_tags(matches=lambda t: t.tag == 'tr')
        first = next(rows)
        index = dict.fromkeys(('název', 'obrázek', 'kód'), None)
        for i, cell in enumerate(first.contents.ifilter_tags(
                matches=lambda t: t.tag == 'th')):
            for key, value in index.items():
                if value is None and key in str(cell.contents).lower():
                    index[key] = i
                    break

        for key, value in index.items():
            if value is None:
                pywikibot.info(f"Couldn't determine column for '{key}'")
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
                pywikibot.info(
                    f"Couldn't determine the item for values "
                    f'{params[0]}/{params[1]} ({len(items)} items)')
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

            if index['obrázek'] is not None:
                match = fileR.search(str(cells[index['obrázek']]))
                if match:
                    image = pywikibot.FilePage(image_repo, match['filename'])
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
        page.save(summary='doplnění článků a/nebo položek na Wikidatech',
                  asynchronous=True)
