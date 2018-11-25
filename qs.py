# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re

from pywikibot import Coordinate, WbMonolingualText, WbQuantity, WbTime
from .wikidata import WikidataEntityBot


class QuickStatementsBot(WikidataEntityBot):

    def __init__(self, file, **kwargs):
        self.availableOptions({
            'always': True,
        })
        super(QuickStatementsBot, self).__init__(**kwargs)
        self.file = file

    def teardown(self):
        self.file.close()
        super(QuickStatementsBot, self).teardown()

    def set_target(self, snak, value):
        if value in ('somevalue', 'novalue'):
            snak.setSnakType(value)
            return True
        if snak.type == 'wikibase-item':
            snak.setTarget(pywikibot.ItemPage(self.repo, value))
            return True
        elif snak.type == 'quantity':
            match = re.fullmatch(
                r'(\d+(?:\.\d+)?)(?:~(\d+(?:\.\d+)?))?(?:U(\d+))?', value)
            if match:
                amount, error, unit = match.groups()
                if unit:
                    unit = pywikibot.ItemPage(self.repo, 'Q' + unit)
                quantity = WbQuantity(amount, unit, error, site=self.repo)
                snak.setTarget(quantity)
                return True
        elif snak.type == 'time':
            iso, _, prec = value.rpartition('/')
            if iso:
                time = WbTime.fromTimestr(
                    iso, precision=int(prec), site=self.repo)
                snak.setTarget(time)
                return True
        elif snak.type in ('string', 'external-id', 'url'):
            if value.startswith('"') and value.endswith('"'):
                snak.setTarget(value[1:-1])
                return True
        elif snak.type == 'monolingualtext':
            lang, _, text = value.partition(':')
            if text and text.startswith('"') and text.endswith('"'):
                monotext = WbMonolingualText(text[1:-1], lang)
                snak.setTarget(monotext)
                return True
        elif snak.type == 'globe-coordinate':
            match = re.fullmatch(r'@(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)', value)
            if match:
                coord = Coordinate(*map(float, match.groups()), site=self.repo)
                snak.setTarget(coord)
                return True
        return False

    def run(self):  
        for line in self.file.readlines():
            split = line.split('\t')
            if len(split) < 3 or len(split) % 2 == 0:
                continue

            try:
                item = pywikibot.ItemPage(self.repo, split[0])
            except Exception as e:
                pywikibot.error(e)
                continue

            try:
                claim = pywikibot.Claim(self.repo, split[1])
            except Exception:
                pywikibot.error(e)
                continue

            if not self.set_target(claim, split[2].strip()):
                continue

            qualifiers = []
            references = []
            for prop, value in zip(split[3::2], split[4::2]):
                if prop.startswith('S'):
                    data = references
                    prop = 'P' + prop[1:]
                    key = 'is_reference'
                else:
                    data = qualifiers
                    key = 'is_qualifier'
                snak = pywikibot.Claim(self.repo, prop, **{key: True})
                if self.set_target(snak, value.strip()):
                    data.append(snak)
            item.addClaim(claim)
            for q in qualifiers:
                claim.addQualifier(q)
            if references:
                claim.addSources(references)


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

    file = open(options.pop('file'), 'r')
    bot = QuickStatementsBot(file, site=site, **options)
    bot.run()


if __name__ == '__main__':
    main()
