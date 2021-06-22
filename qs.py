#!/usr/bin/python
import re

from decimal import Decimal
from itertools import chain

import pywikibot

from pywikibot import Coordinate, WbMonolingualText, WbQuantity, WbTime
from pywikibot.exceptions import NoWikibaseEntityError, WikiBaseError
from pywikibot.page import Property

from .wikidata import WikidataEntityBot


class QuickStatementsBot(WikidataEntityBot):

    decimal_pattern = r'[+-]?(?:[1-9]\d*|0)(?:\.\d+)?'

    def __init__(self, generator, **kwargs):
        self.available_options.update({
            'always': True,
            'noresolve': False,
        })
        super().__init__(**kwargs)
        self.generator = generator
        self.globeR = re.compile(r'@({0})/({0})'.format(self.decimal_pattern))
        self.quantity_errR = re.compile(
            r'({0})(?:~({0}))?(?:U([1-9]\d*))?'
            .format(self.decimal_pattern))
        self.quantity_boundsR = re.compile(
            r'({0})(?:\[({0}),({0})\])(?:U([1-9]\d*))?'
            .format(self.decimal_pattern))
        self.commentR = re.compile(r' */\*(.*?)\*/$')
        self.entity_types = frozenset(
            key for key, val in Property.value_types.items()
            if val == 'wikibase-entityid')
        self.attr_mapping = {
            'L': {'key': 'labels'},
            'D': {'key': 'descriptions'},
            'A': {
                'key': 'aliases',
                'callback': lambda data, key, value: data.setdefault(
                    key, []).append(value)
            },
            'S': {'key': 'sitelinks'},
        }
        self.last = None  # the last created item (using CREATE)
        self._current = None  # the last treated entity

    @property
    def current(self):
        return self._current

    @current.setter
    def current(self, new):
        self._current = new

    @staticmethod
    def valid_text_literal(text, allow_empty=False):
        bound = 3 - allow_empty
        if text.startswith('"') and text.endswith('"') and len(text) >= bound:
            return text[1:-1]
        else:
            return None

    def parse_entity(self, value):
        if value == 'LAST':
            return self.last
        else:
            return self.repo.get_entity_for_entity_id(value)

    def _set_target(self, snak, value):
        if value in ('somevalue', 'novalue'):
            snak.setSnakType(value)
            return True

        def invalid_report():
            pywikibot.warning('Invalid value "{}" for {} datatype'
                              .format(value, snak.type))

        if snak.type in self.entity_types:
            target = self.parse_entity(value)
            if target is None:
                pywikibot.warning('"LAST" magic word used without "CREATE"')
            else:
                snak.setTarget(target)
                return True
        elif snak.type == 'quantity':
            match = self.quantity_errR.fullmatch(value)
            if match:
                amount, error, unit = match.groups()
            else:
                match = self.quantity_boundsR.fullmatch(value)
                if match:
                    groups = list(match.groups())
                    unit = groups.pop()
                    amount, lower, upper = map(Decimal, groups)
                    if lower > upper:
                        error = amount - lower, upper - amount
                    else:
                        error = upper - amount, amount - lower
            if match:
                if unit:
                    unit = pywikibot.ItemPage(self.repo, 'Q' + unit)
                quantity = WbQuantity(amount, unit, error, site=self.repo)
                snak.setTarget(quantity)
                return True
            else:
                invalid_report()
        elif snak.type == 'time':
            iso, _, prec = value.rpartition('/')
            if iso:
                time = WbTime.fromTimestr(
                    iso, precision=int(prec), site=self.repo)
                snak.setTarget(time)
                return True
            else:
                invalid_report()
        elif snak.type in ('string', 'external-id', 'url', 'math'):
            literal = self.valid_text_literal(value)
            if literal:
                snak.setTarget(literal)
                return True
            else:
                invalid_report()
        elif snak.type == 'commonsMedia':
            literal = self.valid_text_literal(value)
            if literal:
                image_repo = self.repo.image_repository()
                snak.setTarget(pywikibot.FilePage(image_repo, literal))
                return True
            else:
                invalid_report()
        # todo: elif snak.type in ('geo-shape', 'tabular-data'):
        elif snak.type == 'monolingualtext':
            lang, _, text = value.partition(':')
            literal = self.valid_text_literal(text)
            if literal:
                monotext = WbMonolingualText(literal, lang)
                snak.setTarget(monotext)
                return True
            else:
                invalid_report()
        elif snak.type == 'globe-coordinate':
            match = self.globeR.fullmatch(value)
            if match:
                coord = Coordinate(
                    *map(float, match.groups()),
                    precision=1e-4,  # hardcoded as in claimit.py
                    site=self.repo)
                snak.setTarget(coord)
                return True
            else:
                invalid_report()
        else:
            pywikibot.warning('"{}" datatype is not supported yet'
                              .format(snak.type))

        return False

    def set_target(self, snak, value):
        try:
            return self._set_target(snak, value)
        except pywikibot.data.api.APIError:
            pass  # warning was printed down the stack
        except WikiBaseError as e:
            pywikibot.error(e)
        return False

    def handle_line(self, line):
        comment_match = self.commentR.search(line)
        if comment_match:
            summary = comment_match.group(1)
            line = line[:comment_match.start()]
        else:
            summary = None

        split = line.split('\t')
        first = split[0]
        if first != 'CREATE' and (len(split) < 3 or len(split) % 2 == 0):
            pywikibot.warning('Invalid line: {}'.format(line))
            return

        if first == 'MERGE':
            entity_from, entity_to = map(self.parse_entity, split[1:3])
            entity_from.mergeInto(entity_to, summary=summary)
            return

        minus = False
        if first == 'CREATE':
            # the orig. QS only supports creating items
            self.last = item = pywikibot.ItemPage(self.repo)
        elif first == 'LAST':
            item = self.last
            if self.last is None:
                pywikibot.warning('"LAST" magic word used without "CREATE"')
                return
        else:
            minus = first.startswith('-')
            if minus:
                first = first[1:]
            try:
                item = self.repo.get_entity_for_entity_id(first)
            except NoWikibaseEntityError as e:
                pywikibot.error(e)
                return

        # TODO: this is currently unused but might become handy
        # when consecutive edits to an item can be squashed
        self.current = item

        pred = split[1]
        if pred.startswith(tuple(self.attr_mapping)):
            literal = self.valid_text_literal(split[2], allow_empty=True)
            if literal is None:
                pywikibot.warning('Invalid literal for {}-command'
                                  .format(pred))
                return
            init, *lang = pred  # split init. char and lang. code
            key = self.attr_mapping[init]['key']
            callback = self.attr_mapping[init].get(
                'callback',
                lambda data, key, value: data.update({key: value}))
            callback(getattr(self.current, key), lang, literal)
            self.current.editEntity(summary=summary)
            return

        # assume the predicate is a property
        # fixme: ideally, validation would be done upstream
        # claim = pywikibot.Claim(self.repo, prop)
        try:
            obj = self.repo.get_entity_for_entity_id(pred)
        except WikiBaseError as e:
            pywikibot.error(e)
            return

        if not isinstance(obj, pywikibot.PropertyPage):
            pywikibot.warning('{} is not a valid property id'.format(pred))
            return

        claim = obj.newClaim()
        del obj
        if not self.set_target(claim, split[2].strip()):
            return

        add_new = True
        if not self.opt['noresolve']:
            for other in self.current.claims.get(pred, []):
                if other.same_as(claim, ignore_rank=True, ignore_quals=True,
                                 ignore_refs=True):
                    claim = other
                    add_new = False
                    break

        if minus:
            if add_new:
                pywikibot.warning('No matching claim to remove found')
            else:
                self.current.removeClaim(claim, summary=summary)
            return

        if add_new:
            self.current.addClaim(claim, summary=summary)

        qualifiers = []
        references = []
        for prop, value in zip(split[3::2], split[4::2]):
            if prop.startswith('S'):
                collection = references
                prop = 'P' + prop[1:]
                key = 'is_reference'
            else:
                collection = qualifiers
                key = 'is_qualifier'
            # fixme: ideally, validation would be done upstream
            # snak = pywikibot.Claim(self.repo, prop, **{key: True})
            try:
                obj = self.repo.get_entity_for_entity_id(prop)
            except WikiBaseError as e:
                pywikibot.error(e)
                return

            if not isinstance(obj, pywikibot.PropertyPage):
                pywikibot.warning('{} is not a valid property id'.format(prop))
                return

            snak = obj.newClaim(**{key: True})
            del obj
            ok = self.set_target(snak, value.strip())
            if not ok:
                return
            collection.append(snak)

        for qual in qualifiers:
            if qual not in chain(*claim.qualifiers.values()):
                claim.addQualifier(qual)
        if references:
            # TODO: check for duplicity
            claim.addSources(references)

    def run(self):
        for line in self.generator:
            line = line.rstrip()
            if line:
                self.handle_line(line)


def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    for arg in local_args:
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    with open(options.pop('file'), 'r', encoding='utf-8') as file:
        bot = QuickStatementsBot(file, site=site, **options)
        bot.run()


if __name__ == '__main__':
    main()
