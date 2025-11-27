#!/bin/python3
import json
import re

from collections import deque, OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import IntEnum
from functools import cache, lru_cache
from typing import Any, Optional

import pywikibot

from pywikibot import textlib, WbTime
from pywikibot.bot import SingleSiteBot
from pywikibot.pagegenerators import (
    GeneratorFactory,
    PreloadingEntityGenerator,
    PreloadingGenerator,
)
from pywikibot.tools import first_upper


class DateContext(IntEnum):
    DATE_OF_BIRTH = 1
    DATE_OF_DEATH = 2
    DOB = 1
    DOD = 2


@dataclass(frozen=True)
class DayMonth:

    month: int
    day: Optional[int] = None

    def to_iso(self) -> str:
        if self.day:
            return f'{self.month:02d}-{self.day:02d}'
        else:
            return f'{self.month:02d}'

    def sortkey(self) -> tuple[int, int]:
        if self.day:
            return (self.month, self.day)
        else:
            return (self.month, 0)

    def consistent_with(self, other: 'DayMonth') -> bool:
        if self.month != other.month:
            return False

        if self.day and other.day:
            return self.day == other.day

        return True


@dataclass(frozen=True)
class Date:

    year: int
    dm: Optional[DayMonth] = None

    @property
    def month(self) -> Optional[int]:
        return self.dm.month if seld.dm else None

    @property
    def day(self) -> Optional[int]:
        return seld.dm.day if seld.dm else None

    def to_iso(self) -> str:
        if self.dm:
            return f'{self.year}-{self.dm.to_iso()}'
        else:
            return str(self.year)

    def sortkey(self) -> tuple[int, int, int]:
        if self.dm:
            return (self.year,) + self.dm.sortkey()
        else:
            return (self.year, 0, 0)

    def consistent_with(self, other: 'Date') -> bool:
        if self.year != other.year:
            return False

        if self.dm and other.dm:
            return self.dm.consistent_with(other.dm)

        return True


DatesPair = tuple[Optional[set[Date]], Optional[set[Date]]]


def split_if_matches(regex: re.Pattern, text: str) -> tuple[re.Match, str]:
    match = regex.match(text)
    if match:
        return match, text[match.end():]
    else:
        return match, text


@lru_cache(maxsize=100)
def get_month_index(text: str) -> Optional[int]:
    for i, vals in months.items():
        if text in vals:
            return i
    return None


@cache
def get_day_month(month: int, day: Optional[int] = None) -> DayMonth:
    return DayMonth(month, day)


def get_day_month_from_text(
    text: str,
    *,
    needs_day: bool = False
) -> Optional[DayMonth]:
    if '.' in text:
        day, _, month = text.partition('.')
        _, month = split_if_matches(spaceR, month)
        index = get_month_index(month)
        if index:
            return get_day_month(index, int(day))
    elif not needs_day:
        index = get_month_index(text)
        if index:
            return get_day_month(index)

    return None


def get_dms_from_match_groups(
    groups: Iterable[Optional[str]]
) -> tuple[set[DayMonth], list[str]]:
    found = set()
    invalid = []
    for group in groups:
        if group is not None:
            dm = get_day_month_from_text(group)
            if dm:
                found.add(dm)
            else:
                invalid.append(group)
    return found, invalid


def get_all_dates(years: set[int], dms: set[DayMonth]) -> set[Date]:
    dates = set()
    for dm in (dms or {None}):
        for year in years:
            dates.add(Date(year, dm))
    return dates


def remove_templates(text: str) -> str:
    while True:
        newtext, n = templateR.subn('', text)
        if not n:
            break
        text = newtext
    return text


def get_last_match(regex: re.Pattern, text: str) -> Optional[re.Match]:
    ret = None
    for match in regex.finditer(text):
        ret = match
    return ret


def get_matching_template_args(
    text: str,
    callback: Callable[[str], bool]
) -> Optional[OrderedDict[str, str]]:
    tp = textlib.extract_templates_and_params(text, strip=True)
    for template, params in tp:
        if callback(template):
            return params
    return None


def make_fragment(template: str, args: OrderedDict[str, str]) -> str:
    text = ''
    text += '{{%s|' % template
    text += '|'.join(args[key] for key in sorted(args) if key.isdigit())
    text += '}}'
    return text


