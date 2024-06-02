#!/usr/bin/python
from datetime import datetime

import pywikibot

pywikibot.handle_args()

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

path = pywikibot.input('Path to file: ')
date = pywikibot.WbTime(year=2024, month=1, day=1, site=repo)

ref_item = 'Q125984191'

with open(path, 'r', encoding='utf-8') as file_data:
    next(file_data)  # header
    for line in file_data:
        if not line:
            continue
        split = line.split('\t')
        item = pywikibot.ItemPage(repo, split[0])
        hasNewClaim = False
        upToDateClaims = []
        count = int(split[1])
        for claim in item.claims.get('P1082', []):
            if claim.getRank() == 'preferred':
                claim.setRank('normal')
                upToDateClaims.append(claim)
            if (claim.qualifiers.get('P585')
                    and claim.qualifiers['P585'][0].target_equals(date)):
                hasNewClaim = True
                break

        if hasNewClaim is True:
            continue

        newClaim = pywikibot.Claim(repo, 'P1082')
        newClaim.setTarget(pywikibot.WbQuantity(count, site=repo))
        newClaim.setRank('preferred')

        newClaim_date = pywikibot.Claim(repo, 'P585', is_qualifier=True)
        newClaim_date.setTarget(date)
        newClaim.addQualifier(newClaim_date)

        newClaim_criter = pywikibot.Claim(repo, 'P1013', is_qualifier=True)
        newClaim_criter.setTarget(pywikibot.ItemPage(repo, 'Q2641256'))
        newClaim.addQualifier(newClaim_criter)

        newClaim_men = pywikibot.Claim(repo, 'P1540', is_qualifier=True)
        newClaim_men.setTarget(pywikibot.WbQuantity(int(split[2]), site=repo))
        newClaim.addQualifier(newClaim_men)

        newClaim_women = pywikibot.Claim(repo, 'P1539', is_qualifier=True)
        newClaim_women.setTarget(pywikibot.WbQuantity(int(split[3]), site=repo))
        newClaim.addQualifier(newClaim_women)

        ref = pywikibot.Claim(repo, 'P248', is_reference=True)
        ref.setTarget(pywikibot.ItemPage(repo, ref_item))

        now = datetime.now()
        access_date = pywikibot.Claim(repo, 'P813', is_reference=True)
        access_date.setTarget(pywikibot.WbTime(year=now.year, month=now.month,
                                               day=now.day, site=repo))
        newClaim.addSources([ref, access_date])

        data = {'claims':[newClaim.toJSON()]}
        for upToDateClaim in upToDateClaims:
            data['claims'].append(upToDateClaim.toJSON())

        item.editEntity(
            data, asynchronous=True,
            summary=f'Adding [[Property:P1082]]: {count} per data from '
                    f'[[Q3504917]], see [[{ref_item}]]')
