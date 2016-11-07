# -*- coding: utf-8  -*-
import pywikibot
import random
import re

from pywikibot import pagegenerators, textlib

from pywikibot.bot import NoRedirectPageBot

from scripts.wikitext import WikitextFixingBot

class OldParamException(Exception):
    pass

class RemoveParamException(Exception):
    pass

class UnknownParamException(Exception):
    pass

class InfoboxMigratingBot(WikitextFixingBot, NoRedirectPageBot):

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
        u'', image_param, size_param, caption_param,
    ]
    rename_params = {}
    old_params = ()
    remove_params = ()

    def __init__(self, **kwargs):
        self.template = self.normalize(kwargs.pop('template'))
        self.new_template = self.normalize(kwargs.pop('new_template'))
        super(InfoboxMigratingBot, self).__init__(**kwargs)

    def normalize(self, template):
        tmp = template.replace('_', ' ').partition('<!--')[0].strip()
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
                    pywikibot.error('Couldn\'t find the template')
                    return

                start = start_match.start()
                if len(fielddict) > 0:
                    end = text.index('|', start)
                else:
                    end = text.index('}}', start)

                for name, value in fielddict.items():
                    end += len(u'|%s=%s' % (name, value))

                    name = name.strip()
                    value = value.strip() #fixme: remove comments about old params

                    try:
                        new_name = self.handleParam(name)
                    except OldParamException:
                        if textlib.removeDisabledParts(
                            value, ['comments']).strip() != '':
                            old_params.append(
                                (name, value)
                            )
                    except RemoveParamException:
                        changed = True
                        if textlib.removeDisabledParts(
                            value, ['comments']).strip() != '':
                            removed_params.append(
                                (name, value)
                            )
                    except UnknownParamException:
                        if textlib.removeDisabledParts(
                            value, ['comments']).strip() != '':
                            unknown_params.append(
                                (name, value)
                            )
                    except AssertionError:
                        pywikibot.warning('Error during handling '
                                          'parameter "%s"' % name)
                        return
                    else:
                        new_params.append(
                            (new_name, value)
                        )
                        if new_name != name:
                            changed = True

                end += len('}}')

                while text[start:end].count('{{') < text[start:end].count('}}'):
                    end = text[:end].rindex('}}') + len('}}')

                if text[start:end].count('{{') > text[start:end].count('}}'):
                    ballance = 1
                    index = start + len('{{')
                    while ballance > 0:
                        next_open = text.index('{{', index)
                        next_close = text.index('}}', index)
                        if next_open < next_close:
                            ballance += 1
                        else:
                            ballance -= 1
                        index = min(next_open, next_close) + len('{}')
                    end = index + len('}}')

                if not text[start:end].endswith('}}'):
                    end = text[:end].rindex('}}') + len('}}')

                if (end < start or not text[start:end].endswith('}}') or
                    text[start:end].count('{{') != text[start:end].count('}}')):
                    pywikibot.error('Couldn\'t parse the template')
                    return
                break

        else:
            pywikibot.error('Couldn\'t parse the template')
            return

        if not changed:
            pywikibot.output('No parameters changed')
            return

        while end < len(text) and text[end].isspace():
            end += 1

        space_before = ''
        lines = []
        for line in text[start:end].splitlines():
            if re.match(' *\|', line): # fixme: nested templates
                lines.append(line)
        if len(lines) > 0 and random.choice(lines).startswith(' '):
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
        if name == '':
            raise UnknownParamException

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

        if self.image_param in params:
            if self.caption_param not in params:
                new.append(
                    (self.caption_param, '')
                )

            new.remove(
                (self.image_param, params[self.image_param])
            )
            image = pywikibot.page.url2unicode(params[self.image_param])
            image = re.sub('_+', ' ', image)
            image = re.sub(' +', ' ', image).strip()
            new.append(
                (self.image_param, image)
            )

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
            'Type the template to replace the previous one:')

    if not options.get('new_template', None):
        options['new_template'] = options['template']

    generator = genFactory.getCombinedGenerator()
    if not generator:
        genFactory.handleArg(u'-transcludes:%s' % options['template'])
        generator = genFactory.getCombinedGenerator()

    bot = InfoboxMigratingBot(generator=generator, **options)
    bot.run()

if __name__ == "__main__":
    main()
