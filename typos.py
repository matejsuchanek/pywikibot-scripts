# -*- coding: utf-8  -*-
import datetime
import pywikibot
import re

from pywikibot import pagegenerators
from pywikibot import textlib

start = datetime.datetime.now()
site = pywikibot.Site('cs', 'wikipedia')

"""Is it mandatory to apply the rule search engine was queried for?"""
quick_mode = True
#quick_mode = False

typoRules = []
# default
exceptions = ['category', 'comment', 'gallery', 'header', 'hyperlink', 'interwiki',
              'invoke', 'pre', 'property', 'source', 'startspace', 'template']
# tags
exceptions += ['ce', 'code', 'graph', 'imagemap', 'math', 'nowiki', 'poem',
               'score', 'section', 'timeline']
# regexes ('target-part' of a wikilink; quotation marks; italics)
exceptions += [re.compile(r'\[\[[^\[\]\|]+[\|\]]'), re.compile(ur'„[^“]+“'),
               re.compile(r"((?<!\w)\"|(?<!')'')(?:(?!\1).)+\1", re.M | re.U)]

pywikibot.output(u'Loading typos')
WPCTypos = pywikibot.Page(site, u'Wikipedie:WPCleaner/Typo')
content = WPCTypos.get()

false_positives = pywikibot.Page(site, u'Wikipedie:WPCleaner/Typo/False')
false_positives.get()

for template, fielddict in textlib.extract_templates_and_params(content):
    if template.lower() == 'typo':
        if 'auto' not in fielddict.keys():
            continue
        if '3' in fielddict.keys():
            continue
        ok = True
        insource = True
        query = None
        find = None
        replace = None
        for pairs in fielddict.items():
            if pairs[0] == '1':
                find = re.sub(r'</?nowiki>', '', pairs[1])
                if re.search(r'\(\?<[=!][^\(\)]*([\^\$\(\{\}\+\*\?\|]|\\[1-9b])', find):
                    ok = False # only fixed-width look-behind
                    break
            elif pairs[0] == '2':
                replace = re.sub(r'</?nowiki>', '', pairs[1])
                replace = re.sub(r'\$([1-9])', r'\\\1', replace)
            elif pairs[0] == 'hledat':
                if pairs[1] != '':
                    query = pairs[1].replace('{{!}}', '|')
            elif pairs[0] == 'insource':
                insource = pairs[1] != 'ne'
            elif pairs[0] == 'auto':
                if pairs[1] != 'ano':
                    ok = False
                    break
        if ok is True:
            if query is not None and insource is True:
                query = 'insource:/%s/i' % query
            typoRules.append(
                (query, find, replace)
            )

pywikibot.output(u'%s typos loaded' % len(typoRules))

def replace_and_summary(match, replacement, replaced):
    old = match.group(0)
    new = replacement
    i = 0
    for group in match.groups(''):
        i += 1
        new = new.replace('\%s' % i, group)
    if old == new:
        pywikibot.output(u'No replacement done in "%s"' % old)
    else:
        fragment = u' → '.join([re.sub(r'(^ | $)', r'_', j) for j in [old, new]])
        if fragment.lower() not in [j.lower() for j in replaced]:
            replaced.append(fragment)
    return new

for rule in typoRules:
    if rule[0] is None:
        continue
    pywikibot.output(u'Doing %s' % rule[0])
    i = j = 0.0
    for page in pagegenerators.SearchPageGenerator(rule[0], namespaces=[0], site=site):
        if u'[[%s]]' % page.title() in false_positives.text:
            pywikibot.output(u'%s is on whitelist' % page.title())
            continue
        if re.search(rule[1], page.title(), re.U) is not None:
            pywikibot.output(u'Expression matched title: %s' % page.title())
            continue
        replaced = []
        text = page.get()
        callback = lambda match: replace_and_summary(match, rule[2], replaced)
        text = textlib.replaceExcept(text, re.compile(rule[1], re.U), callback, exceptions, site=site)
        i += 1
        if text == page.text:
            if quick_mode is True:
                continue
        else:
            j += 1
        for sub_rule in typoRules:
            if re.search(sub_rule[1], page.title(), re.U) is not None:
                continue
            callback = lambda match: replace_and_summary(match, sub_rule[2], replaced)
            text = textlib.replaceExcept(text, re.compile(sub_rule[1], re.U), callback, exceptions, site=site)
        if len(replaced) > 0:
            page.text = text
            page.save(summary=u'oprava překlepů: %s' % ', '.join(replaced), async=True)
    if i > 0.0 and j / i < 0.5:
        pywikibot.output(u'Inaccurate query {} ({} %)'.format(rule[0], int((j / i) * 100)))

end = datetime.datetime.now()

pywikibot.output('Complete! Took %s seconds' % (end - start).total_seconds())
