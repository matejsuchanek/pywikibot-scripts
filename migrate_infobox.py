# -*- coding: utf-8  -*-
import pywikibot
import random
import re

from pywikibot import pagegenerators
from pywikibot import textlib

from pywikibot.bot import (
    ExistingPageBot, NoRedirectPageBot
)

from scripts.wikitext import WikitextFixingBot

class DeprecatedParamException(Exception):
    pass

class UnknownParamException(Exception):
    pass

class InfoboxMigratingBot(WikitextFixingBot, ExistingPageBot, NoRedirectPageBot):

    caption_param = 'popisek'
    image_param = u'obrázek'
    size_param = u'velikost obrázku'
    all_params = [
        u'titul před', u'jméno', 'titul za', image_param, size_param,
        caption_param,

        u'pořadí', u'úřad', 'od', 'do', 'spolu s', u'nastupující za',
        'prezident', u'předsedkyně vlády', u'předseda vlády', u'kancléř',
        u'předseda', u'guvernér', 'panovnice', u'panovník', u'generální guvernér',
        'viceprezident', u'místopředseda vlády', 'poslanec', u'náměstek',
        u'jmenující', u'spoluvládce', u'nastupující za', u'zástupce', u'protivník',
        u'úřadující', u'předchůdce', u'nástupce', u'volební obvod', u'většina',
        u'pořadí#',

        'soud', u'období soudce', u'soud#',

        'strana', u'těleso', u'kandidující za', u'těleso#',

        u'datum narození', u'místo narození', u'datum úmrtí', u'místo úmrtí',
        u'národnost', u'země', u'občanství', 'titul', 'kneset', u'choť',
        'partner', 'partnerka', 'vztahy', u'rodiče', u'děti', u'příbuzní',
        u'sídlo', 'alma mater', u'zaměstnání', 'profese', u'náboženství',
        'podpis', 'popisek podpisu', 'web', u'ocenění',

        u'přezdívka', u'sloužil', u'složka', u'doba služby', 'hodnost',
        'jednotka', 'velel', 'bitvy', u'vyznamenání',

        'commons', u'poznámky'
    ]
    rename_params = {
        u'čestný titul': u'titul před',
        u'čestný sufix': 'titul za',
        u'manžel/ka': u'choť',
        'website': 'web',
        u'webová stránka': 'web',
    }
    old_params = ('width', 'height', u'malý obrázek', 'poslanec', 'velvyslanec')

    def __init__(self, site, **kwargs):
        self.template = self.normalize(kwargs.pop('template'))
        self.new_template = self.normalize(kwargs.pop('new_template'))
        super(InfoboxMigratingBot, self).__init__(site, **kwargs)

    def normalize(self, template):
        tmp, _, __ = template.replace('_', ' ').partition('<!--')
        tmp = tmp.strip()
        return tmp[0].upper() + tmp[1:]

    def treat_page(self):
        page = self.current_page
        text = page.text

        new_params = []
        deprecated_params = []
        unknown_params = []
        changed = self.template != self.new_template
        for template, fielddict in textlib.extract_templates_and_params(
            text, remove_disabled_parts=False, strip=False):
            if self.normalize(template) == self.template:
                start_match = re.search(
                    r'\{\{\s*%s\s*' % re.escape(template), text) # todo: prefix
                if not start_match:
                    pywikibot.warning('Couldn\'t find the template')
                    return

                start = start_match.start()
                if len(fielddict) > 0:
                    end = text.index('|', start)
                else:
                    end = text.index('}}', start)

                for name, value in fielddict.items():
                    end += len('=|') + len(value)
                    if not name.isdigit():
                        end += len(name)

                    name = name.strip()
                    value = value.strip()
                    try:
                        new_name = self.handleParam(name)
                    except DeprecatedParamException:
                        if value != '' and not (\
                            value.startswith('<!--') and value.endswith('-->')):
                            deprecated_params.append(
                                (name, value)
                            )
                    except UnknownParamException:
                        if value != '' and not (\
                            value.startswith('<!--') and value.endswith('-->')):
                            unknown_params.append(
                                (name, value)
                            )
                    except AssertionError:
                        pywikibot.warning('Error during handling parameter "%s"' % name)
                        return
                    else:
                        new_params.append(
                            (new_name, value)
                        )
                        if new_name != name:
                            changed = True

                end += len('}}')
                if not text[start:end].endswith('}}'):
                    if text[start:end].count('{{') == text[start:end].count('}}'):
                        end = text[:end].rindex('}}') + len('}}')
                    else:
                        while text[start:end].count('{{') > text[start:end].count('}}'):
                            end = text.index('}}', start) + len('}}')
                        while text[start:end].count('{{') < text[start:end].count('}}'):
                            end = text[:end].rindex('}}') + len('}}')

                assert text[start:end].endswith('}}')
                break

        else:
            pywikibot.warning('Couldn\'t parse the template')
            return

        if not changed:
            pywikibot.output('No parameters changed')
            return

        while text[end].isspace():
            end += 1

        space_before = ''
        lines = []
        for line in text[start:end].splitlines():
            if re.match(' *\|', line):
                lines.append(line)
        if len(lines) and random.choice(lines).startswith(' '):
            space_before = ' '

        self.handleParams(new_params)
        new_params.sort(key=self.keyForSort)

        new_template = u'{{%s' % self.new_template
        if len(new_params) > 0:
            new_template += '\n'
            for param, value in new_params:
                new_template += u'%s| %s = %s\n' % (space_before, param, value)

        if len(deprecated_params) > 0:
            new_template += u'<!-- Zastaralé parametry -->\n'
            for param, value in deprecated_params:
                new_template += u'%s| %s = %s\n' % (space_before, param, value)

        if len(unknown_params) > 0:
            new_template += u'<!-- Neznámé parametry -->\n'
            for param, value in unknown_params:
                new_template += u'%s| %s = %s\n' % (space_before, param, value)

        new_template += '}}\n'

        page.text = text[:start] + new_template + text[end:]
        if self.getOption('always') is not True:
            pywikibot.showDiff(text, page.text)
        self._save_page(page, self.fix_wikitext, page,
                        summary=u'sjednocení infoboxu')

    def keyForSort(self, value):
        name = value[0]
        if name in self.old_params:
            return len(self.all_params) + self.old_params.index(name)

        if name in self.all_params:
            return self.all_params.index(name)

        if self.endsWithDigit(name):
            name, digit = self.stripDigit(name)
            if name not in self.all_params:
                return len(self.all_params) + int(digit)

            base_index = top_index = bottom_index = self.all_params.index(name)
            dec_index = int(digit) * 0.1
            while not self.all_params[top_index].endswith('#'):
                top_index += 1
            while self.all_params[bottom_index] != self.all_params[top_index][:-1]:
                bottom_index -= 1

            cent_index = 0.1 / (1 + top_index - base_index)
            return top_index + dec_index + cent_index

        return len(self.all_params)

    def endsWithDigit(self, text):
        digits = '0123456789'
        return text not in digits and any(text.endswith(x) for x in digits)

    def stripDigit(self, text):
        assert self.endsWithDigit(text)
        match = re.match('([^0-9]+)([0-9]+)$', text)
        return match.group(1), match.group(2)

    def handleParam(self, name):
        name = name.replace('_', ' ')
        if name in self.rename_params:
            name = self.rename_params[name]
            assert name in self.all_params

        if name in self.old_params:
            raise DeprecatedParamException

        if name in self.all_params:
            return name

        new_name = name
        if self.endsWithDigit(name):
            new_name, digit = self.stripDigit(name)
            if int(digit) > 10:
                raise UnknownParamException
            if new_name in self.all_params:
                return name

        if new_name in self.old_params:
            raise DeprecatedParamException
        else:
            raise UnknownParamException

    def handleParams(self, params):
        pairs = {} # fixme: better
        for key, value in params:
            pairs[key] = value

        if self.size_param in params:
            if 'width' in pairs:
                params.remove(
                    ('width', pairs['width'])
                )
            if 'heigth' in pairs:
                params.remove(
                    ('heigth', pairs['heigth'])
                )
        else:
            if 'width' in pairs or 'heigth' in pairs:
                width = pairs['width'] if 'width' in pairs else '225'
                height = pairs['heigth'] if 'heigth' in pairs else '250px'
                params.append(
                    (self.size_param, width + 'x' + height)
                )

        if self.image_param in pairs:
            if self.caption_param not in pairs:
                params.append(
                    (self.caption_param, '')
                )
            if '_' in pairs[self.image_param]:
                params.remove(
                    (self.image_param, pairs[self.image_param])
                )
                params.append(
                    (self.image_param, pairs[self.image_param].replace('_', ' '))
                )

        if 'strana' in pairs and u'těleso' not in pairs and\
           any(x in pairs['strana'] for x in [
               u'nestraník', u'nezávislý', u'bezpartijní']):
            params.extend(
                [(u'těleso', ''), (u'kandidující za', '')]
            )

