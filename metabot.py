# -*- coding: utf-8  -*-
import datetime
import pywikibot
import re

from pywikibot import textlib

site = pywikibot.Site('wikidata','wikidata')
repo = site.data_repository()

template_metadata = 'property documentation'
template_regex = 'constraint:format'

regexes = {
    u'arrow': r"\s*(?: (?:<|'')+?(?:\{\{P\|P?\d+\}\}|[A-Za-z ]+)(?:''|>)+?=? |(?<=\d)\|[A-Za-z ]+\|(?=Q?\d)|→|\x859|[=\-]+>|\s[=-]+\s|\s>|:\s)\s*",
    u'commonsMedia': r"\b[Ff]ile:([^[\]|{}]*\.\w{3,})\b",
    #u'coordinates': r"",
    #u'monolingualtext': r"",
    #u'quantity': r"(-?\d(?:[\d\.,]*\d)?\b)",
    u'split': r"\s*(?:(?:<[^>\w]*br(?!\w)[^>]*> *|(?:^|\n+)[:;*#]+){1,2}|\s;\s|(?<=\d\}\}), +(?=<?\{\{[Qq]\|))\s*", # FIXME: both <br> and wikisyntax
    #u'time': r"",
    u'url': r"(https?://\S+)(?<!\])",
    u'wikibase-item': r"\b[Qq]\W*([1-9]\d*)\b",
    u'wikibase-property': r"\b[Pp]\W*([1-9]\d*)\b"
}

def summary(prop, value, item):
    if isinstance(value, pywikibot.ItemPage):
        value = u'[[%s]]' % value.title()
    elif isinstance(value, pywikibot.FilePage):
        value = u'[[c:File:%s|%s]]' % (value.title(), value.title())
    elif isinstance(value, pywikibot.PropertyPage):
        value = u'[[%s|%s]]' % (value.title(), value.getID())
    else:
        value = u"'%s'" % value
    rev_id = item.toggleTalkPage().latest_revision_id
    return u'Importing "[[Property:%s]]: %s" from [[Special:PermaLink/%s|talk page]]' % (prop, value, rev_id)

def getregexfromitem(item):
    if 'P1793' in item.claims.keys():
        for claim in item.claims['P1793']:
            return claim.getTarget()
    return

def getformatterregex():
    if 'formatter' not in regexes.keys():
        prop = pywikibot.PropertyPage(repo, 'P1630')
        prop.get()
        regexes['formatter'] = getregexfromitem(prop)
    return re.compile(regexes['formatter'])

def formatter(item, textvalue):
    if item.type not in ['commonsMedia', 'external-id', 'string']:
        pywikibot.output(u'Redundant to harvest formatter URL for "%s" datatype' % item.type)
        return
    if 'P1630' in item.claims.keys():
        pywikibot.output(u'Formatter URL for "%s" already exists' % item.title())
        return

    for match in getformatterregex().findall(textvalue):
        claim = pywikibot.Claim(repo, 'P1630')
        claim.setTarget(match)
        item.editEntity({"claims":[claim.toJSON()]}, summary=summary('P1630', match, item))
        item.get()

def subject_item(item, textvalue):
    if 'P1629' in item.claims.keys():
        pywikibot.output(u'Subject item for "%s" already exists' % item.title())
        return

    for itemid in re.findall(r'\b[Qq][1-9]\d*\b', textvalue):
        claim = pywikibot.Claim(repo, 'P1629')
        target = pywikibot.ItemPage(repo, itemid.upper())
        claim.setTarget(target)
        item.editEntity({"claims":[claim.toJSON()]}, summary=summary('P1629', target, item))
        item.get(True)

        rev_id = item.latest_revision_id
        data = { # FIXME: T113174
            "claims":[
                {
                    "mainsnak":{
                        "snaktype":"value",
                        "property":"P1687",
                        "datavalue":{
                            "value":{
                                u'entity-type':u'property',
                                u'numeric-id':item.getID(numeric=True)
                            },
                            "type":u"wikibase-entityid"
                        }
                    },
                    "type":"statement",
                    "rank":"normal"
                }
            ]
        }
        #inverse_claim = pywikibot.Claim(repo, u'P1687')
        #target = pywikibot.PropertyPage(repo, item.title())
        #inverse_claim.setTarget(target)
        target.editEntity(data, summary=u"Adding inverse to an [[Special:Diff/%s#P1629|imported claim]]" % rev_id)

