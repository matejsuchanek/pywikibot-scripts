# -*- coding: utf-8  -*-
import pywikibot
import random
import re

from pywikibot import pagegenerators, textlib

from pywikibot.bot import (
    ExistingPageBot, NoRedirectPageBot
)

from scripts.wikitext import WikitextFixingBot

class OldParamException(Exception):
    pass

class RemoveParamException(Exception):
    pass

class UnknownParamException(Exception):
    pass

class InfoboxMigratingBot(WikitextFixingBot, ExistingPageBot, NoRedirectPageBot):

    '''
    Bot to rename an infobox and its parameters

    Features:
    * renames or removes parameters
    * marks old/unknown parameters and removes those that are empty
    * provides access to all parameters and allows addding/changing/removing them
    * sorts parameters
    * fixes whitespace "| param = value"
    '''

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
    remove_params = ('soud', u'období soudce')

    def __init__(self, **kwargs):
        self.template = self.normalize(kwargs.pop('template'))
        self.new_template = self.normalize(kwargs.pop('new_template'))
        super(InfoboxMigratingBot, self).__init__(**kwargs)

    def normalize(self, template):
        tmp, _, __ = template.replace('_', ' ').partition('<!--')
        tmp = tmp.strip()
        return tmp[0].upper() + tmp[1:]

    def treat_page(self):
        page = self.current_page
        text = page.text

        new_params = []
        old_params = []
        unknown_params = []
        removed_params = []
        changed = self.template != self.new_template
        for template, fielddict in textlib.extract_templates_and_params(
            text, remove_disabled_parts=False, strip=False): # todo: support multiple boxes
            if self.normalize(template) == self.template:
                start_match = re.search(
                    r'\{\{\s*((%s)\s*:\s*)?%s\s*' % (
                        '|'.join(self.site.namespaces[10]),
                        re.escape(template)), text)
                if not start_match:
                    pywikibot.warning('Couldn\'t find the template')
                    return

                start = start_match.start()
                if len(fielddict) > 0:
                    end = text.index('|', start)
                else:
                    end = text.index('}}', start)

                for name, value in fielddict.items():
                    end += len(u'|%s=%s' % (name, value))

                    name = name.strip()
                    value = value.strip()

                    try:
                        new_name = self.handleParam(name)
                    except OldParamException:
                        if textlib.removeDisabledParts(value, ['comments']).strip() != '':
                            old_params.append(
                                (name, value)
                            )
                    except RemoveParamException:
                        changed = True
                        if textlib.removeDisabledParts(value, ['comments']).strip() != '':
                            removed_params.append(
                                (name, value)
                            )
                    except UnknownParamException:
                        if textlib.removeDisabledParts(value, ['comments']).strip() != '':
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

                if text[start:end].count('{{') != text[start:end].count('}}'):
                    while text[start:end].count('{{') > text[start:end].count('}}'):
                        end = text[:end].rindex('{{')
                        end = text[:end].rindex('}}') + len('}}')
                    while text[start:end].count('{{') < text[start:end].count('}}'):
                        end = text[:end].rindex('}}') + len('}}')

                else:
                    if not text[start:end].endswith('}}'):
                        end = text[:end].rindex('}}') + len('}}')

                if (end < start or not text[start:end].endswith('}}') or
                    text[start:end].count('{{') != text[start:end].count('}}')):
                    pywikibot.warning('Couldn\'t parse the template')
                    return
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
            if re.match(' *\|', line): # fixme: nested templates
                lines.append(line)
        if len(lines) and random.choice(lines).startswith(' '):
            space_before = ' '

        self.handleParams(new_params, old_params, removed_params, unknown_params)
        new_params.sort(key=self.keyForSort)

        new_template = u'{{%s' % self.new_template
        if len(new_params) > 0:
            new_template += '\n'
            for param, value in new_params:
                new_template += u'%s| %s = %s\n' % (space_before, param, value)

        if len(old_params) > 0:
            new_template += u'<!-- Zastaralé parametry -->\n'
            for param, value in old_params:
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
        return not text.isdigit() and text[-1].isdigit()

    def stripDigit(self, text):
        assert self.endsWithDigit(text)
        return re.match('(.+?)([0-9]+)$', text).groups()

    def handleParam(self, name):
        name = name.replace('_', ' ')
        if name in self.rename_params:
            name = self.rename_params[name]
            assert name in self.all_params

        if name in self.all_params:
            return name

        if name in self.remove_params:
            raise RemoveParamException

        if name in self.old_params:
            raise OldParamException

        new_name = name
        if self.endsWithDigit(name):
            new_name, digit = self.stripDigit(name)
            if new_name in self.all_params:
                top_index = index = self.all_params.index(new_name)
                while not self.all_params[top_index].endswith('#'):
                    top_index += 1
                    if len(self.all_params) == top_index:
                        raise UnknownParamException

                top_name = self.all_params[top_index][:-1]
                assert top_name in self.all_params
                if self.all_params.index(top_name) > index:
                    raise UnknownParamException

                return name

        if new_name in self.remove_params:
            raise RemoveParamException
        elif new_name in self.old_params:
            raise OldParamException
        else:
            raise UnknownParamException

    def handleParams(self, new, old, removed, unknown):
        # fixme: list of tuples is too complicated
        params = {}
        for key, value in new + old + removed + unknown:
            #if key in params: ...
            params[key] = value

        if self.size_param in params:
            if 'width' in params:
                old.remove(
                    ('width', params['width'])
                )
            if 'heigth' in params:
                old.remove(
                    ('heigth', params['heigth'])
                )
        else:
            if 'width' in params or 'heigth' in params:
                width = params['width'] if 'width' in params else '225'
                height = params['heigth'] if 'heigth' in params else '250px'
                new.append(
                    (self.size_param, u'%sx%s' % (width, height))
                )

        if self.image_param in params:
            if self.caption_param not in params:
                new.append(
                    (self.caption_param, '')
                )
            if '_' in params[self.image_param]:
                new.remove(
                    (self.image_param, params[self.image_param])
                )
                new.append(
                    (self.image_param, params[self.image_param].replace('_', ' '))
                )

        if any(x in params for x in (
            'soud', 'soud1', u'období soudce', u'období soudce1')):
            if 'profese' in params:
                if 'soudce' not in params['profese'].lower():
                    before, conj, after = params['profese'].rpartition(' a ')
                    new.remove(
                        ('profese', params['profese'])
                    )
                    if conj:
                        new.append(
                            ('profese', u'%s, %s a [[soudce]]' % (before, after))
                        )
                    else:
                        new.append(
                            ('profese', u'%s a [[soudce]]' % before)
                        )

        if 'strana' in params and u'těleso' not in params and\
           any(x in params['strana'] for x in [
               u'nestraník', u'nezávislý', u'bezpartijní', u'bez politické']):
            new.extend(
                [(u'těleso', ''), (u'kandidující za', '')]
            )

##        if u'jméno' in params:
##            before, title, after = params[u'jméno'].partition(self.current_page.title())
##            if after:
##                new.remove(
##                    (u'jméno', params[u'jméno'])
##                )
##                new.append(
##                    (u'jméno', title + after)
##                )
##                if u'titul před' in params:
##                    new.remove(
##                        (u'titul před', params[u'titul před'])
##                    )
##                    new.append(
##                        (u'titul před', params[u'titul před'] + ' ' + before.strip())
##                    )
##                else:
##                    new.append(
##                        (u'titul před', before.strip())
##                    )

def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
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
        genFactory.handleArg(u'-transcludes:%s' % options['template'])
        generator = genFactory.getCombinedGenerator()

    bot = InfoboxMigratingBot(generator=generator, **options)
    bot.run()

if __name__ == "__main__":
    main()
