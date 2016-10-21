# -*- coding: utf-8  -*-
import pywikibot
import random
import re

from pywikibot import pagegenerators
from pywikibot import textlib

from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, SkipPageError
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
        u'webová stránka': 'web',
    }
    old_params = ['width', 'height', 'poslanec', 'velvyslanec']

    def __init__(self, site, **kwargs):
        template = kwargs.pop('template', False)
        new_template = kwargs.pop('new_template', template)
        super(InfoboxMigratingBot, self).__init__(site, **kwargs)
        self.template = self.getTemplate(template)
        self.new_template = self.getTemplate(new_template)

    def getTemplate(self, template):
        if not template:
            pywikibot.warning('Failed template name match')
            return template

        return template.replace('_', ' ').strip()

    def init_page(self, page):
        pass

    def treat_page(self):
        page = self.current_page
        text = page.text
        start = -1
        end = -1
        for match in textlib.NESTED_TEMPLATE_REGEX.finditer(text):
            name = self.getTemplate(match.group(1))
            if name == self.template:
                start = match.start()
                end = match.end()
                break

        if start < 0:
            pywikibot.warning('Couldn\'t find the template')
            return

        new_params = []
        deprecated_params = []
        unknown_params = []
        for template, fielddict in textlib.extract_templates_and_params(
            text[start:end], remove_disabled_parts=False, strip=True):
            if template == self.template:
                for name, value in fielddict.items():
                    try:
                        name, value = self.handleParam(name, value)
                    except DeprecatedParamException:
                        value = value.strip()
                        if value != '' and not (\
                            value.startswith('<!--') and value.endswith('-->')):
                            deprecated_params.append(
                                (name, value)
                            )
                    except UnknownParamException:
                        value = value.strip()
                        if value != '' and not (\
                            value.startswith('<!--') and value.endswith('-->')):
                            unknown_params.append(
                                (name, value)
                            )
                    except AssertionError:
                        pywikibot.warning('Error during handling parameter "%s"' % name)
                        return
                    else:
                        value = value.strip()
                        new_params.append(
                            (name, value)
                        )
                break

        else:
            pywikibot.warning('Couldn\'t parse the template')
            return

        space_before = ''
        lines = text[start:end].splitlines()
        if re.match(' *}}$', lines[-1]):
            lines.pop()
        if len(lines) > 1 and random.choice(lines[1:]).startswith(' '):
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

        new_template += '}}'

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
                return len(self.all_params)

            base_index = top_index = bottom_index = self.all_params.index(name)
            dec_index = int(digit) * 0.1
            while not self.all_params[top_index].endswith('#'):
                top_index += 1
            while self.all_params[bottom_index] != self.all_params[top_index][:-1]:
                bottom_index -= 1

            cent_index = base_index * 0.1 / (top_index - bottom_index)

            return top_index + dec_index + cent_index

        return len(self.all_params)

    def endsWithDigit(self, text):
        digits = '0123456789'
        return text not in digits and any(text.endswith(x) for x in digits)

    def stripDigit(self, text):
        assert self.endsWithDigit(text)
        match = re.match('([^0-9]+)([0-9]+)', text)
        return match.group(1), match.group(2)

    def handleParam(self, name, value):
        name = name.replace('_', ' ')
        if name in self.rename_params:
            name = self.rename_params[name]
            assert name in self.all_params

        if name in self.old_params:
            raise DeprecatedParamException

        if name in self.all_params:
            return (name, value)

        new_name = name
        if self.endsWithDigit(name):
            new_name, digit = self.stripDigit(name)
            if int(digit) > 10:
                raise UnknownParamException
            if new_name in self.all_params:
                return (name, value)

        if new_name in self.old_params:
            raise DeprecatedParamException
        else:
            raise UnknownParamException

    def handleParams(self, params):
        pairs = {}
        for key, value in params:
            pairs[key] = value
        has_size = self.size_param in params
        if has_size:
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
                    (self.caption_param, width + 'x' + height)
                )

        if self.image_param in pairs and self.caption_param not in pairs:
            params.append(
                (self.caption_param, '')
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

    if 'template' not in options:
        pywikibot.output('Mandatory parameter "-template:" is missing')
        return

    generator = genFactory.getCombinedGenerator()
    if not generator:
        genFactory.handleArg('-transcludes:%s' % options['template'])
        generator = genFactory.getCombinedGenerator()

    site = pywikibot.Site()
    bot = InfoboxMigratingBot(site, generator=generator, **options)
    bot.run()

if __name__ == "__main__":
    main()