def get_date_from_params(params: list[str]) -> Date:
    assert len(params) == 3
    month = int(params[1])
    if month:
        day = int(params[2]) or None
        dm = get_day_month(month, day)
    else:
        dm = None
    return Date(int(params[0]), dm)


def all_consistent(dates: set[Date], others: set[Date]) -> bool:
    for date in dates:
        if all(not date.consistent_with(d) for d in others):
            return False
    return True


def safe_union(*args: Optional[set]) -> set:
    return set.union(*[arg for arg in args if arg is not None])


months = {
    1: ['leden', 'ledna'],
    2: ['únor', 'února'],
    3: ['březen', 'března'],
    4: ['duben', 'dubna'],
    5: ['květen', 'května'],
    6: ['červen', 'června'],
    7: ['červenec', 'července'],
    8: ['srpen', 'srpna'],
    9: ['září'],
    10: ['říjen', 'října'],
    11: ['listopad', 'listopadu'],
    12: ['prosinec', 'prosince'],
}

space = '(?: |&nbsp;)*'
months_regex = '(?:' + ('|'.join(sum(months.values(), []))) + ')'
dm_regex = fr'([123]?\d\.{space}{months_regex})'

dm_tmp = ''
for vals in months.values():
    init = vals[0]
    trails = []
    for val in vals[1:]:
        if val.startswith(init):
            trails.append(val.removeprefix(init))
    if trails:
        dm_tmp += fr'\[\[([123]?\d\.{space}{init})\]\]'
        dm_tmp += ('(?:' + ('|'.join(trails)) + ')') if len(trails) > 1 else trails[0]
        dm_tmp += '|'
dm_tmp += fr'\[\[ *{dm_regex} *(?:\| *{dm_regex} *)?\]\]'

dm_link = f'(?:{dm_tmp}|{dm_regex}|({months_regex}))'
year_link = (r'(?:\[\[ *([12]?\d{0,3})(?: *\| *([12]?\d{0,3}))? *\]\]'
             r'|\b(?<!\[\[)(?<!\|)(\d{1,4})\b)')
date_regex = f'(?:{dm_link}{space}{year_link}|{year_link})'
parenth_regex = r'\(((?:[^()]|\[\[[^\[\]]+\]\])+)\)'

dmR = re.compile(dm_link)
yearR = re.compile(year_link)
dateR = re.compile(date_regex)
spaceR = re.compile(space)
parenthR = re.compile(parenth_regex)
zeroR = re.compile(r'\{\{0(?:\|0*)?\}\}')
linkR = re.compile(r'\[\[([^\[\|\]]+)(?:\|[^\[\|\]]+)?\]\]')
templateR = re.compile(r'\{\{[^{}]+\}\}')


