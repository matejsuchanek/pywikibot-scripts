# -*- coding: utf-8  -*-
import datetime
import pywikibot

from pywikibot import pagegenerators
from pywikibot import textlib

start = datetime.datetime.now()

do_only = []
dont_do = []

tp_map = {
    u'cs|wikipedia': {
        'commons': {
            '1': {
                'lang': 'commons',
                'family': 'commons'
            },
        },
        'commonscat': {
            '1': {
                'lang': 'commons',
                'family': 'commons',
                'pattern': 'Category:%s',
                'namespaces': (14)
            },
        },
        u'wikicitáty': {
            u'dílo': {
                'family': 'wikiquote',
                'pattern': u'Dílo:%s'
            },
            'kategorie': {
                'family': 'wikiquote',
                'pattern': 'Kategorie:%s'
            },
            'osoba': 'wikiquote',
            u'téma': 'wikiquote'
        },
        'wikizdroje': {
            u'dílo': 'wikisource',
            'autor': {
                'family': 'wikisource',
                'pattern': 'Autor:%s'
            },
            'kategorie': {
                'family': 'wikiquote',
                'pattern': 'Kategorie:%s'
            },
        },
        'wikidruhy': {
            'taxon': {
                'family': 'species',
                'lang': 'species',
            },
        },
    },
    u'cs|wikiquote': {
        'commons': {
            'galerie': {
                'lang': 'commons',
                'family': 'commons'
            },
            'kategorie': {
                'lang': 'commons',
                'family': 'commons',
                'pattern': 'Category:%s',
                'namespaces': (14)
            },
        },
        'wikipedie': {
            u'článek': 'wikipedia'
        },
    },
    u'cs|wikisource': {
        'commons': {
            'galerie': {
                'lang': 'commons',
                'family': 'commons'
            },
            'kategorie': {
                'lang': 'commons',
                'family': 'commons',
                'pattern': 'Category:%s',
                'namespaces': (14)
            },
        },
        'autorinfo': {
            'BiografieWiki': 'wikipedia',
            'WikiquoteCS': 'wikiquote'
        },
    },
    u'de|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    u'es|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    u'fi|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    u'fr|wikiquote': {
        'autres projets': {
            'w': 'wikipedia',
            's': 'wikisource',
            'species': {
                'family': 'species',
                'lang': 'species'
            },
            'wikispecies': {
                'family': 'species',
                'lang': 'species'
            },
            'commons': {
                'lang': 'commons',
                'family': 'commons'
            },
            '1': {
                'lang': 'commons',
                'family': 'commons'
            },
        },
    },
    u'fr|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    u'pt|wikiquote': {
        'autor': {
            'Wikinoticias': 'wikinews',
            'Wikipedia': 'wikipedia',
            'Wikisource': 'wikisource'
        },
        u'wikipédia': {
            '1': 'wikipedia'
        },
        'wikisource': {
            '1': 'wikisource'
        },
    },
    u'ru|wikiquote': {
        u'википедия': {
            '1': 'wikipedia'
        },
        'wikipedia': {
            '1': 'wikipedia'
        },
        u'навигация': {
            u'Википедия': 'wikipedia',
            u'Викитека': 'wikisource',
            u'Викивиды': {
                'family': 'species',
                'lang': 'species'
            },
            u'Викисклад': {
                'lang': 'commons',
                'family': 'commons'
            },
            u'Викигид': 'wikivoyage',
        },
    },
    u'sk|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    u'sv|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
}

for project in tp_map.keys():
    (lang, family) = project.split('|')
    if len(do_only) > 0 and lang + family not in do_only and family not in do_only:
        continue
    if lang + family in dont_do or family in dont_do:
        continue

    site = pywikibot.Site(lang, family)
    pywikibot.output('Doing %s%s' % (lang, family))

    for page in pagegenerators.UnconnectedPageGenerator(site, 1500):
        if page.namespace() not in [0, 14, 100]:
            continue
        if family == 'wikisource' and page.namespace() == 0:
            continue
        if family == 'wikipedia' and page.namespace() == 100:
            continue
        if page.namespace() != 14 and page.isDisambig():
            continue

        for template, fields in textlib.extract_templates_and_params(page.get()):
            if template.lower() in tp_map[project].keys():
                params = tp_map[project][template.lower()]
                for key in fields.keys():
                    if key in params.keys():
                        title = fields[key].strip()
                        if not title:
                            continue

                        target_lang = lang
                        target_family = family
                        if type(params[key]) == type({}):
                            if 'namespaces' in params[key].keys() and page.namespace() not in params[key]['namespaces']:
                                continue
                            if 'pattern' in params[key].keys():
                                title = params[key]['pattern'] % title
                            if 'family' in params[key].keys():
                                target_family = params[key]['family']
                            if 'lang' in params[key].keys():
                                target_lang = params[key]['lang']
                        else:
                            target_family = params[key]

                        target_site = pywikibot.Site(target_lang, target_family)
                        target_page = pywikibot.Page(target_site, title)
                        if not target_page.exists():
                            continue
                        if target_page.isRedirectPage():
                            target_page = target_page.getRedirectTarget()
                        if target_page.isDisambig():
                            continue
                        try:
                            item = target_page.data_item()
                            item.get()
                            if site.dbName() in item.sitelinks.keys():
                                continue
                            item.setSitelink(page, summary=u'Adding sitelink to [[%s:%s]]'
                                             % (site.sitename(), page.title()))
                            page.touch()
                            break
                        except Exception as exc:
                            pywikibot.output('%s: %s' % (page.title(), exc.message))

end = datetime.datetime.now()

pywikibot.output("Complete! Took %s seconds" % (end - start).total_seconds())
