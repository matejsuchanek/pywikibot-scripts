#!/usr/bin/python
import datetime

import pywikibot

from pywikibot import pagegenerators, textlib
from pywikibot.exceptions import APIError, NoPageError
from pywikibot.tools import first_lower

pywikibot.handle_args()

start = datetime.datetime.now()

do_only = []
dont_do = []

tp_map = {
    'cs|wikipedia': {
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
                'namespaces': [14]
            },
        },
        'wikicitáty': {
            'dílo': {
                'family': 'wikiquote',
                'pattern': 'Dílo:%s'
            },
            'kategorie': {
                'family': 'wikiquote',
                'pattern': 'Kategorie:%s'
            },
            'osoba': 'wikiquote',
            'téma': 'wikiquote'
        },
        'wikizdroje': {
            'dílo': 'wikisource',
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
    'cs|wikiquote': {
        'commons': {
            'galerie': {
                'lang': 'commons',
                'family': 'commons'
            },
            'kategorie': {
                'lang': 'commons',
                'family': 'commons',
                'pattern': 'Category:%s',
                'namespaces': [14]
            },
        },
        'wikipedie': {
            'článek': 'wikipedia'
        },
    },
    'cs|wikisource': {
        'commons': {
            'galerie': {
                'lang': 'commons',
                'family': 'commons'
            },
            'kategorie': {
                'lang': 'commons',
                'family': 'commons',
                'pattern': 'Category:%s',
                'namespaces': [14]
            },
        },
        'autorinfo': {
            'BiografieWiki': 'wikipedia',
            'WikiquoteCS': 'wikiquote'
        },
    },
    'de|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    'es|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    'fi|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    'fr|wikiquote': {
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
    'fr|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    'id|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    'pl|wikiquote': {
        'commons': {
            '1': {
                'lang': 'commons',
                'family': 'commons'
            }
        },
        'wikinews': {str(i): 'wikinews' for i in range(1, 10)},
        'wikipediakat': {
            '1': {
                'lang': 'pl',
                'family': 'wikipedia',
                'pattern': 'Category:%s',
                'namespaces': [14],
            },
        },
        'wikisource': {}, # todo
    },
    'pt|wikiquote': {
        'autor': {
            'Wikinoticias': 'wikinews',
            'Wikipedia': 'wikipedia',
            'Wikisource': 'wikisource'
        },
        'wikipédia': {
            '1': 'wikipedia'
        },
        'wikisource': {
            '1': 'wikisource'
        },
    },
    'ru|wikiquote': {
        'википедия': {
            '1': 'wikipedia'
        },
        'wikipedia': {
            '1': 'wikipedia'
        },
        'навигация': {
            'Википедия': 'wikipedia',
            'Викитека': 'wikisource',
            'Викивиды': {
                'family': 'species',
                'lang': 'species'
            },
            'Викисклад': {
                'lang': 'commons',
                'family': 'commons'
            },
            'Викигид': 'wikivoyage',
        },
    },
    'sk|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
    'sv|wikiquote': {
        'wikipedia': {
            '1': 'wikipedia'
        },
    },
}

for project in tp_map.keys():
    lang, family = project.split('|', 1)
    if len(do_only) > 0 and lang + family not in do_only and family not in do_only:
        continue
    if lang + family in dont_do or family in dont_do:
        continue

    site = pywikibot.Site(lang, family)
    pywikibot.output('Doing %s%s' % (lang, family))
    site.login()

    genFactory = pagegenerators.GeneratorFactory(site=site)
    for ns in (0, 14, 100):
        if family != 'wikisource' and ns == 100:  # fixme: cswikiquote
            continue
        if family == 'wikisource' and ns == 0:
            continue
        genFactory.handle_arg('-ns:%i' % ns)
    genFactory.handle_arg('-unconnectedpages')
    generator = genFactory.getCombinedGenerator(preload=True)

    for page in generator:
        if page.namespace() != 14 and page.isDisambig():
            continue

        for template, fields in textlib.extract_templates_and_params(page.text):
            if first_lower(template) not in tp_map[project]:
                continue

            params = tp_map[project][first_lower(template)]
            for key in fields:
                if key not in params:
                    continue

                title = fields[key].strip()
                if not title:
                    continue

                target_lang = lang
                target_family = family
                if isinstance(params[key], dict):
                    if params[key].get('namespaces', []) and page.namespace() not in params[key]['namespaces']:
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
                if '{{' in title:
                    title = site.expand_text(title, page.title())
                target_page = pywikibot.Page(target_site, title)
                if not target_page.exists():
                    pywikibot.output("%s doesn't exist" % target_page)
                    continue
                while target_page.isRedirectPage():
                    target_page = target_page.getRedirectTarget()
                if target_page.isDisambig():
                    pywikibot.output('%s is a disambiguation' % target_page)
                    continue

                try:
                    item = target_page.data_item()
                except NoPageError:
                    repo = site.data_repository()
                    # fixme: unused return value
                    data = repo.linkTitles(page, target_page)
                    pywikibot.output('Item created')
                    pywikibot.output(data)  # todo
                    break
                if site.dbName() in item.sitelinks:
                    pywikibot.output(page)
                    pywikibot.output('%s already has sitelink to %s%s' % (
                        item, lang, family))
                    continue

                try:
                    item.setSitelink(
                        page, summary='Adding sitelink %s' % page.title(
                            asLink=True, insite=item.site))
                except APIError:
                    pass
                else:
                    page.purge()
                    break

end = datetime.datetime.now()

pywikibot.output('Complete! Took %d seconds' % (end - start).total_seconds())
