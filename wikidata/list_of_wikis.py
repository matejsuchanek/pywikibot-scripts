#!/bin/python3
import json

import pywikibot

from pywikibot.data.sparql import SparqlQuery
from pywikibot.exceptions import SiteDefinitionError, UnknownFamilyError
from tqdm import tqdm


pywikibot.handle_args()

repo = pywikibot.Site('wikidata')
page = pywikibot.Page(repo, 'Wikidata:List of wikis/python')
data = json.loads(page.text)

endpoint = SparqlQuery(repo=repo)
query = '''SELECT * WHERE { ?item wdt:P1800 ?dbname } ORDER BY ?dbname'''
missing_families = set()
added = set()

out = {}
for entry in tqdm(endpoint.select(query, full_data=True)):
    item = entry['item'].getID()
    dbname = entry['dbname'].value
    code, sep, right = dbname.rpartition('wik')
    if not sep:
        pywikibot.output(f'dbname not recognized: {dbname}')
        continue

    if dbname == 'sourceswiki':
        code, family = 'mul', 'wikisource'
    else:
        family = sep + right
        if family == 'wiki':
            if code in data:  # commons, etc.
                family = code
            else:
                family = 'wikipedia'

    if family in missing_families:
        continue

    replace_hyphen = False
    if '_' in code:
        code = code.replace('_', '-')
        replace_hyphen = True

    try:
        site = pywikibot.Site(code, family)
    except UnknownFamilyError as e:
        missing_families.add(family)
        pywikibot.log(e.unicode)
        continue
    except SiteDefinitionError as e:
        pywikibot.log(e.unicode)
        continue

    if replace_hyphen:
        code = code.replace('-', '_')

    if code in out.setdefault(family, {}):
        pywikibot.warning(f'Duplicate {code}.{family} entry for {dbname}')
        continue

    out[family][code] = item
    if code not in data.get(family, {}):
        added.add(dbname)

if added:
    total = sum(map(len, out.values()))
    summary = f'Updating list of wikis: {total} wikis; added: ' + (
        ', '.join(sorted(added)))
    text = json.dumps(out, sort_keys=True, indent=4)
    pywikibot.showDiff(page.text, text)
    page.text = text
    pywikibot.output(f'Edit summary: {summary}')
    page.save(summary=summary, minor=False, bot=False)
else:
    pywikibot.output('No wikis to be added')