##        if u'jméno' in pairs:
##            before, title, after = pairs[u'jméno'].partition(self.current_page.title())
##            if after:
##                params.remove(
##                    (u'jméno', pairs[u'jméno'])
##                )
##                params.append(
##                    (u'jméno', title + after)
##                )
##                if u'titul před' in pairs:
##                    params.remove(
##                        (u'titul před', pairs[u'titul před'])
##                    )
##                    params.append(
##                        (u'titul před', pairs[u'titul před'] + ' ' + before.strip())
##                    )
##                else:
##                    params.append(
##                        (u'titul před', before.strip())
##                    )

def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    numbers = []
    for arg in local_args:
        if not genFactory.handleArg(arg):
            if arg.startswith('-'):
                arg, sep, value = arg.partition(':')
                if value != '':
                    options[arg[1:]] = value if not value.isdigit() else int(value)
                else:
                    options[arg[1:]] = True

    while not options.get('template', None):
        options['template'] = pywikibot.input(
            'Type the template you would like to work on:')
        options['new_template'] = pywikibot.input(
            'Type the template to replace the previous one:') or options['template']

    generator = genFactory.getCombinedGenerator()
    if not generator:
        genFactory.handleArg('-transcludes:%s' % options['template'])
        generator = genFactory.getCombinedGenerator()

    site = pywikibot.Site()
    bot = InfoboxMigratingBot(site, generator=generator, **options)
    bot.run()

if __name__ == "__main__":
    main()