def source(item, textvalue):
    for match in re.split(regexes['split'], textvalue):
        if match == '':
            continue
        regex = r'(?:\[' + regexes['url'] + r'(?: [^\]]*)?\]|^' + regexes['url'] + '$)'
        searchObj = re.search(regex, match)
        if searchObj is None or (searchObj.group(1) is None and searchObj.group(2) is None):
            pywikibot.output(u'Could not match source "%s"' % match)
            continue

        target = searchObj.group(1) or searchObj.group(2)
        if any(claim.target_equals(target) for claim in item.claims.get('P1896', [])):
            pywikibot.output(u'"%s" already has "%s" as the source' % (item.title(), target))
            continue

        claim = pywikibot.Claim(repo, 'P1896')
        claim.setTarget(target)
        item.editEntity({"claims":[claim.toJSON()]},
			summary=summary('P1896', target, item))
        item.get(True)

def example(item, textvalue):
    if any(claim.target_equals(pywikibot.ItemPage(repo, 'Q15720608')) for claim in item.claims.get('P31', [])):
           pywikibot.output(u'%s is for qualifier use' % item.title())
           return

    if item.type in ['external-id', 'string']:
        regex = getregexfromitem(item)
        if regex is None:
            pywikibot.output(u'Regex for "%s" not found' % item.title())
            return

        formatter = None
        if 'P1630' in item.claims.keys():
            for claim in item.claims['P1630']:
                if claim.snaktype != 'value':
                    continue
                searchObj = getformatterregex().search(claim.getTarget())
                if searchObj is None:
                    pywikibot.output(u'Found wrongly formatted formatter URL for "%s"' % item.title())
                    continue

                formatter = searchObj.group()
                break

        if formatter is None:
            if item.type == "external-id":
                pywikibot.output(u'Info: No formatter found for "%s"' % item.title())
            regex = '^(%s)$' % regex
        else:
            regex = re.sub(r'((?:^|[^\\])(?:\\\\)*)\(', r'\1(?:', regex) # no capture groups
            regex = r'(?:' + re.sub(r'\\\$1', r'(%s)' % regex, re.escape(formatter)) + r'|(?:^["\'<]?|\s)(' + regex + r')(?:["\'>]?$|\]))'

    elif item.type == "commonsMedia":
        regex = getregexfromitem(item)
        if regex is None:
            regex = regexes[item.type]
        else:
            flags = 0
            if regex.startswith('(?i)'):
                regex = regex[4:]
                flags |= re.I
            regex = re.sub(r'((?:^|[^\\])(?:\\\\)*)\(', r'\1(?:', regex) # no capture groups
            regex = re.compile(r'([Ff]ile:%s)' % regex, flags)
    else:
        if item.type in regexes.keys():
            regex = regexes[item.type]
        else:
            pywikibot.output(u'"%s" is not supported datatype for matching examples' % item.type)
            return

    for match in re.split(regexes['split'], textvalue):
        if match == '':
            continue
        splitObj = re.split(regexes['arrow'], match)
        if len(splitObj) < 2:
            pywikibot.output(u'Example pair not recognized in "%s"' % match)
            continue

        splitObj = [splitObj[i] for i in [0, -1]]
        searchObj = re.search(regexes['wikibase-item'], splitObj[0])
        if searchObj is None:
            pywikibot.output(u'No item id found in "%s"' % splitObj[0])
            continue

        item_match = 'Q%s' % searchObj.group(1)
        item2 = pywikibot.ItemPage(repo, item_match)
        if any(claim.target_equals(item2) for claim in item.claims.get('P1855', [])):
            pywikibot.output(u'There is already one example with "%s"' % item_match)
            continue

        for qual_match in re.finditer(regex, splitObj[1]):
            qual_target = None
            for string in qual_match.groups():
                if string:
                    qual_target = string
                    break
            else:
                pywikibot.output(u'Failed on matching target from "%s"' % splitObj[1])
                break

            if item.type == "wikibase-item":
                qual_target = pywikibot.ItemPage(repo, 'Q%s' % qual_target)
                while qual_target.isRedirectPage():
                    qual_target = qual_target.getRedirectTarget()
            elif item.type == "wikibase-property": # FIXME: T113174
                qual_target = pywikibot.PropertyPage(repo, 'P%s' % qual_target)
            elif item.type == "commonsMedia":
                commons = pywikibot.Site("commons", "commons")
                imagelink = pywikibot.Link(qual_target, source=commons,
                                           defaultNamespace=6)
                qual_target = pywikibot.FilePage(imagelink)
                if not qual_target.exists():
                    pywikibot.output(u'"%s" doesn\'t exist' % qual_target.title())
                    break
                while qual_target.isRedirectPage():
                    qual_target = pywikibot.FilePage(qual_target.getRedirectTarget())
            elif item.type == "quantity":
                num = float(qual_target.replace(',', ''))
                if num.is_integer():
                    num = int(num)
                qual_target = pywikibot.WbQuantity(num)

            target = pywikibot.ItemPage(repo, item_match)
            while target.isRedirectPage():
                target = target.getRedirectTarget()

            claim = pywikibot.Claim(repo, 'P1855')
            claim.setTarget(target)
            qualifier = item.newClaim(isQualifier=True)
            qualifier.setTarget(qual_target)
            data = {"claims":[claim.toJSON()]}
            data['claims'][0]['qualifiers'] = {item.getID():[qualifier.toJSON()]}
            item.editEntity(data, summary=summary('P1855', target, item))
            item.get(True)
            break # only the first value match

