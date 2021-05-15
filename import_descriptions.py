#!/usr/bin/python
import re

import pywikibot

from pywikibot import textlib
from pywikibot.pagegenerators import (
    GeneratorFactory,
    PreloadingEntityGenerator,
    PreloadingGenerator,
    SearchPageGenerator,
    WikidataSPARQLPageGenerator,
)

from .query_store import QueryStore
from .wikidata import WikidataEntityBot


class BaseDescriptionBot(WikidataEntityBot):

    def __init__(self, **kwargs):
        self.available_options.update({
            'min_words': 2,
        })
        super().__init__(**kwargs)
        self.FORMATTING_REGEX = re.compile("'{5}|'{2,3}")
        self.REF_REGEX = re.compile(r'<ref.*?(>.*?</ref|/)>')

    def get_regex_for_title(self, escaped_title):
        pattern = r'^\*+ *\[\[(%s)(?:\|[^][]+)?\]\]' % escaped_title
        pattern += r' *(?:\([^)]+\))?'
        pattern += '(?:,| [-–]) *(.*)$'
        return re.compile(pattern, re.M)

    @staticmethod
    def handle_link(m):
        text = m.group(2)
        if text:
            return text.lstrip('|').strip()
        else:
            return m.group('title').strip()

    def validate_description(self, desc):
        return (bool(desc) and len(desc.split()) >= self.opt['min_words'])

    def parse_description(self, text):
        desc = textlib.removeDisabledParts(
            text,
            ['comment', 'file', 'nowiki', 'template', self.FORMATTING_REGEX,
             self.REF_REGEX])
        desc = LINK_REGEX.sub(self.handle_link, desc)
        desc = desc.replace('&nbsp;', ' ').strip()
        desc = re.sub(r' *\([^)]+\)$', '', desc)
        desc = desc.partition(';')[0]
        desc = re.sub(r'^.*\) [-–] +', '', desc)
        desc = re.sub(r'^\([^)]+\) +', '', desc)
        while ' ' * 2 in desc:
            desc = desc.replace(' ' * 2, ' ')
        if re.search('[^IVX]\.$', desc) or desc.endswith(tuple(',:')):
            desc = desc[:-1].rstrip()
        if desc.startswith(('a ', 'an ')):
            desc = desc.partition(' ')[2]
        return desc

    def get_summary(self, page, desc):
        return 'importing [{}] description "{}" from {}'.format(
            page.site.lang, desc, page.title(as_link=True, insite=self.repo))


class MissingDescriptionBot(BaseDescriptionBot):

    use_from_page = False

    def __init__(self, **kwargs):
        self.available_options.update({
            'allpages': False,
        })
        super().__init__(**kwargs)
        self.store = QueryStore()

    @property
    def generator(self):
        query = self.store.build_query(
            'missing_descriptions',
            hostname=self.site.hostname(),
            lang=self.site.lang)
        return PreloadingEntityGenerator(
            WikidataSPARQLPageGenerator(query, site=self.repo))

    def treat_page_and_item(self, page, item):
        if self.site.lang in item.descriptions:
            return
        title = item.getSitelink(self.site)
        search_query = r'linksto:"%s" insource:/\* *%s/' % (
            title, re.escape('[[' + title))
        regex = self.get_regex_for_title(re.escape(title))
        for ref_page in PreloadingGenerator(
                SearchPageGenerator(search_query, namespaces=[0])):
            # todo: first polish text
            match = regex.search(ref_page.text)
            if not match:
                continue
            if not self.opt['allpages'] and not ref_page.isDisambig():
                continue
            desc = self.parse_description(match.group(2))
            if not self.validate_description(desc):
                continue
            summary = self.get_summary(ref_page, desc)
            item.descriptions[self.site.lang] = desc.strip()
            if self.user_edit_entity(item, summary=summary):
                break


class MappingDescriptionBot(BaseDescriptionBot):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.regex = self.get_regex_for_title(r'[^\[\|\]]+')

    def get_pages_with_descriptions(self, text):
        data = {}
        for match in self.regex.finditer(text):
            title, desc = match.groups()
            page = pywikibot.Page(self.site, title)
            data[page] = self.parse_description(desc)
        return data

    def treat_page(self):
        page = self.current_page
        descriptions = self.get_pages_with_descriptions(page.text)
        for item in PreloadingEntityGenerator(descriptions.keys()):
            if self.site.lang in item.descriptions:
                continue
            target = pywikibot.Page(item.sitelinks[self.site])
            desc = descriptions.get(target)
            if not self.validate_description(desc):
                continue
            summary = self.get_summary(page, desc)
            item.descriptions[self.site.lang] = desc.strip()
            self.current_page = item
            self.user_edit_entity(item, summary=summary)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    genFactory = GeneratorFactory(site=site)
    for arg in local_args:
        if genFactory.handle_arg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = int(value) if value.isdigit() else value
            else:
                options[arg[1:]] = True

    generator = genFactory.getCombinedGenerator(preload=True)
    if generator:
        bot = MappingDescriptionBot(generator=generator, site=site, **options)
    else:
        bot = MissingDescriptionBot(site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
