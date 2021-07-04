#!/usr/bin/python
import requests

from collections import OrderedDict

import mwparserfromhell as parser
import pywikibot

from .lua_formatter import format_dictionary


def get_single_year(year):
    return year.rpartition(', ')[2]


def main():
    pywikibot.handle_args()
    site = pywikibot.Site()
    url_pattern = 'https://www.chmi.cz/files/portal/docs/meteo/ok/klementinum/extrklem{:02d}_cs.html'
    text = '-- Zdroj dat:'
    data = OrderedDict()
    for i in range(1, 13):
        url = url_pattern.format(i)
        response = requests.get(url)
        code = parser.parse(response.text)
        month = OrderedDict()
        trs = (tr for tr in code.ifilter_tags() if tr.tag == 'tr')
        next(trs)  # skip headline
        for day, tr in enumerate(trs, start=1):
            tags = tr.contents.filter_tags()
            if len(tags) != 6:
                break
            _, avg, mx, mx_year, mn, mn_year = [tag.contents for tag in tags]
            month[day] = OrderedDict([
                ('avg', avg),
                ('max', mx),
                ('max_year', get_single_year(mx_year)),
                ('min', mn),
                ('min_year', get_single_year(mn_year)),
            ])
        data[i] = month
        text += '\n-- ' + url
    page = pywikibot.Page(site, 'Modul:Klementinum/data')
    text += '\n\nreturn ' + format_dictionary(
        data, quotes_always=True, use_tabs=True)
    page.put(text, summary='aktualizace dat pro šablonu Klementinum',
             minor=False, botflag=False, apply_cosmetic_changes=False)


if __name__ == '__main__':
    main()
