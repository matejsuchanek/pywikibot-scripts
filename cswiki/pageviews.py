import heapq
import json
import os.path as osp
from collections import defaultdict
from datetime import date, datetime, timedelta

import pywikibot
import requests
from pywikibot.backports import removeprefix
from pywikibot.comms.http import user_agent
from pywikibot.pagegenerators import PreloadingGenerator

pywikibot.handle_args()

site = pywikibot.Site()

headers = {'User-Agent': user_agent()}
hostname = site.hostname()
prefix = 'https://wikimedia.org/api/rest_v1/metrics/pageviews'
pattern = f'{prefix}/top/{hostname}/all-access/%Y/%m/%d'

check_templates = {
    'Aktualizovat', 'Celkově zpochybněno', 'Globalizovat', 'Neověřeno', 'NPOV',
    'Pahýl', 'Pravopis', 'Reklama', 'Sloh', 'Upravit', 'Vlastní výzkum',
    'Vyhýbavá slova',
}
check_categories = {
    'Wikipedie:Polozamčené stránky',
    'Wikipedie:Rozšířeně polozamčené stránky',
    'Wikipedie:Dlouhodobě zamčené stránky',
    'Wikipedie:Dobré články',
    'Wikipedie:Nejlepší články',
    'Žijící lidé',
}

top = 100
days = 7
gamma = 0.85
weights = [pow(gamma, i) for i in range(days)]

today = date.today()
this = today - timedelta(days=1)
first = today - timedelta(days=days)
min_per_day = []

check_categories.add(f'Úmrtí v roce {this.year}')
check_categories.add(f'Úmrtí v roce {this.year - 1}')

aggregate_url = '{}/aggregate/{}/all-access/user/daily/{}/{}'.format(
    prefix,
    hostname,
    first.strftime('%Y%m%d'),
    this.strftime('%Y%m%d')
)
resp = requests.get(aggregate_url, headers=headers)
data = resp.json()
daily = [entry['views'] for entry in data['items']]

index = defaultdict(lambda: [None] * days)
for diff in range(days):
    the_day = this - timedelta(days=diff)
    resp = requests.get(the_day.strftime(pattern), headers=headers)
    data = resp.json()

    array = []
    for info in data['items'][0]['articles']:
        page = info['article']
        views = info['views']
        index[page][diff] = views
        array.append(views)
    min_per_day.append(min(array))
    del data

done_heap = []
stack = []

for page, values in index.items():
    if page.startswith('Speciální:'):
        continue
    complete = True
    total = 0
    for views, at_most in zip(values, min_per_day):
        if views is None:
            complete = False
            total += at_most
        else:
            total += views

    if complete:
        done_heap.append((total, page, values))
    else:
        stack.append((total, page, values))

done_heap.sort()
del done_heap[:-top]
stack.sort()

while True:
    possible, page, values = stack.pop()
    lowest = done_heap[0][0]
    if possible < lowest:
        break

    present = [i for i, val in enumerate(values) if val is None]

    start = this - timedelta(days=max(present))
    end = this - timedelta(days=min(present))

    url = f'{prefix}/per-article/{hostname}/all-access/user/'
    url += page.replace('/', '%2F') + '/daily/'
    url += start.strftime('%Y%m%d00') + '/' + end.strftime('%Y%m%d00')
    resp = requests.get(url, headers=headers)
    if resp.ok:
        data = resp.json()
        for entry in data['items']:
            dt = datetime.strptime(entry['timestamp'], '%Y%m%d%H')
            delta = this - dt.date()
            values[delta.days] = entry['views']

    for i in range(days):
        if values[i] is None:
            values[i] = 0

    total = sum(values)
    assert total <= possible
    if total >= lowest:
        heapq.heappushpop(done_heap, (total, page, values))

done_heap.sort(reverse=True)

lines = []
lines.append(
    f"Nejčtenější stránky za období {first.day}. {first.month}. {first.year}"
    f" – {this.day}. {this.month}. {this.year}."
)
lines.append('')
lines.append('{| class="wikitable sortable"')
lines.append('! Pořadí')
lines.append('! Stránka')
lines.append('! Celkový<br>počet návštěv')
lines.append('! Vážený<br>počet návštěv')
lines.append('! Koeficient')
lines.append('! Problémy')
lines.append('! Příznaky')
lines.append('! class="unsortable" | Graf')

aggregate = sum(daily)
weighted = sum(v * w for v, w in zip(daily, weights))
coef = weighted / aggregate

lines.append('|-')
lines.append('|')
lines.append("| ''vše''")
lines.append(f'| {aggregate}')
lines.append(f'| {weighted:.0f}')
lines.append('| %s' % f'{coef:.3f}'.replace('.', ',', 1))
lines.append(f'|')
lines.append(f'|')
lines.append(f"| [https://pageviews.wmcloud.org/siteviews/?sites={hostname}"
                 f"&agent=user&range=latest-20]")

gen = (pywikibot.Page(site, title) for _, title, _ in done_heap)
for rank, (page, (total, title, values)) in enumerate(zip(
    site.preloadpages(gen, templates=True, categories=True, content=False),
    done_heap
), start=1):
    weighted = sum(v * w for v, w in zip(values, weights))
    coef = weighted / total
    link_title = title.replace('_', ' ')
    if link_title.startswith(('Soubor:', 'Kategorie:')):
        link_title = f':{link_title}'

    lines.append('|-')
    lines.append(f'| {rank}')
    lines.append(f'| [[{link_title}]]')
    lines.append(f'| {total}')
    lines.append(f'| {weighted:.0f}')
    lines.append('| %s' % f'{coef:.3f}'.replace('.', ',', 1))

    show_templates = check_templates.intersection(map(
        lambda p: p.title(with_ns=False), page.templates()))
    show_categories = check_categories.intersection(map(
        lambda p: p.title(with_ns=False), page.categories()))

    if show_templates:
        lines.append('| ' + ('<br>'.join(
            f'[[Šablona:{t}|{t}]]' for t in sorted(show_templates))))
    else:
        lines.append('|')

    if show_categories:
        lines.append('| ' + ('<br>'.join(
            f"[[:Kategorie:{c}|{removeprefix(c, 'Wikipedie:')}]]"
            for c in sorted(show_categories))))
    else:
        lines.append('|')

    lines.append(f"| [https://pageviews.wmcloud.org/pageviews/?project={hostname}"
                 f"&agent=user&range=latest-20&pages={title}]")

lines.append('|}')

the_page = pywikibot.Page(site, f'{site.username()}/Návštěvy', ns=2)
the_page.text = '\n'.join(lines)
the_page.save(minor=False, bot=False, apply_cosmetic_changes=False,
              summary='aktualizace')
