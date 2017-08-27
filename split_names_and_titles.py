# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pywikibot
import re

from pywikibot import pagegenerators, textlib

from pywikibot.textlib import mwparserfromhell
from pywikibot.tools import first_upper

try:
    from .wikitext import WikitextFixingBot
except ImportError:
    from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot

    class WikitextFixingBot(SingleSiteBot, NoRedirectPageBot, ExistingPageBot):
        pass

class TitlesMovingBot(WikitextFixingBot):

    param = 'jméno'
    param_before = 'titul před'
    param_after = 'titul za'

    summary = 'přesun titulů do vlastních parametrů'

    def __init__(self, template, offset=0, **kwargs):
        self.template = self.normalize(template)
        self.start_offset = offset
        self.offset = 0
        super(TitlesMovingBot, self).__init__(**kwargs)

    def normalize(self, template):
        return first_upper(template
                           .partition('<!--')[0]
                           .replace('_', ' ')
                           .strip())

    def treat(self, page):
        self.offset += 1
        if self.offset > self.start_offset:
            super(TitlesMovingBot, self).treat(page)

    def treat_page(self):
        page = self.current_page
        code = mwparserfromhell.parse(page.text)
        for temp in code.ifilter_templates():
            if self.template != self.normalize(temp.name):
                continue
            if not temp.has(self.param):
                continue
            param = temp.get(self.param)
            value = str(param.value)
            before, inside, after = self.handle_param(value)
            if not before and not after:
                continue
            temp.add(self.param, inside)
            if before:
                temp.add(self.param_before, before, before=param)
                my_param = temp.get(self.param_before)
                my_param.value = self.add_spaces(my_param.value, value)
            if after:
                index = temp.params.index(param)
                if len(temp.params) - 1 == index:
                    temp.add(self.param_after, after)
                else:
                    temp.add(self.param_after, after,
                             before=temp.params[index+1])
                my_param = temp.get(self.param_after)
                my_param.value = self.add_spaces(my_param.value, value)

        if self.put_current(str(code), summary=self.summary):
            self.offset -= 1

    def add_spaces(self, new, pattern):
        pre, post = re.fullmatch(r'(\s*).*?(\s*)', pattern, flags=re.S).groups()
        return pre + new.strip() + post

    def handle_param(self, param):
        before = after = ''
        if '<br>' in param.replace(' ', '').replace('/', '').replace('\\', ''):
            return before, param, after

        new_param = (param
                     .replace("'''", '')
                     .replace('<small>', '')
                     .replace('</small>', '')
                     .strip())
        title = self.current_page.title()
        first = title.partition(' ')[0]
        index = new_param.find(first)
        if index > 0:
            before = new_param[:index].strip()
            if before.endswith('&nbsp;'):
                before = before[:-len('&nbsp;')]
            if before.endswith('.') or before.endswith(']]'):
                new_param = new_param[index:]
            else:
                before = ''

        new_param, comma, after = new_param.partition(', ')
        if before or after:
            param = new_param

        return before, new_param, after.strip()

    def exit(self):
        super(TitlesMovingBot, self).exit()
        pywikibot.output('Current offset: %s' % self.offset)

def main(*args):
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    while not options.get('template', None):
        options['template'] = pywikibot.input(
            'Type the template you would like to work on:')

    generator = genFactory.getCombinedGenerator(preload=True)
    if not generator:
        genFactory.handleArg('-transcludes:%s' % options['template'])
        generator = genFactory.getCombinedGenerator(preload=True)

    bot = TitlesMovingBot(generator=generator, **options)
    bot.run()

if __name__ == '__main__':
    if isinstance(mwparserfromhell, Exception):
        pywikibot.error('Running this script requires having mwparserfromhell '
                        'installed')
    else:
        main()