func_dict = {
    u'formatter URL': formatter,
    u'subject item': subject_item,
    u'source': source,
    u'example': example
}

start = int(pywikibot.input("Start: "))
end = int(pywikibot.input("End: ") or start)

start_time = datetime.datetime.now()

for i in range(start, end + 1): # fixme: pagegenerators?
    item = pywikibot.PropertyPage(repo, u'P%s' % i)
    pywikibot.output(u'Looking up for "%s"' % item.title())
    if not item.exists():
        pywikibot.output(u'"%s" doesn\'t exist, skipping to the next one' % item.title())
        continue

    page = item.toggleTalkPage()
    if not page.exists():
        pywikibot.output(u'"%s" doesn\'t exist, skipping to the next one' % page.title())
        continue

    templates = textlib.extract_templates_and_params(page.get())
    fields = None
    for template, fielddict in templates:
        if template.lower() == template_metadata:
            fields = fielddict
            break
    else:
        pywikibot.output(u'Template "%s" not found' % template_metadata)
        continue

    item.get()

    if item.type in ['commonsMedia', 'external-id', 'string', 'url'] and 'P1793' not in item.claims.keys():
        for template, fielddict in templates:
            if template.lower() == template_regex:
                pywikibot.output('Found field "regex"')
                for param, value in fielddict.items():
                    if param == 'pattern':
                        regex = textlib.removeDisabledParts(value, include=['nowiki'])
                        regex = re.sub('</?nowiki>', '', regex)
                        claim = pywikibot.Claim(repo, 'P1793')
                        claim.setTarget(regex.strip())
                        try:
                            item.editEntity({"claims":[claim.toJSON()]},
                                            summary=summary('P1793', regex, item))
                        except pywikibot.data.api.APIError as exc:
                            pywikibot.warning(exc)
                        else:
                            item.get(True)
                        break
                #else:
                break
        #else:

    for func_key in func_dict:
        for field, field_value in fields.items():
            field = field.strip()
            if func_key == field:
                field_value = textlib.removeDisabledParts(field_value).strip()
                if field_value in ['', '-']:
                    break
                pywikibot.output(u'Found field "%s"' % field)
                try:
                    func_dict[func_key](item, field_value)
                except pywikibot.data.api.APIError as exc:
                    pywikibot.warning(exc)
                break
        #else:
    #else:
        #page.touch()

end_time = datetime.datetime.now()

pywikibot.output("Complete! Took %s seconds" % (end_time - start_time).total_seconds())