class DatesBot(SingleSiteBot):

    available_options = {
        'always': True,
        'outputpage': None,
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.data = {
            'invalid': [],
            'entry': [],
            'person': [],
        }
        self.templates = {
            DateContext.DOB: ['Datum narození', 'Datum narození a věk', 'Věk',
                              'JULGREGDATUM'],
            DateContext.DOD: ['Datum úmrtí', 'Datum úmrtí a věk',
                              'JULGREGDATUM'],
        }

    def setup(self) -> None:
        super().setup()

    def teardown(self) -> None:
        if self.opt.outputpage:
            out = pywikibot.Page(self.site, self.opt.outputpage)
        else:
            out = pywikibot.Page(self.site,
                                 f'User:{self.site.username()}/Dates')

        text = ''
        already = set()
        if self.data['invalid']:
            text += "'''Nejednoznačné datumy:'''\n"
            text += '{| class="wikitable sortable"\n! Stránka !! Fragment\n'
            for entry in self.data['invalid']:
                pair = (entry['title'], entry['text'])
                if pair in already:
                    continue
                already.add(pair)
                entry_text = pair[1].replace('&', '&amp;')
                text += '|-\n'
                text += f"| [[{pair[0]}]]\n"
                text += f'| <code><nowiki>{entry_text}</nowiki></code>\n'
            text += '|}\n\n'

        if self.data['entry']:
            keys = ['entry', 'intro', 'categories', 'infobox', 'wd']

            text += "'''Neshodné datumy v seznamech:'''\n"
            text += '{{Sticky header}}\n'
            text += '{| class="wikitable sortable sticky-header"\n'
            text += '! class="unsortable" | Stránka'
            text += ' !! class="unsortable" | Článek !! Údaj !! Seznam'
            text += ' !! Úvod !! Kategorie !! Infobox !! Wikidata\n'
            for entry in self.data['entry']:
                text += '|-\n'
                text += f"| [[{entry['source']}]]\n"
                text += f"| [[{entry['target']}]]\n"
                text += f"| {entry['what']}\n"
                for key in keys:
                    if entry[key] is not None:
                        text += f"| {'<br>'.join(entry[key])}\n"
                    else:
                        text += '|\n'
            text += '|}\n\n'

        if self.data['person']:
            keys = ['intro', 'categories', 'infobox', 'wd']

            text += "'''Neshodné datumy v článcích:'''\n"
            text += '{{Sticky header}}\n'
            text += '{| class="wikitable sortable sticky-header"\n'
            text += ' ! class="unsortable" | Článek !! Údaj !! Úvod'
            text += ' !! Kategorie !! Infobox !! Wikidata\n'
            for entry in self.data['person']:
                text += '|-\n'
                text += f"| [[{entry['target']}]]\n"
                text += f"| {entry['what']}\n"
                for key in keys:
                    if entry[key] is not None:
                        text += f"| {'<br>'.join(entry[key])}\n"
                    else:
                        text += "|\n"
            text += '|}\n\n'

        if text:
            if out.exists():
                summary = 'aktualizace údržbového seznamu'
            else:
                summary = 'vytvoření údržbového seznamu'
            out.text = '__NOINDEX__\n' + text
            out.save(summary=summary, minor=False,
                     apply_cosmetic_changes=False)

        super().teardown()

    def treat(self, page: pywikibot.Page) -> None:
        if not page.exists():
            return

        gen = None
        title = page.title()
        if title.isdigit():
            gen = self.treat_year(page)
        elif get_day_month_from_text(title, needs_day=True):
            gen = self.treat_day_month(page)


        def process_queue():
            for item in PreloadingEntityGenerator(queue, groupsize):
                link = item.sitelinks.get(self.site)
                key = pywikibot.Page(link)
                item_cache[key] = item
            while queue:
                article = queue.popleft()
                article._item = item_cache.get(article)
                entry = entry_cache[article]
                self.treat_entry(page, article, entry)


        if gen is not None:
            groupsize = 50
            entry_cache = {}
            item_cache = {}
            queue = deque()
            gen = self.wrap_for_preloading(gen, entry_cache)
            for article in PreloadingGenerator(gen, groupsize):
                queue.append(article)
                if len(queue) == groupsize:
                    process_queue()
            process_queue()
            del queue, entry_cache, item_cache
        else:
            self.treat_person(page)

    @staticmethod
    def wrap_for_preloading(
        generator: Iterable[tuple[pywikibot.Page, Any]],
        cache: Dict
    ) -> Iterable[pywikibot.Page]:
        for page, entry in generator:
            cache[page] = entry
            yield page

    def report_fragment(self, text: str, page: pywikibot.Page) -> None:
        entry = {
            'title': page.title(),
            'text': text,
        }
        self.data['invalid'].append(entry)
        pywikibot.info('Found invalid fragment: {}'
                       .format(json.dumps(entry, indent=4)))

    def report_from_entry(self, source: pywikibot.Page, target: pywikibot.Page,
                          context: DateContext, *sources: set[Date]) -> None:
        entry = {
            'source': source.title(),
            'target': target.title(),
            'what': context.name,
        }
        keys = ['entry', 'intro', 'categories', 'infobox', 'wd']
        for key, dates in zip(keys, sources):
            if dates is not None:
                entry[key] = [date.to_iso()
                              for date in sorted(dates, key=Date.sortkey)]
            else:
                entry[key] = None

        self.data['entry'].append(entry)
        pywikibot.info('Found inconsistency: {}'
                       .format(json.dumps(entry, indent=4)))

    def report_person(self, page: pywikibot.Page, context: DateContext,
                      *sources: set[Date]) -> None:
        entry = {
            'target': page.title(),
            'what': context.name,
        }
        keys = ['intro', 'categories', 'infobox', 'wd']
        for key, dates in zip(keys, sources):
            if dates is not None:
                entry[key] = [date.to_iso()
                              for date in sorted(dates, key=Date.sortkey)]
            else:
                entry[key] = None

        self.data['person'].append(entry)
        pywikibot.info('Found inconsistency: {}'
                       .format(json.dumps(entry, indent=4)))

    def treat_entry(self, source_page: pywikibot.Page, page: pywikibot.Page,
                    entry: dict[DateContext, set[Date]]) -> None:
        while page.isRedirectPage():
            page = page.getRedirectTarget()
        if '#' in page.title() or page.namespace() != 0:
            return
        if not page.exists():
            return

        intro, infobox, cats, wd = self.get_dates_for_person(page)

        for i, context in enumerate([DateContext.DOB, DateContext.DOD]):
            dates = entry.get(context)
            sources = [intro[i], cats[i], infobox[i], wd[i]]
            if dates and not all_consistent(dates, safe_union(*sources)):
                self.report_from_entry(source_page, page, context,
                                       dates, *sources)
            #self.check_person(page, context, *sources)

    def treat_year(self, source_page: pywikibot.Page) -> None:
        year = int(source_page.title())
        context = None
        result = textlib.extract_sections(source_page.text, source_page.site)
        for title, content in result.sections:
            title_text = title.strip('= ')
            if title_text == 'Narození':
                context = DateContext.DOB
            elif title_text == 'Úmrtí':
                context = DateContext.DOD
            elif context and not title.startswith('==='):
                break

            if not context:
                continue

            dates = None
            for line in content.splitlines():
                if not line.startswith('*'):
                    continue

                orig_line = line
                line = line.lstrip('* ')
                _, line = split_if_matches(zeroR, line)
                match, line = split_if_matches(dmR, line.lstrip())
                if match:
                    found, invalid = get_dms_from_match_groups(match.groups())
                    assert found, f'No date found in "{match.group()}"'
                    if invalid or len(found) > 1:
                        self.report_fragment(match.group(), source_page)
                    dates = {Date(year, dm) for dm in found}
                    line = line.lstrip(' -–')
                    del found
                elif line.startswith('?'):
                    line = line[1:].lstrip(' -–')
                    dates = {Date(year)}

                if not dates:
                    continue

                link, line = split_if_matches(linkR, line)
                if not link:
                    if line:
                        pywikibot.info(f'No link found in: "{line}"')
                    continue

                other_dates = None
                parenth_match = get_last_match(parenthR, line)
                if parenth_match:
                    another_match = dateR.search(parenth_match[1])
                    if another_match:
                        other_dates = self.get_dates_from_match(
                            another_match, source_page)

                if context == DateContext.DOB:
                    dob, dod = dates, other_dates
                else:
                    dob, dod = other_dates, dates

                page = pywikibot.Page(self.site, link[1])
                yield page, {DateContext.DOB: dob, DateContext.DOD: dod}

    def treat_day_month(self, source_page: pywikibot.Page) -> None:
        dm = get_day_month_from_text(source_page.title(), needs_day=True)
        context = None
        result = textlib.extract_sections(source_page.text, source_page.site)
        for title, content in result.sections:
            title_text = title.strip('= ')
            if title_text == 'Narození':
                context = DateContext.DOB
            elif title_text == 'Úmrtí':
                context = DateContext.DOD
            elif context and not title.startswith('==='):
                break

            if not context:
                continue

            dates = None
            for line in content.splitlines():
                if not line.startswith('*'):
                    continue

                orig_line = line
                line = line.lstrip('* ')
                _, line = split_if_matches(zeroR, line)
                match, line = split_if_matches(yearR, line.lstrip())
                if match:
                    years = set()
                    for group in match.groups():
                        if group is not None and group.isdigit():
                            years.add(int(group))
                    assert years, f'No year found in "{match.group()}"'
                    if len(years) > 1:
                        self.report_fragment(match.group(), source_page)
                    dates = {Date(year, dm) for year in years}
                    line = line.lstrip(' -–')

                if not dates:
                    continue

                link, line = split_if_matches(linkR, line)
                if not link:
                    if line:
                        pywikibot.info(f'No link found in: "{line}"')
                    continue

                other_dates = None
                parenth_match = get_last_match(parenthR, line)
                if parenth_match:
                    another_match = dateR.search(parenth_match[1])
                    if another_match:
                        other_dates = self.get_dates_from_match(
                            another_match, source_page)

                if context == DateContext.DOB:
                    dob, dod = dates, other_dates
                else:
                    dob, dod = other_dates, dates

                page = pywikibot.Page(self.site, link[1])
                yield page, {DateContext.DOB: dob, DateContext.DOD: dod}

    def check_person(self, page: pywikibot.Page, context: DateContext,
                     *sources: set[Date]) -> None:
        filter_sources = [s for s in sources if s]
        if len(filter_sources) < 2:
            return

        for i, source in enumerate(filter_sources):
            ok = False
            for date in source:
                consistent = True
                for j, other_source in enumerate(filter_sources):
                    if i == j:
                        continue
                    if not any(date.consistent_with(d) for d in other_source):
                        consistent = False
                        break
                if consistent:
                    ok = True

            if not ok:
                self.report_person(page, context, *sources)
                return

    def get_dates_for_person(self, page: pywikibot.Page
                             ) -> tuple[DatesPair, ...]:
        intro_content = textlib.extract_sections(page.text, page.site)

        intro = self.get_dates_from_intro(intro_content.header, page)
        infobox = self.get_dates_from_infobox(intro_content.header, page)
        cats = self.get_dates_from_categories(page)
        wd = self.get_dates_from_wd(page)

        # deal with false claims
        if intro[1] and not any(bool(p[1]) for p in [infobox, cats, wd]):
            categories = textlib.getCategoryLinks(page.text, self.site)
            if 'Žijící lidé' in (cat.title(with_ns=False) for cat in categories):
                intro = (intro[0], None)

        return intro, infobox, cats, wd

    def treat_person(self, page: pywikibot.Page) -> None:
        intro, infobox, cats, wd = self.get_dates_for_person(page)
        self.check_person(page, DateContext.DOB,
                          intro[0], cats[0], infobox[0], wd[0])
        self.check_person(page, DateContext.DOD,
                          intro[1], cats[1], infobox[1], wd[1])

    def remove_elements(self, text: str) -> str:
        return textlib.removeDisabledParts(
            remove_templates(text),
            ['comment', 'file', 'ref'],
            site=self.site)

    def get_dates_from_match(self, match: re.Match, page: pywikibot.Page
                             ) -> set[Date]:
        years = set()
        rest = []
        last_year = None
        for group in match.groups():
            if group is None:
                continue
            if not group.isdigit():
                rest.append(group)
                continue

            year = int(group)
            if last_year is not None and last_year > 100 \
               and year in (last_year % 100, last_year % 10):
                continue

            years.add(year)
            last_year = year

        assert years, f'No year found in "{match.group()}"'

        dms, invalid = get_dms_from_match_groups(rest)
        out = get_all_dates(years, dms)
        if invalid or len(out) > 1:
            self.report_fragment(match.group(), page)
        return out

    def get_dates_from_intro(self, text: str, page: pywikibot.Page
                             ) -> DatesPair:
        def find_dates(text: str) -> DatesPair:
            date_of_birth = date_of_death = None
            for match in dateR.finditer(text):
                dates = self.get_dates_from_match(match, page)
                if not date_of_birth:
                    date_of_birth = dates
                elif not date_of_death:
                    date_of_death = dates
                else:
                    break
            return date_of_birth, date_of_death


        text = self.remove_elements(text)
        text, *_ = text.lstrip().partition('\n\n')

        for parenth_match in parenthR.finditer(text):
            ret = find_dates(parenth_match[1])
            if ret[0] or ret[1]:
                return ret

        return find_dates(text)

    def get_dates_from_infobox(self, text: str, page: pywikibot.Page
                               ) -> DatesPair:
        params = get_matching_template_args(
            text, lambda t: first_upper(t).startswith('Infobox'))
        if not params:
            return None, None

        date_of_birth = date_of_death = None
        match_dob_count = match_dod_count = 1

        fragment_dob = []
        fragment_dod = []

        param = params.get('datum narození', '')
        if param:
            date_of_birth = set()
            for temp in self.templates[DateContext.DOB]:
                args = get_matching_template_args(
                    param, lambda t: first_upper(t) == temp)
                if not args:
                    continue
                arg_list = [args.get(key) for key in '123']
                date_of_birth.add(get_date_from_params(arg_list))
                fragment_dob.append(make_fragment(temp, args))

            match = dateR.search(self.remove_elements(param))
            if match:
                dates = self.get_dates_from_match(match, page)
                date_of_birth |= dates
                match_dob_count = len(dates)
                fragment_dob.append(match.group())

        param = params.get('datum úmrtí', '')
        if param:
            date_of_death = set()
            for temp in self.templates[DateContext.DOD]:
                args = get_matching_template_args(
                    param, lambda t: first_upper(t) == temp)
                if not args:
                    continue
                arg_list = [args.get(key) for key in '123']
                date_of_death.add(get_date_from_params(arg_list))
                fragment = make_fragment(temp, args)
                fragment_dod.append(fragment)
                if len(args) == 6:
                    if date_of_birth is None:
                        date_of_birth = set()
                    arg_list = [args.get(key) for key in '456']
                    date_of_birth.add(get_date_from_params(arg_list))
                    fragment_dob.append(fragment)

            match = dateR.search(self.remove_elements(param))
            if match:
                dates = self.get_dates_from_match(match, page)
                date_of_death |= dates
                match_dod_count = len(dates)
                fragment_dod.append(match.group())

        if date_of_birth and len(date_of_birth) - match_dob_count > 1:
            self.report_fragment(' '.join(fragment_dob), page)

        if date_of_death and len(date_of_death) - match_dod_count > 1:
            self.report_fragment(' '.join(fragment_dod), page)

        return date_of_birth, date_of_death

    def get_dates_from_categories_helper(
        self,
        categories: list[pywikibot.Category],
        prefixes: tuple[str, str],
        page: pywikibot.Page
    ) -> set[Date]:
        years = set()
        dms = set()
        matched = []
        for cat in categories:
            title = cat.title(with_ns=False)
            rest = title.removeprefix(prefixes[0])
            if rest != title and rest.isdigit():
                years.add(int(rest))
                matched.append(cat)
                continue

            rest = title.removeprefix(prefixes[1])
            if rest != title:
                dm = get_day_month_from_text(rest, needs_day=True)
                if dm:
                    dms.add(dm)
                    matched.append(cat)

        out = get_all_dates(years, dms)
        if len(out) > 1:
            matched.sort()
            # hack
            fragment = ''.join(cat.title(as_link=True) for cat in matched)
            self.report_fragment(fragment, page)
        return out

    def get_dates_from_categories(self, page: pywikibot.Page) -> DatesPair:
        categories = textlib.getCategoryLinks(page.text, self.site)
        birth_dates = self.get_dates_from_categories_helper(
            categories, ('Narození v roce ', 'Narození '), page)
        death_dates = self.get_dates_from_categories_helper(
            categories, ('Úmrtí v roce ', 'Úmrtí '), page)

        return birth_dates, death_dates

    def get_dates_from_wd(self, page: pywikibot.Page) -> DatesPair:
        item = pywikibot.ItemPage.fromPage(page, lazy_load=True)
        if not item:
            return None, None

        try:
            item.get()
        except pywikibot.exceptions.NoPageError:
            return None, None

        birth_dates = set()
        death_dates = set()
        for prop, dates in [('P569', birth_dates), ('P570', death_dates)]:
            for claim in item.claims.get(prop, []):
                if claim.rank == 'deprecated':
                    continue
                target = claim.getTarget()
                if not target:
                    continue

                if target.precision >= WbTime.PRECISION['day']:
                    dm = get_day_month(target.month, target.day)
                    dates.add(Date(target.year, dm))
                elif target.precision == WbTime.PRECISION['month']:
                    dates.add(Date(target.year, get_day_month(target.month)))
                elif target.precision == WbTime.PRECISION['year']:
                    dates.add(Date(target.year))

        return birth_dates, death_dates


if __name__ == '__main__':
    args = pywikibot.handle_args()
    site = pywikibot.Site('cs', 'wikipedia')
    gen_factory = GeneratorFactory(site)

    options = {}
    for arg in gen_factory.handle_args(args):
        option, _, value = arg.partition(':')
        if option.startswith('-'):
            options[option[1:]] = value

    generator = gen_factory.getCombinedGenerator(preload=True)
    bot = DatesBot(generator=generator, site=site, **options)
    bot.run()
