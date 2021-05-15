#!/usr/bin/python
import re

from itertools import chain
from random import choice

import pywikibot

from pywikibot import pagegenerators, textlib
from pywikibot.tools import first_upper

try:
    from .wikitext import WikitextFixingBot
    # TODO: from .tools import .
    from .custome_fixes import FilesFix
except ImportError:
    from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot

    class WikitextFixingBot(SingleSiteBot, NoRedirectPageBot, ExistingPageBot):
        pass


class OldParamException(Exception):
    pass


class RemoveParamException(Exception):
    pass


class UnknownParamException(Exception):
    pass


class UnnamedParamException(Exception):
    pass


class IterUnnamed:

    def __init__(self, unnamed):
        self.unnamed = unnamed

    def __iter__(self):
        while self.unnamed:
            yield self.unnamed.popitem()

    def __nonzero__(self):
        return True  # needed? return self.unnamed?


class InfoboxMigratingBot(WikitextFixingBot):

    '''
    Bot to rename an infobox and its parameters

    Features:
    * renames or removes parameters
    * marks old/unknown parameters and removes those that are empty
    * provides access to all parameters and allows addding/changing/removing them
    * sorts parameters
    * fixes whitespace to "| param = value"
    '''

    alt_param = 'alt'
    caption_param = 'popisek'
    image_param = 'obrázek'
    image_size_param = 'velikost obrázku'
    latitude = 'zeměpisná šířka'
    longitude = 'zeměpisná délka'

    summary = 'sjednocení infoboxu'

    all_params = []
    rename_params = {}
    old_params = ()
    remove_params = ()

    def __init__(self, template, new_template, offset=0, **kwargs):
        self.template = self.normalize(template)
        self.new_template = self.normalize(new_template)
        self.start_offset = offset
        self.offset = 0
        super().__init__(**kwargs)
        self.file_regex = re.compile(
            textlib.FILE_LINK_REGEX % '|'.join(self.site.namespaces[6]), re.X)
        #self.parser = TemplateParser()

    def normalize(self, template):
        #return self.parser.normalize(template)
        return first_upper(template
                           .partition('<!--')[0]
                           .replace('_', ' ')
                           .strip())

    def treat(self, page):
        self.offset += 1
        if self.offset > self.start_offset:
            super().treat(page)

    def treat_page(self):
        text = self.current_page.text
        start = 0
        while True:
            before, after = text[:start], text[start:]
            new, start = self.find_and_replace(after, start == 0)
            text = before + new
            if after == new:
                break
        self.put_current(text, summary=self.summary)

    def find_and_replace(self, text, init):
        new_params = []
        old_params = []
        unknown_params = []
        removed_params = []
        changed = False
        for template, fielddict in textlib.extract_templates_and_params(
                text, remove_disabled_parts=False, strip=False):
            if self.normalize(template) not in (self.template,
                                                self.new_template):
                continue

            changed = self.normalize(template) != self.new_template
            start_match = re.search(r'\{\{\s*((%s)\s*:\s*)?%s\s*' % (
                '|'.join(self.site.namespaces[10]), re.escape(template)), text)
            if not start_match:
                if not init:
                    pywikibot.error("Couldn't find the template")
                return text, 0

            start = start_match.start()
            if len(fielddict) > 0:
                end = text.index('|', start)
            else:
                end = text.index('}}', start)

            unnamed = {}
            for name, value in chain(fielddict.items(), IterUnnamed(unnamed)):
                end += len('|%s=%s' % (name, value))

                name = name.strip()
                value = (value
                         .replace('\n<!-- Zastaralé parametry -->', '')
                         .replace('\n<!-- Neznámé parametry -->', '')
                         .strip())

                try:
                    new_name = self.handle_param(name)
                except OldParamException:
                    if textlib.removeDisabledParts(value, ['comments']).strip():
                        old_params.append(
                            (name, value)
                        )
                except RemoveParamException:
                    changed = True
                    if textlib.removeDisabledParts(value, ['comments']).strip():
                        removed_params.append(
                            (name, value)
                        )
                except UnknownParamException:
                    if textlib.removeDisabledParts(value, ['comments']).strip():
                        unknown_params.append(
                            (name, value)
                        )
                except AssertionError:
                    pywikibot.error('Couldn\'t handle parameter "%s"' % name)
                    return text, 0
                except UnnamedParamException:
                    unnamed[value] = ''
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
                end = start
                while ballance > 0:
                    next_close = text.index('}}', end)
                    ballance += text[end:next_close].count('{{') - 1
                    end = next_close + len('}}')

            if not text[start:end].endswith('}}'):  # elif?
                end = text[:end].rindex('}}') + len('}}')

            if (end < start or not text[start:end].endswith('}}') or
                    text[start:end].count('{{') != text[start:end].count('}}')):
                pywikibot.error("Couldn't parse the template")
                return text, 0
            break

        else:
            pywikibot.error("Couldn't parse the template")
            return text, 0

        if not changed:
            pywikibot.output('No parameters changed')
            return text, 0

        while end < len(text) and text[end].isspace():  # todo: also before
            end += 1

        lines = []
        nested = 0
        for line in text[start:end].splitlines():
            if nested == 1 and re.match(' *\|', line):
                lines.append(line)
            nested += line.count('{{') - line.count('}}')

        space_before = ''
        if len(lines) > 0 and choice(lines).startswith(' '):
            space_before = ' '

        self.handle_params(new_params, old_params, removed_params, unknown_params)
        self.deduplicate(new_params)
        new_params.sort(key=self.key_for_sort)

        new_template = '{{%s' % self.new_template
        if len(new_params) > 0:
            new_template += '\n'
            for param, value in new_params:
                new_template += '%s| %s = %s\n' % (space_before, param, value)

        if len(old_params) > 0:
            new_template += '<!-- Zastaralé parametry -->\n'
            for param, value in old_params:
                new_template += '%s| %s = %s\n' % (space_before, param, value)

        if len(unknown_params) > 0:
            new_template += '<!-- Neznámé parametry -->\n'
            for param, value in unknown_params:
                new_template += '%s| %s = %s\n' % (space_before, param, value)

        new_template += '}}\n'

        return text[:start] + new_template + text[end:], end

    def key_for_sort(self, value):
        name = value[0]
        if name in self.old_params:
            return len(self.all_params) + self.old_params.index(name)

        if name in self.all_params:
            return self.all_params.index(name)

        if self.ends_with_digit(name): # fixme: sort as tuple
            name, digit = self.strip_digit(name)
            digit = int(digit) + 1.0
            if name not in self.all_params:
                return len(self.all_params) + digit

            base_index = top_index = bottom_index = self.all_params.index(name)
            while not self.all_params[top_index].endswith('#'):
                top_index += 1
            while self.all_params[bottom_index] != self.all_params[top_index][:-1]:
                bottom_index -= 1

            top_index += 1
            diff = top_index - bottom_index
            return top_index - diff / digit + (diff / digit - diff / (digit + 1)) / (top_index - base_index)

        return len(self.all_params)

