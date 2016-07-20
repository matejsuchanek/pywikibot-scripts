# -*- coding: utf-8  -*-
import datetime
import pywikibot
import re

from pywikibot import pagegenerators
from pywikibot import textlib

start = datetime.datetime.now()

cswiki = pywikibot.Site('cs', 'wikipedia')
commons = pywikibot.Site('commons', 'commons')
repo = cswiki.data_repository()

category = pywikibot.Category(cswiki, u'Údržba:Commonscat není na Wikidatech')
gen_articles = pagegenerators.CategorizedPageGenerator(category, namespaces=0)
gen_subcats = pagegenerators.SubCategoriesPageGenerator(category)
gen_combined = pagegenerators.CombinedPageGenerator([gen_articles, gen_subcats])

deferred_touch = []

def def_touch(def_page):
    pywikibot.output("Deferred touching %s" % def_page.title())
    def_page.touch(botflag=True)

for page in pagegenerators.WikibaseItemFilterPageGenerator(gen_combined):
    item = pywikibot.ItemPage.fromPage(page)
    item.get()
    if item.claims.has_key('P373'):
        deferred_touch.append(page)
        continue

    page_text = page.get()
    extra = textlib.extract_templates_and_params(page_text, remove_disabled_parts=True, strip=True)
    for template, fielddict in textlib.extract_templates_and_params(page.get()):
        if template.lower() == 'commonscat':
            has_param = False
            cat_name = page.title(withNamespace=False)
            if '1' in fielddict.keys():
                for pairs in fielddict.items():
                    if pairs[0] == '1':
                        cat_name = pairs[1].strip()
                        if cat_name != '':
                            has_param = True
                        else:
                            cat_name = page.title(withNamespace=False)
                        break

            commons_cat = pywikibot.Category(commons, cat_name)
            if not commons_cat.exists():
                regex = r'(?:[\n\r]?|^)(?:\* *)?\{\{ *[Cc]ommons(?:cat|[_ ]?category) *'
                if has_param is True:
                    regex += r'\| *' + re.escape(cat_name).replace('\ ', '[_ ]')
                regex += r'[^\}]*\}\}'
                page_replaced_text = re.sub(regex, '', page_text)
                if page_replaced_text == page_text:
                    pywikibot.output(u'No replacement done in %s' % page.title())
                else:
                    page_replaced_text = re.sub(ur'[\n\r]+==+\ ?Externí\ odkazy\ ?==+\ *[\n\r]+(==|\{\{(?:DEFAULTSORT:|[Pp]ahýl|[Pp]osloupnost|[Aa]utoritní data|[Pp]ortály)|\[\[Kategorie:)',
                                                r'\n\n\1', page_replaced_text)
                    page.text = page_replaced_text
                    pywikibot.output('Saving %s' % page.title())
                    callback = None
                    if len(deferred_touch) > 0:
                        def_page = deferred_touch.pop(0)
                        callback = lambda _, __: def_touch(def_page)
                    page.save(summary=u'odstranění odkazu na neexistující kategorii na Commons',
                              async=True, callback=callback)
            else:
                claim = pywikibot.Claim(repo, 'P373')
                claim.setTarget(cat_name)
                pywikibot.output(u'Importing P373 from %s to %s' % (page.title(), item.getID()))
                item.addClaim(claim)
                ref = pywikibot.Claim(repo, 'P143', isReference=True)
                ref.setTarget(pywikibot.ItemPage(repo, 'Q191168'))
                claim.addSource(ref)
                deferred_touch.append(page)
            break

pywikibot.output('Touching %s remaining page%s' % (len(deferred_touch), 's' if len(deferred_touch) != 1 else ''))
for def_page in deferred_touch:
    def_touch(def_page)

end = datetime.datetime.now()

pywikibot.output('Complete! Took %s seconds' % (end - start).total_seconds())
