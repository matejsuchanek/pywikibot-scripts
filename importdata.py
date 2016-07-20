# -*- coding: utf-8  -*-
import pywikibot
import re

from datetime import datetime

site = pywikibot.Site('wikidata', 'wikidata')
repo = site.data_repository()

with open('..\data.txt', 'r') as file_data:
    for line in file_data:
        split = re.split(r"\t", line)
        item = pywikibot.ItemPage(site, split[0])
        item.get()
        hasNewClaim = False
        upToDateClaim = None
        count = int(split[1])
        if item.claims.has_key('P1082'):
            for claim in item.claims['P1082']:
                if claim.getRank() == 'preferred':
                    upToDateClaim = claim
                    upToDateClaim.setRank('normal')
                if count == int(claim.getTarget().amount):
                    if claim.qualifiers.has_key('P1539'):
                        hasNewClaim = True
                        break

        if hasNewClaim is True:
            continue

        newClaim = pywikibot.Claim(repo, 'P1082')
        newClaim.setTarget(pywikibot.WbQuantity(count))
        newClaim.setRank('preferred')

        data = {"claims":[newClaim.toJSON()]}
        data['claims'][0]['qualifiers'] = {}
        data['claims'][0]['references'] = [{'snaks':{}}]

        newClaim_date = pywikibot.Claim(repo, 'P585', isQualifier=True)
        newClaim_date.setTarget(pywikibot.WbTime(year=2016, month=1, day=1))
        data['claims'][0]['qualifiers']['P585'] = [newClaim_date.toJSON()]

        #newClaim_method = pywikibot.Claim(repo, 'P459', isQualifier=True)
        #newClaim_method.setTarget(pywikibot.ItemPage(site, ''))
        #data['claims'][0]['qualifiers']['P459'] = [newClaim_method.toJSON()]

        newClaim_criter = pywikibot.Claim(repo, 'P1013', isQualifier=True)
        newClaim_criter.setTarget(pywikibot.ItemPage(site, 'Q2641256'))
        data['claims'][0]['qualifiers']['P1013'] = [newClaim_criter.toJSON()]

        newClaim_men = pywikibot.Claim(repo, 'P1540', isQualifier=True)
        newClaim_men.setTarget(pywikibot.WbQuantity(int(split[2])))
        data['claims'][0]['qualifiers']['P1540'] = [newClaim_men.toJSON()]

        newClaim_women = pywikibot.Claim(repo, 'P1539', isQualifier=True)
        newClaim_women.setTarget(pywikibot.WbQuantity(int(split[3])))
        data['claims'][0]['qualifiers']['P1539'] = [newClaim_women.toJSON()]

        ref_item = 'Q24560797'
        ref = pywikibot.Claim(repo, 'P248', isReference=True)
        ref.setTarget(pywikibot.ItemPage(site, ref_item))
        data['claims'][0]['references'][0]['snaks']['P248'] = [ref.toJSON()]

        now = datetime.now()
        access_date = pywikibot.Claim(repo, 'P813', isReference=True)
        access_date.setTarget(pywikibot.WbTime(year=now.year, month=now.month, day=now.day))
        data['claims'][0]['references'][0]['snaks']['P813'] = [access_date.toJSON()]

        if upToDateClaim is not None:
            data['claims'].append(upToDateClaim.toJSON())

        item.editEntity(data, summary=u'Adding [[Property:P1082]]: %s, based on data from [[Q3504917]], see [[%s]]' % (count, ref_item))
