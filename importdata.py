# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re

from datetime import datetime

pywikibot.handle_args()

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

direct = pywikibot.input('File directory: ')
date = pywikibot.WbTime(year=2017, month=1, day=1, site=repo)

ref_item = 'Q29678797'

with open(direct, 'r') as file_data:
    for line in file_data:
        split = line.split('\t')
        item = pywikibot.ItemPage(repo, split[0])
        item.get()
        hasNewClaim = False
        upToDateClaims = []
        count = int(split[1])
        for claim in item.claims.get('P1082', []):
            if claim.getRank() == 'preferred':
                claim.setRank('normal')
                upToDateClaims.append(claim)
            if claim.qualifiers.get('P585') and claim.qualifiers['P585'][0].target_equals(date):
                hasNewClaim = True
                break

        if hasNewClaim is True:
            continue

        newClaim = pywikibot.Claim(repo, 'P1082')
        newClaim.setTarget(pywikibot.WbQuantity(count, site=repo))
        newClaim.setRank('preferred')

        data = {'claims':[newClaim.toJSON()]}
        data['claims'][0]['qualifiers'] = {}
        data['claims'][0]['references'] = [{'snaks':{}}]

        newClaim_date = pywikibot.Claim(repo, 'P585', isQualifier=True)
        newClaim_date.setTarget(date)
        data['claims'][0]['qualifiers']['P585'] = [newClaim_date.toJSON()]

        newClaim_criter = pywikibot.Claim(repo, 'P1013', isQualifier=True)
        newClaim_criter.setTarget(pywikibot.ItemPage(repo, 'Q2641256'))
        data['claims'][0]['qualifiers']['P1013'] = [newClaim_criter.toJSON()]

        newClaim_men = pywikibot.Claim(repo, 'P1540', isQualifier=True)
        newClaim_men.setTarget(pywikibot.WbQuantity(int(split[2]), site=repo))
        data['claims'][0]['qualifiers']['P1540'] = [newClaim_men.toJSON()]

        newClaim_women = pywikibot.Claim(repo, 'P1539', isQualifier=True)
        newClaim_women.setTarget(pywikibot.WbQuantity(int(split[3]), site=repo))
        data['claims'][0]['qualifiers']['P1539'] = [newClaim_women.toJSON()]

        ref = pywikibot.Claim(repo, 'P248', isReference=True)
        ref.setTarget(pywikibot.ItemPage(repo, ref_item))
        data['claims'][0]['references'][0]['snaks']['P248'] = [ref.toJSON()]

        now = datetime.now()
        access_date = pywikibot.Claim(repo, 'P813', isReference=True)
        access_date.setTarget(pywikibot.WbTime(year=now.year, month=now.month, day=now.day, site=repo))
        data['claims'][0]['references'][0]['snaks']['P813'] = [access_date.toJSON()]

        for upToDateClaim in upToDateClaims:
            data['claims'].append(upToDateClaim.toJSON())

        item.editEntity(data, asynchronous=True,
                        summary='Adding [[Property:P1082]]: %s, '
                        'based on data from [[Q3504917]], see [[%s]]' % (
                            count, ref_item))
