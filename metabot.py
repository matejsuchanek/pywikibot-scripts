#!/usr/bin/python
import re

from collections import OrderedDict
from operator import methodcaller

import pywikibot

from pywikibot import pagegenerators, textlib

from pywikibot.exceptions import APIError
from pywikibot.textlib import mwparserfromhell
from pywikibot.tools import first_upper

from .tools import get_best_statements
from .wikidata import WikidataEntityBot


def parse_float(value):  # todo: move to tools
    if ',' in value:
        if '.' in value:
            try:
                value = float(value.replace(',', ''))
            except ValueError:
                value = float(value.replace('.', '').replace(',', '.'))
        else:
            try:
                value = float(value.replace(',', '.'))
            except ValueError:
                value = float(value.replace(',', ''))
    else:
        try:
            value = float(value)
        except ValueError:
            value = float(value.replace('.', ''))
    return value


class MetadataHarvestingBot(WikidataEntityBot):

    obsolete_params = ('datatype', 'planned use', 'status', 'suggested values',
                       'subpage', 'topic', 'number of ids', )
    regexes = {
        'arrow': r"\s*(?: (?:<|'')+?(?:\{\{P\|P?\d+\}\}|[A-Za-z ]+)(?:''|>)+?=? |(?<=\d)\|[A-Za-z ]+\|(?=Q?\d)|→|\x859|[=\-]+>|\s[=-]+\s|\s>|:\s)\s*",
        'commonsMedia': re.compile(
            r'\b(?:[Ff]il|[Ii]mag)e:(?P<value>[^]|[{}]*\.\w{3,})\b'),
        #'coordinates': r'',
        #'monolingualtext': r'',
        'quantity': re.compile(
            r'(?P<value>(?P<amount>-?\b\d(?:[\d.,]*\d)?)\b'
            r'(\s*(?:±|[+-])\s*(?P<error>\d(?:[\d.,]*\d)?)\b)?'
            r'(?P<unit>\W+[Qq]\W*[1-9]\d*\b)?)'),
        'split-break': re.compile(r'\s*(?:<[^>\w]*br\b[^>]*> *|'
                                  '(?:^|\n+)[:;*#]+){1,2}'),
        'split-comma': re.compile(r'\s*[:;,]\s+'),
        #'time': r'',
        'url': textlib.compileLinkR(),
        'wikibase-item': re.compile(r'\b[Qq]\W*(?P<value>[1-9]\d*)\b'),
        'wikibase-property': re.compile(r'\b[Pp]\W*(?P<value>[1-9]\d*)\b'),
    }
    template_metadata = 'Property documentation'
    use_from_page = False

    def __init__(self, generator, **kwargs):
        self.available_options.update({
            'always': False,
            'importonly': False,
            'start': 'P1',
            'end': None,
            'total': None,
        })
        super().__init__(**kwargs)
        self._generator = generator or self.custom_generator()
        self.func_dict = {
            'corresponding template': self.get_data_as_item('P2667'),
            'example': self.example,
            'formatter URL': self.formatter,
            'proposed by': self.proposed_by,
            'subject item': self.get_data_as_item('P1629', 'P1687'),
            'subpage': self.subpage,
            'source': self.source,
            'allowed values': self.allowed_values,
            #'source': self.get_data_as_url('P1896'),
            'number of ids': self.number_of_ids,
            #'embed URL': self.get_data_as_url('P2720'),
            #'allowed units': ...,
            #'see also': ...,
            'track diff cat': self.get_data_as_item('P3709'),
            'track local yes-WD no': self.get_data_as_item('P3713'),
            'track same cat': self.get_data_as_item('P3734'),
            'track usage cat': self.get_data_as_item('P2875'),
        }

    @property
    def generator(self):
        return pagegenerators.PreloadingEntityGenerator(self.subgenerator())

    def subgenerator(self):
        for page in self._generator:
            if '/' in page.title():
                continue
            if page.isTalkPage():
                page = page.toggleTalkPage()
            if page.namespace() == self.repo.property_namespace:
                yield pywikibot.PropertyPage(
                    self.repo, page.title(with_ns=False))

    def custom_generator(self):
        end = self.opt['end']
        for page in pagegenerators.AllpagesPageGenerator(
                start=self.opt['start'], namespace=120,
                site=self.repo, total=self.opt['total']):
            yield page
            if page.title(with_ns=False) == end:
                break

    def skip_page(self, prop):
        return super().skip_page(prop) or (
            not prop.exists() or prop.isRedirectPage())

    def treat_page(self):
        prop = self.current_page
        self.treat_property_and_talk(prop, prop.toggleTalkPage())

    def treat_property_and_talk(self, prop, page):
        self.current_talk_page = page
        # todo: skip sandbox properties
        # todo: removeDisabledParts now?
        code = mwparserfromhell.parse(page.text, skip_style_tags=True)
        for template in code.ifilter_templates():
            if not template.name.matches(self.template_metadata):
                continue
            params = OrderedDict()
            for param in template.params:
                params[str(param.name).strip()] = str(param.value).strip()
            break
        else:
            pywikibot.info(f'Template "{self.template_metadata}" not found')
            return

        keys = set(self.func_dict.keys()) & set(params.keys())
        # formatter URL must go before example
        if {'formatter URL', 'example'} <= keys:
            keys.remove('formatter URL')
            keys = ['formatter URL'] + list(keys)

        clear_params = []
        for key in keys:
            param = textlib.removeDisabledParts(params[key])
            if param == '-':
                continue
            if param != '':
                pywikibot.info(f'Found param "{key}"')
                try:
                    remove = self.func_dict[key](param)
                except APIError:
                    remove = False
                if remove:
                    clear_params.append(key)
        if self.opt['importonly']:
            return

        for par in clear_params:
            template.remove(par, keep_field=True)
        for par in set(params.keys()) & set(self.obsolete_params):
            template.remove(par)

        self.current_page = self.current_talk_page
        self.put_current(str(code), show_diff=True,
                         summary='removing migrated/obsolete parameters')

    def get_regex_from_prop(self, prop):
        for claim in get_best_statements(prop.claims.get('P1793', [])):
            if claim.getTarget():
                return claim.getTarget()
        for claim in prop.claims.get('P2302', []):
            if claim.target_equals('Q21502404'):
                if claim.qualifiers.get('P1793'):
                    return claim.qualifiers['P1793'][0].getTarget()
        return None

    def get_formatter_regex(self):
        if 'formatter' not in self.regexes:
            prop = pywikibot.PropertyPage(self.repo, 'P1630')
            self.regexes['formatter'] = re.compile(
                self.get_regex_from_prop(prop))
        return self.regexes['formatter']

    def get_source(self):
        source = pywikibot.Claim(self.repo, 'P4656', is_reference=True)
        source.setTarget('https:' + self.current_talk_page.permalink())
        return source

    def make_summary(self):
        rev_id = self.current_talk_page.latest_revision_id
        return f'Importing from [[Special:PermaLink/{rev_id}|talk page]]'

    def example(self, textvalue):
        prop = self.current_page
        # todo: scope constraint
        if any(map(methodcaller('target_equals', 'Q15720608'),
                   prop.claims.get('P31', []))):
            pywikibot.info(f'{prop.title()} is for qualifier use')
            return False

        if prop.type in ('external-id', 'string'):
            regex = self.get_regex_from_prop(prop)
            if regex is None:
                pywikibot.info(f'Regex for "{prop.title()}" not found')
                return False

            formatter = None
            for claim in prop.claims.get('P1630', []):
                if claim.snaktype != 'value':
                    continue
                searchObj = self.get_formatter_regex().search(claim.getTarget())
                if searchObj is None:
                    pywikibot.info('Found wrongly formatted formatter URL '
                                   f'for "{prop.title()}"')
                    continue

                formatter = searchObj.group()
                break

            if formatter is None:
                if prop.type == 'external-id':
                    pywikibot.info(
                        f'Info: No formatter found for "{prop.title()}"')
                try:
                    regex = re.compile(f'^(?P<value>{regex})$')
                except re.error as e:
                    pywikibot.info("Couldn't create a regex")
                    pywikibot.exception(e)
                    return False
            else:
                split = formatter.split('$1')
                full_regex = ''
                full_regex += f'(?P<value>{regex})'.join(
                    map(re.escape, split[:2]))
                full_regex += '(?P=value)'.join(map(re.escape, split[2:]))
                if full_regex.endswith(re.escape('/')):
                    full_regex += '?'
                else:
                    full_regex += re.escape('/') + '?'
                full_regex = (fr'(?:{full_regex}|(?:^["\'<]?|\s)'
                              fr'(?P<value2>{regex})(?:["\'>]?$|\]))')
                try:
                    regex = re.compile(full_regex)
                except re.error as e:
                    pywikibot.info("Couldn't create a regex")
                    pywikibot.exception(e)
                    return False

        elif prop.type == 'commonsMedia':
            regex = self.get_regex_from_prop(prop)
            if regex is None:
                regex = self.regexes[prop.type]
            else:
                flags = 0
                if regex.startswith('(?i)'):
                    regex = regex[4:]
                    flags |= re.I
                regex = re.compile(
                    fr'\b(?:[Ff]il|[Ii]mag)e:(?P<value>{regex})', flags)
        else:
            if prop.type in self.regexes:
                regex = self.regexes[prop.type]
            else:
                pywikibot.info(f'"{prop.type}" is not supported datatype '
                               'for matching examples')
                return False

        remove = True
        split = self.regexes['split-break'].split(textvalue)
        if len(split) == 1:
            split = self.regexes['split-comma'].split(textvalue)
        for match in split:
            if match.strip() == '':
                continue
            pair = re.split(self.regexes['arrow'], match)
            if len(pair) == 1:
                pywikibot.info(f'Example pair not recognized in "{match}"')
                remove = False
                continue

            pair = [pair[0], pair[-1]]
            searchObj = self.regexes['wikibase-item'].search(pair[0])
            if searchObj is None:
                pywikibot.info(f'No item id found in "{pair[0]}"')
                remove = False
                continue

            item_match = 'Q' + searchObj['value']
            target = pywikibot.ItemPage(self.repo, item_match)
            while target.isRedirectPage():
                target = target.getRedirectTarget()
            if any(map(methodcaller('target_equals', target),
                       prop.claims.get('P1855', []))):
                pywikibot.info(
                    f'There is already one example with "{item_match}"')
                continue

            qual_match = regex.search(pair[1])
            if not qual_match:
                pywikibot.info(f'Couldn\'t match example value in "{pair[1]}"')
                remove = False
                continue

            for g in ('value', 'value2', 'url'):
                if g in qual_match.groupdict():
                    if qual_match[g]:
                        qual_target = qual_match[g]
                        break

            if prop.type == 'wikibase-item':
                qual_target = pywikibot.ItemPage(self.repo, 'Q' + qual_target)
                if not qual_target.exists():
                    pywikibot.info(f'"{qual_target.title()}" doesn\'t exist')
                    remove = False
                    continue
                while qual_target.isRedirectPage():
                    qual_target = qual_target.getRedirectTarget()
            elif prop.type == 'wikibase-property':
                qual_target = pywikibot.PropertyPage(
                    self.repo, 'P' + qual_target)
            elif prop.type == 'commonsMedia':
                commons = pywikibot.Site('commons', 'commons')
                imagelink = pywikibot.Link(qual_target, source=commons,
                                           defaultNamespace=6)
                qual_target = pywikibot.FilePage(imagelink)
                if not qual_target.exists():
                    pywikibot.info(f'"{qual_target.title()}" doesn\'t exist')
                    remove = False
                    continue
                while qual_target.isRedirectPage():
                    qual_target = pywikibot.FilePage(qual_target.getRedirectTarget())
            elif prop.type == 'quantity':
                try:
                    amount = parse_float(qual_match['amount'])
                except ValueError:
                    pywikibot.info(f'Couldn\'t parse "{qual_target}"')
                    remove = False
                    continue
                error = qual_match['error']
                unit = qual_match['unit']
                if error:
                    try:
                        error = parse_float(error)
                    except ValueError:
                        pywikibot.info(f'Couldn\'t parse "{qual_target}"')
                        remove = False
                        continue
                if unit:
                    search = self.regexes['wikibase-item'].search(unit)
                    unit = pywikibot.ItemPage(self.repo, 'Q' + search['value'])
                    if unit.isRedirectPage():
                        unit = unit.getRedirectTarget()
                else:
                    unit = None
                qual_target = pywikibot.WbQuantity(
                    amount, unit, error, site=self.repo)

            claim = pywikibot.Claim(self.repo, 'P1855')
            claim.setTarget(target)
            qualifier = prop.newClaim(is_qualifier=True)
            qualifier.setTarget(qual_target)
            claim.addQualifier(qualifier)
            claim.addSource(self.get_source())
            ok = self.user_add_claim(prop, claim, summary=self.make_summary())
            remove = ok and remove
        return remove

    def formatter(self, textvalue):
        prop = self.current_page
        if prop.type not in ('commonsMedia', 'external-id', 'string'):
            pywikibot.info(
                f'"{prop.type}" datatype doesn\'t make use of formatter')
            return True

        remove = True
        for match in self.get_formatter_regex().findall(textvalue):
            if any(map(methodcaller('target_equals', match),
                       prop.claims.get('P1630', []))):
                pywikibot.info(
                    f'"{prop.title()}" already has "{match}" as the formatter URL')
                continue
            if match.strip() in ('http://', 'https://'):
                continue  # ???
            claim = pywikibot.Claim(self.repo, 'P1630')
            claim.setTarget(match)
            claim.addSource(self.get_source())
            ok = self.user_add_claim(prop, claim, summary=self.make_summary())
            remove = ok and remove
        return remove

    def get_data_as_item(self, prop_id, inverse=None):
        def get_item(textvalue):
            prop = self.current_page
            remove = True
            for item in re.findall(r'\b[Qq][1-9]\d*\b', textvalue):
                if any(map(methodcaller('target_equals', item),
                           prop.claims.get(prop_id, []))):
                    pywikibot.info('"{}" already has "{}: {}"'.format(
                        prop.title(), prop_id, item))
                    continue
                if item.upper() == 'Q5':
                    continue
                claim = pywikibot.Claim(self.repo, prop_id)
                target = pywikibot.ItemPage(self.repo, item.upper())
                if target.isRedirectPage():
                    target = target.getRedirectTarget()
                claim.setTarget(target)
                claim.addSource(self.get_source())
                ok = self.user_add_claim(
                    prop, claim, summary=self.make_summary(),
                    asynchronous=not inverse)
                remove = ok and remove
                if ok and inverse:
                    rev_id = prop.latest_revision_id
                    inverse_claim = pywikibot.Claim(self.repo, inverse)
                    inverse_claim.setTarget(prop)
                    summary = ('Adding inverse to an [[Special:Diff/{}#{}|'
                               'imported claim]]').format(rev_id, prop.getID())
                    target.addClaim(inverse_claim, summary=summary)
            return remove

        return get_item

    def proposed_by(self, textvalue):
        prop = self.current_page
        if 'P3254' not in prop.claims:
            try:
                int(textvalue)
            except ValueError as e:
                pywikibot.exception(e)
            else:
                claim = pywikibot.Claim(self.repo, 'P3254')
                target = ('https://www.wikidata.org/wiki/'
                          'Wikidata:Property_proposal/Archive/{}#{}'
                          ).format(textvalue, prop.id)
                claim.setTarget(target)
                claim.addSource(self.get_source())
                return self.user_add_claim(
                    prop, claim, summary=self.make_summary())
        return False

    def subpage(self, textvalue):
        prop = self.current_page
        if 'P3254' not in prop.claims:
            title = 'Wikidata:Property_proposal/' + textvalue
            page = pywikibot.Page(self.repo, title)
            if page.exists():
                claim = pywikibot.Claim(self.repo, 'P3254')
                target = 'https://www.wikidata.org/wiki/' + title
                claim.setTarget(target)
                claim.addSource(self.get_source())
                return self.user_add_claim(prop, claim, self.make_summary())
        return False

    def get_data_as_url(self, prop_id):
        pass  # todo

    def source(self, textvalue):
        prop = self.current_page
        remove = True
        for match in self.regexes['split-break'].split(textvalue):
            if not match.strip():
                continue
            regex = self.regexes['url']  # todo: textlib.compileLinkR()
            url_match = regex.findall(match)
            if not url_match:
                pywikibot.info(f'Could not match source "{match}"')
                remove = False
                continue

            for target in url_match:
                if any(map(methodcaller('target_equals', target),
                           prop.claims.get('P1896', []))):
                    pywikibot.info(
                        f'"{prop.title()}" already has "{target}" as the source')
                    continue

                claim = pywikibot.Claim(self.repo, 'P1896')
                claim.setTarget(target)
                # todo: qualifier 'title', language "und"
                claim.addSource(self.get_source())
                ok = self.user_add_claim(
                    prop, claim, summary=self.make_summary())
                remove = ok and remove
        return remove

    def allowed_values(self, textvalue):
        return self.get_regex_from_prop(self.current_page) == textvalue

    def number_of_ids(self, textvalue):
        prop = self.current_page
        if prop.type == 'external-id' and 'P4876' not in prop.claims:
            remove = False
            match = self.regexes['quantity'].search(textvalue)
            if match:
                try:
                    num = int(match['value'])
                except ValueError as e:
                    pywikibot.exception(e)
                else:
                    target = pywikibot.WbQuantity(num, site=self.repo)
                    claim = pywikibot.Claim(self.repo, 'P4876')
                    claim.setTarget(target)
                    claim.addSource(self.get_source())
                    remove = self.user_add_claim(
                        prop, claim, summary=self.make_summary())
        else:
            remove = True
        return remove


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site('wikidata', 'wikidata')
    genFactory = pagegenerators.GeneratorFactory(site=site)
    for arg in local_args:
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if arg in ('-always', '-importonly', '-start', '-end', '-total'):
                if value != '':
                    options[arg[1:]] = int(value) if value.isdigit() else value
                else:
                    options[arg[1:]] = True
            else:
                genFactory.handle_arg(arg + sep + value)

    generator = genFactory.getCombinedGenerator()

    bot = MetadataHarvestingBot(generator, site=site, **options)
    bot.run()


if __name__ == '__main__':
    if isinstance(mwparserfromhell, Exception):
        pywikibot.error('metabot.py requires having mwparserfromhell installed')
    else:
        main()