##    def key_for_sort(self, value):
##        name = value[0]
##        if name in self.old_params:
##            return len(self.all_params), self.old_params.index(name)
##
##        if name in self.all_params:
##            return self.all_params.index(name), 0
##
##        if self.ends_with_digit(name): # fixme: sort as tuple
##            name, digit = self.strip_digit(name)
##            digit = int(digit)
##            if name not in self.all_params:
##                return len(self.all_params), digit
##
##            base_index = top_index = bottom_index = self.all_params.index(name)
##            while not self.all_params[top_index].endswith('#'):
##                top_index += 1
##            while self.all_params[bottom_index] != self.all_params[top_index][:-1]:
##                bottom_index -= 1
##
##            top_index += 1
##            diff = top_index - bottom_index
##            return top_index - diff / digit + (diff / digit - diff / (digit + 1)) / (top_index - base_index)
##
##        return len(self.all_params)

    def ends_with_digit(self, text):
        return not text.isdigit() and text[-1].isdigit()

    def strip_digit(self, text):
        assert self.ends_with_digit(text)
        return re.fullmatch(r'(.+?)(\d+)', text).groups()

    def handle_param(self, name):
        if not name:
            raise UnknownParamException

        name = name.replace('_', ' ')
        if name in self.rename_params:
            name = self.rename_params[name]
            assert name in self.all_params or '#' in name #fixme

        if name in self.all_params:
            return name

        if name in self.remove_params:
            raise RemoveParamException

        if name in self.old_params:
            raise OldParamException

        if name.isdigit():
            raise UnnamedParamException

        new_name = name
        if self.ends_with_digit(name):
            new_name, digit = self.strip_digit(name)
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

    def handle_params(self, new, old, removed, unknown):
        # fixme: list of tuples is too complicated
        params = {}
        for key, value in chain(new, old, removed, unknown):
            # todo: if key in params: ...
            params[key] = value

        if self.image_param in params:
            new.remove(
                (self.image_param, params[self.image_param])
            )
            image, size, caption = self.handle_image(params[self.image_param])
            new.append(
                (self.image_param, image)
            )
            params[self.image_param] = image
            if not params.get(self.caption_param, ''):
                if self.caption_param in params:
                    new.remove(
                        (self.caption_param, params[self.caption_param])
                    )
                new.append(
                    (self.caption_param, caption)
                )
                params[self.caption_param] = caption
            if (size and not params.get(self.image_size_param, '')
                    and self.image_size_param in self.all_params):
                if self.image_size_param in params:
                    new.remove(
                        (self.image_size_param,
                         params[self.image_size_param])
                    )
                new.append(
                    (self.image_size_param, size)
                )
                params[self.image_size_param] = size

    def handle_image(self, image):
        # TODO: merge with .tools.parse_image
        caption = ''
        size = ''
        match = self.file_regex.fullmatch(image)
        if match:
            image, _, rest = match.group().partition('|')
            image = image.lstrip('[').strip()
            for x in rest[:-2].split('|'):
                if size and caption:
                    break
                if x.startswith('alt='):  # todo: l10n
                    continue
                if x.startswith('link='):
                    continue
                if not size and x.endswith('px'):
                    size = x.strip()
                    continue
                if not caption and not any(
                    word == x.strip() for word in (
                        self.site.getmagicwords(magic)
                        for magic in FilesFix.magic)):
                    caption = x
                    continue

        if not self.file_regex.search(image):
            image = pywikibot.page.url2unicode(image)
            image = re.sub('[ _]+', ' ', image).strip()

            if image.lower().startswith(tuple(
                    '%s:' % ns.lower() for ns in self.site.namespaces[6]))
                image = image.partition(':')[2].strip()

        return image, size, caption

    def deduplicate(self, params):
        keys = [i for i, j in params]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            pywikibot.warning('Duplicate arguments %s' % duplicates)
            for dupe in duplicates:
                values = [y for x, y in params if x == dupe]
                #print(dupe)
                #print(values)
                if '' in values:
                    params.remove((dupe, ''))
                    #values.remove('')
                #while len(set(values)) < len(values): todo

    def exit(self):
        super().exit()
        pywikibot.output('Current offset: %s' % self.offset)

# TODO: prepare for extending
def main(*args): # bot_class=InfoboxMigratingBot
    options = {}
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if genFactory.handle_arg(arg):
            continue
        if arg.startswith('-'):
            arg, sep, value = arg.partition(':')
            if value != '':
                options[arg[1:]] = value if not value.isdigit() else int(value)
            else:
                options[arg[1:]] = True

    while not options.get('template', None):
        options['template'] = pywikibot.input(
            'Enter the template you would like to work on:')
        options['new_template'] = pywikibot.input(
            'Enter the template to replace the previous one:')

    if not options.get('new_template', None):
        options['new_template'] = options['template']

    generator = genFactory.getCombinedGenerator()
    if not generator:
        genFactory.handle_arg('-transcludes:%s' % options['template'])
        generator = genFactory.getCombinedGenerator()

    bot = InfoboxMigratingBot(generator=generator, **options) # bot_class
    bot.run()


if __name__ == '__main__':
    main()
