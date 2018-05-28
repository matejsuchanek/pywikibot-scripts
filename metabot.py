# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re

from operator import methodcaller

from pywikibot import pagegenerators, textlib

from pywikibot.bot import SkipPageError
from pywikibot.textlib import mwparserfromhell
from pywikibot.tools import first_upper, OrderedDict

from .wikidata import WikidataEntityBot

class MetadataHarvestingBot(WikidataEntityBot):

    obsolete_params = ('datatype', 'planned use', 'status', 'suggested values',
                       'topic', )
    regexes = {
        'arrow': r"\s*(?: (?:<|'')+?(?:\{\{P\|P?\d+\}\}|[A-Za-z ]+)(?:''|>)+?=? |(?<=\d)\|[A-Za-z ]+\|(?=Q?\d)|→|\x859|[=\-]+>|\s[=-]+\s|\s>|:\s)\s*",
        'commonsMedia': re.compile(r'\b(?:[Ff]il|[Ii]mag)e:(?P<value>[^]|[{}]*\.\w{3,})\b'),
        #'coordinates': r'',
        #'monolingualtext': r'',
        'quantity': re.compile(r'(?P<value>-?\b\d([\d.,]*\d)?\b'
                               r'(\s+[Qq]\W*[1-9]\d*\b)?)'), # ±
        'split-break': re.compile(r'\s*(?:<[^>\w]*br\b[^>]*> *|'
                                  '(?:^|\n+)[:;*#]+){1,2}'),
        'split-comma': re.compile(r'\s*(?:[;/]\s+|,\s*)'),
        #'time': r'',
        'url': textlib.compileLinkR(),
        'wikibase-item': re.compile(r'\b[Qq]\W*(?P<value>[1-9]\d*)\b'),
        'wikibase-property': re.compile(r'\b[Pp]\W*(?P<value>[1-9]\d*)\b'),
    }
    template_metadata = 'Property documentation'
    template_regex = 'Constraint:Format'
    use_from_page = False

    def __init__(self, **kwargs):
        self.availableOptions.update({
            'always': False,
            'importonly': False,
            'start': 'P1',
            'end': None,
            'total': None,
        })
        super(MetadataHarvestingBot, self).__init__(**kwargs)
        self.func_dict = {
            'corresponding template': self.get_data_as_item('P2667'),
            'example': self.example,
            'formatter URL': self.formatter,
            'proposed by': self.proposed_by,
            'subject item': self.get_data_as_item('P1629', 'P1687'),
            'subpage': self.subpage,
            'source': self.source,
            #'source': self.get_data_as_url('P1896'),
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
        if hasattr(self, '_generator'):
            for page in self._generator:
                if '/' in page.title():
                    continue
                if page.isTalkPage():
                    page = page.toggleTalkPage()
                if page.namespace() == self.repo.property_namespace:
                    yield pywikibot.PropertyPage(
                        self.repo, page.title(withNamespace=False))
        else:
            # todo: preload
            for page in pagegenerators.AllpagesPageGenerator(
                    start=self.getOption('start'), namespace=120,
                    site=self.repo, total=self.getOption('total')):
                if '/' in page.title():
                    continue
                yield pywikibot.PropertyPage(
                    self.repo, page.title(withNamespace=False))
                if page.title(withNamespace=False) == self.getOption('end'):
                    break

    @generator.setter
    def generator(self, value):
        if value:
            pywikibot.output('Info: Own generator')
            self._generator = value

    def init_page(self, prop):
        super(MetadataHarvestingBot, self).init_page(prop)
        page = prop.toggleTalkPage()
        if not page.exists() or page.isRedirectPage():
            raise SkipPageError(prop, 'Talk page doesn\'t exist')

    def treat_page_and_item(self, page, prop):
        self.current_talk_page = page = prop.toggleTalkPage()
        code = mwparserfromhell.parse(page.text, skip_style_tags=True)
        for template in code.ifilter_templates():
            if not template.name.matches(self.template_metadata):
                continue
            params = OrderedDict()
            for param in template.params:
                params[str(param.name).strip()] = str(param.value).strip()
            break
        else:
            pywikibot.output('Template "%s" not found' % self.template_metadata)
            return

        if (prop.type in ['commonsMedia', 'external-id', 'string', 'url']
                and not prop.claims.get('P1793')):
            cleaned_text = textlib.removeDisabledParts(
                page.text, include=['nowiki'])
            templates = textlib.extract_templates_and_params(
                cleaned_text, remove_disabled_parts=False, strip=True)
            for tmpl, fielddict in templates:
                if first_upper(tmpl) != self.template_regex:
                    continue
                if 'pattern' not in fielddict:
                    continue
                pywikibot.output('Found param "regex"')
                regex = re.sub('</?nowiki>', '', fielddict['pattern'])
                claim = pywikibot.Claim(self.repo, 'P1793')
                claim.setTarget(regex.strip())
                try:
                    prop.editEntity({'claims':[claim.toJSON()]},
                                    summary=self.make_summary('P1793', regex))
                except pywikibot.PageSaveRelatedError as e:
                    pywikibot.exception(e)
                break

        keys = set(self.func_dict.keys()) & set(params.keys())
        # formatter URL must go before example
        if {'formatter URL', 'example'} <= keys:
            keys = list(keys)
            keys.remove('formatter URL')
            keys.insert(0, 'formatter URL')

        clear_params = []
        for key in keys:
            param = textlib.removeDisabledParts(params[key])
            if param == '-':
                continue
            if param != '':
                pywikibot.output('Found param "%s"' % key)
                try:
                    remove = self.func_dict[key](param)
                except pywikibot.data.api.APIError as exc:
                    remove = False
                if remove:
                    clear_params.append(key)
        if self.getOption('importonly'):
            return

        if clear_params or (set(params.keys()) & set(self.obsolete_params)):
            for par in clear_params:
                template.remove(par, keep_field=True)
            for par in set(params.keys()) & set(self.obsolete_params):
                template.remove(par)

        self.current_page = self.current_talk_page
        self.put_current(str(code), show_diff=True, asynchronous=True,
                         summary='removing migrated/obsolete parameters')

    def get_regex_from_prop(self, prop):
        for claim in prop.claims.get('P1793', []):
            if claim.getTarget():
                return claim.getTarget()
        return

    def get_formatter_regex(self):
        if 'formatter' not in self.regexes:
            prop = pywikibot.PropertyPage(self.repo, 'P1630')
            prop.get()
            self.regexes['formatter'] = re.compile(self.get_regex_from_prop(prop))
        return self.regexes['formatter']

    def make_summary(self, prop, value):
        if isinstance(value, pywikibot.ItemPage):
            value = value.title(insite=self.repo, asLink=True)
        elif isinstance(value, pywikibot.FilePage):
            value = '[[%s|%s]]' % (value.title(insite=self.repo),
                                   value.title(withNamespace=False))
        elif isinstance(value, pywikibot.PropertyPage):
            value = '[[%s|%s]]' % (value.title(), value.getID())
        rev_id = self.current_talk_page.latest_revision_id
        return ('Importing "[[Property:%s]]: %s" from '
                '[[Special:PermaLink/%s|talk page]]' % (prop, value, rev_id))

    def example(self, textvalue):
        prop = self.current_page
        if any(map(methodcaller('target_equals', 'Q15720608'),
                   prop.claims.get('P31', []))):
            pywikibot.output('%s is for qualifier use' % prop.title())
            return False

        if prop.type in ['external-id', 'string']:
            regex = self.get_regex_from_prop(prop)
            if regex is None:
                pywikibot.output('Regex for "%s" not found' % prop.title())
                return False

            formatter = None
            for claim in prop.claims.get('P1630', []):
                if claim.snaktype != 'value':
                    continue
                searchObj = self.get_formatter_regex().search(claim.getTarget())
                if searchObj is None:
                    pywikibot.output('Found wrongly formatted formatter URL '
                                     'for "%s"' % prop.title())
                    continue

                formatter = searchObj.group()
                break

            if formatter is None:
                if prop.type == 'external-id':
                    pywikibot.output('Info: No formatter found for "%s"' % prop.title())
                regex = re.compile('^(?P<value>%s)$' % regex)
            else:
                split = formatter.split('$1')
                full_regex = (('(?P<value>%s)' % regex).join(map(re.escape, split[:2])) +
                              '(?P=value)'.join(map(re.escape, split[2:])))
                full_regex = (
                    '(?:' + full_regex + r'|(?:^["\'<]?|\s)(?P<value2>' + regex +
                    r')(?:["\'>]?$|\]))')
                try:
                    regex = re.compile(full_regex)
                except re.error:
                    pywikibot.output('Couldn\'t create a regex')
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
                regex = re.compile(r'\b(?:[Ff]il|[Ii]mag)e:(?P<value>%s)' % regex, flags)
        else:
            if prop.type in self.regexes:
                regex = self.regexes[prop.type]
            else:
                pywikibot.output('"%s" is not supported datatype '
                                 'for matching examples' % prop.type)
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
                pywikibot.output('Example pair not recognized in "%s"' % match)
                remove = False
                continue

            pair = [pair[i] for i in [0, -1]]
            searchObj = self.regexes['wikibase-item'].search(pair[0])
            if searchObj is None:
                pywikibot.output('No item id found in "%s"' % pair[0])
                remove = False
                continue

            item_match = 'Q%s' % searchObj.group('value')
            target = pywikibot.ItemPage(self.repo, item_match)
            while target.isRedirectPage():
                target = target.getRedirectTarget()
            if any(map(methodcaller('target_equals', target),
                       prop.claims.get('P1855', []))):
                pywikibot.output('There is already one example with "%s"' % item_match)
                continue

            qual_match = regex.search(pair[1])
            if not qual_match:
                pywikibot.output('Couldn\'t match example value in "%s"' % pair[1])
                remove = False
                continue

            for g in ['value', 'value2', 'url']:
                if g in qual_match.groupdict():
                    if qual_match.group(g):
                        qual_target = qual_match.group(g)
                        break

            if prop.type == 'wikibase-item':
                qual_target = pywikibot.ItemPage(self.repo, 'Q%s' % qual_target)
                while qual_target.isRedirectPage():
                    qual_target = qual_target.getRedirectTarget()
            elif prop.type == 'wikibase-property':
                qual_target = pywikibot.PropertyPage(
                    self.repo, 'P%s' % qual_target)
            elif prop.type == 'commonsMedia':
                commons = pywikibot.Site('commons', 'commons')
                imagelink = pywikibot.Link(qual_target, source=commons,
                                           defaultNamespace=6)
                qual_target = pywikibot.FilePage(imagelink)
                if not qual_target.exists():
                    pywikibot.output('"%s" doesn\'t exist' % qual_target.title())
                    remove = False
                    continue
                while qual_target.isRedirectPage():
                    qual_target = pywikibot.FilePage(qual_target.getRedirectTarget())
            elif prop.type == 'quantity':
                tgt, _, unit = qual_target.partition(' ')
                # todo: +-
                if unit:
                    search = self.regexes['wikibase-item'].search(unit)
                    unit = pywikibot.ItemPage(
                        self.repo, 'Q%s' % search.group('value'))
                    if unit.isRedirectPage():
                        unit = unit.getRedirectTarget()
                else:
                    unit = None
                num = float(tgt.replace(',', ''))
                if num.is_integer():
                    num = int(num)
                qual_target = pywikibot.WbQuantity(num, site=self.repo,
                                                   unit=unit)

            claim = pywikibot.Claim(self.repo, 'P1855')
            claim.setTarget(target)
            qualifier = prop.newClaim(isQualifier=True)
            qualifier.setTarget(qual_target)
            data = {'claims':[claim.toJSON()]}
            data['claims'][0]['qualifiers'] = {prop.getID(): [qualifier.toJSON()]}
            self.user_edit_entity(prop, data, summary=self.make_summary('P1855', target),
                                  asynchronous=True)
        return remove

    def formatter(self, textvalue):
        prop = self.current_page
        if prop.type not in ['commonsMedia', 'external-id', 'string']:
            pywikibot.output('"%s" datatype doesn\'t make use of formatter'
                             '' % prop.type)
            return True

        for match in self.get_formatter_regex().findall(textvalue):
            if any(map(methodcaller('target_equals', match),
                       prop.claims.get('P1630', []))):
                pywikibot.output('"%s" already has "%s" as the formatter URL'
                                 '' % (prop.title(), match))
                continue
            if match.strip() in ['http://', 'https://']:
                continue # ???
            claim = pywikibot.Claim(self.repo, 'P1630')
            claim.setTarget(match)
            self.user_edit_entity(prop, {'claims':[claim.toJSON()]},
                                  summary=self.make_summary('P1630', match),
                                  asynchronous=True)
        return True

    def get_data_as_item(self, prop_id, inverse=None):
        def get_item(textvalue):
            prop = self.current_page
            for item in re.findall(r'\b[Qq][1-9]\d*\b', textvalue):
                if any(map(methodcaller('target_equals', item),
                           prop.claims.get(prop_id, []))):
                    pywikibot.output('"%s" already has "%s: %s"'
                                     '' % (prop.title(), prop_id, item))
                    continue
                if item.upper() == 'Q5':
                    continue
                claim = pywikibot.Claim(self.repo, prop_id)
                target = pywikibot.ItemPage(self.repo, item.upper())
                if target.isRedirectPage():
                    target = target.getRedirectTarget()
                claim.setTarget(target)
                prop.editEntity({'claims':[claim.toJSON()]}, asynchronous=True,
                                summary=self.make_summary(prop_id, target))

                if inverse:
                    rev_id = prop.latest_revision_id
                    inverse_claim = pywikibot.Claim(self.repo, inverse)
                    inverse_claim.setTarget(prop)
                    summary = ('Adding inverse to an [[Special:Diff/%s#%s|'
                               'imported claim]]' % (rev_id, prop.getID()))
                    target.get()
                    target.addClaim(inverse_claim, summary=summary)
            return True

        return get_item

    def proposed_by(self, textvalue):
        prop = self.current_page
        if 'P3254' not in prop.claims:
            try:
                int(textvalue)
            except:
                pywikibot.exception()
            else:
                claim = pywikibot.Claim(self.repo, 'P3254')
                target = ('https://www.wikidata.org/wiki/'
                          'Wikidata:Property_proposal/Archive/%s#%s'
                          ) % (textvalue, prop.id)
                claim.setTarget(target)
                self.user_edit_entity(
                    prop, {'claims':[claim.toJSON()]}, asynchronous=True,
                    summary=self.make_summary('P3254', target))
        return False

    def subpage(self, textvalue):
        prop = self.current_page
        if 'P3254' not in prop.claims:
            title = 'Wikidata:Property_proposal/%s' % textvalue
            page = pywikibot.Page(self.repo, title)
            if page.exists():
                claim = pywikibot.Claim(self.repo, 'P3254')
                target = 'https://www.wikidata.org/wiki/%s' % title
                claim.setTarget(target)
                self.user_edit_entity(
                    prop, {'claims':[claim.toJSON()]}, asynchronous=True,
                    summary=self.make_summary('P3254', target))
        return False

    def get_data_as_url(self, prop_id):
        pass # todo

    def source(self, textvalue):
        prop = self.current_page
        remove = True
        for match in self.regexes['split-break'].split(textvalue):
            if not match.strip():
                continue
            regex = self.regexes['url'] # textlib.compileLinkR()
            url_match = regex.findall(match)
            if not url_match:
                pywikibot.output('Could not match source "%s"' % match)
                remove = False
                continue

            for target in url_match:
                if any(map(methodcaller('target_equals', target),
                           prop.claims.get('P1896', []))):
                    pywikibot.output('"%s" already has "%s" as the source'
                                     '' % (prop.title(), target))
                    continue

                claim = pywikibot.Claim(self.repo, 'P1896')
                claim.setTarget(target)
                # XXX: qualifier 'title' but how to guess the language?
                self.user_edit_entity(
                    prop, {'claims':[claim.toJSON()]},
                    summary=self.make_summary('P1896', target),
                    asynchronous=True)
        return remove

def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site('wikidata', 'wikidata')
    genFactory = pagegenerators.GeneratorFactory(site=site)
    for arg in local_args:
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if arg in ['-start', '-end', '-total']:
                if value != '':
                    options[arg[1:]] = int(value) if value.isdigit() else value
                else:
                    options[arg[1:]] = True
            else:
                genFactory.handleArg(arg + sep + value)

    options['generator'] = genFactory.getCombinedGenerator()

    bot = MetadataHarvestingBot(site=site, **options)
    bot.run()

if __name__ == '__main__':
    if isinstance(mwparserfromhell, Exception):
        pywikibot.error('metabot.py requires having mwparserfromhell installed')
    else:
        main()
