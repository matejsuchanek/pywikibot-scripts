# -*- coding: utf-8  -*-
import pywikibot
import re

class CheckWiki(object):

    '''Object to load errors from CheckWiki'''

    def __init__(self, site, **kwargs):
        self.site = site
        self.numberToClass = {
            81: DuplicateReferences
        }

    def getClass(self, number):
        return self.numberToClass[num](self.site)

    def loadError(self, number): # todo
        pass

    def errorGenerator(self, number): # todo
        pass

    def applyError(self, num, text, replaced=[]):
        error = getClass(num)
        return error.apply(text, replaced)

    def applyErrors(self, text, replaced=[]):
        for num in self.numberToClass.keys():
            text = self.applyError(num, text, replaced)
        return text

class CheckWikiError(object):

    '''Abstract class for each error to extend'''

    def __init__(self, site, number, **kwargs):
        self.site = site
        self.number = number

    def loadError(self):
        pass

    def apply(self):
        pass # todo: abstract

class DuplicateReferences(CheckWikiError):

    def __init__(self, site, **kwargs):
        super(DuplicateReferences, self).__init__(site, 81)

    def apply(self, text, replaced):
        ref_regex = re.compile(
            '<ref(?= |>)(?P<params>[^>]*)(?: ?/|>(?P<content>(?:(?!</?ref).)+)</ref)>',
            re.S | re.U)

        param_regex = re.compile(
            '(?P<param>[a-z]+) *= *'
            '(?P<quote>[\'"])?'
            r'(?P<content>(?(quote)(?!(?P=quote)|>).|\w)+)'
            '(?(quote)(?P=quote)|)',
            re.U)

        named_contents = {}
        duplicate_named_contents = {}
        unnamed_contents = {}
        duplicate_unnamed_contents = {}
        names = {}
        destroyed_names = {}
        i = {}

        def getParams(params):
            name = ''
            group = ''
            for match in re.finditer(param_regex, params):
                if match.group('param') == 'group':
                    group = match.group('content').strip()
                elif match.group('param') == 'name':
                    name = match.group('content').strip()
            return (name, group)

        for match in re.finditer(ref_regex, text):
            if match.group('content') is None:
                continue
            content = match.group('content').strip()
            name, group = getParams(match.group('params'))

            if group not in named_contents:
                named_contents[group] = [] # the order is important!
                duplicate_named_contents[group] = set()
                unnamed_contents[group] = set()
                duplicate_unnamed_contents[group] = set()
                names[group] = set()
                destroyed_names[group] = {}
                i[group] = 1

            if name == '':
                if content in unnamed_contents[group]:
                    duplicate_unnamed_contents[group].add(content)
                else:
                    unnamed_contents[group].add(content)
            else:
                names[group].add(name)
                if (name, content) not in named_contents[group]:
                    named_contents[group].append(
                        (name, content)
                    )

        def replaceRef(match):
            if match.group('content') is None:
                return match.group(0)

            content = match.group('content').strip()
            name, group = getParams(match.group('params'))
            if name != '':
                if name in destroyed_names[group]:
                    return match.group(0) # do in the second round

                for ref_name, ref_content in duplicate_named_contents[group]:
                    if ref_content == content:
                        if ref_name != name:
                            destroyed_names[group][name] = ref_name
                        return u'<ref name="%s"%s />' % (
                            ref_name, u' group="%s"' % group if group != '' else '')

                for ref_name, ref_content in named_contents[group]:
                    if ref_content == content:
                        if ref_name == name:
                            named_contents[group].remove(
                                (name, content)
                            )
                            duplicate_named_contents[group].add(
                                (name, content)
                            )
                        else:
                            destroyed_names[group][name] = ref_name
                        return match.group(0)
                    if ref_name == name:
                        pass # this should not happen!

            else:
                for ref_name, ref_content in named_contents[group] + list(duplicate_named_contents[group]):
                    if ref_content == content:
                        return u'<ref name="%s"%s />' % (
                            ref_name, u' group="%s"' % group if group != '' else '')

                if content in duplicate_unnamed_contents[group]:
                    new_name = 'rfr%s' % i[group]
                    while new_name in names[group]:
                        i[group] += 1
                        new_name = 'rfr%s' % i[group]
                    names[group].add(new_name)
                    duplicate_named_contents[group].add(
                        (new_name, content)
                    )
                    return u'<ref name="%s"%s>%s</ref>' % (
                        new_name, u' group="%s"' % group if group != '' else '', content)

            return match.group(0)

        def repairNamesAndTidy(match):
            content = match.group('content')
            params = match.group('params')
            name, group = getParams(params)
            if name.isdigit() and name not in destroyed_names[group]:
                new_name = 'rfr%s' % i[group]
                while new_name in names[group]:
                    i[group] += 1
                    new_name = 'rfr%s' % i[group]
                names[group].add(new_name)
                destroyed_names[group][name] = new_name

            if name in destroyed_names[group]:
                if content is None:
                    return u'<ref name="%s"%s />' % (
                        destroyed_names[group][name],
                        u' group="%s"' % group if group != '' else '')
                else:
                    return u'<ref name="%s"%s>%s</ref>' % (
                        destroyed_names[group][name],
                        u' group="%s"' % group if group != '' else '',
                        content.strip())

            ref = '<ref'
            for param_match in re.finditer(param_regex, params):
                param = param_match.group('param')
                quote = param_match.group('quote') or '"'
                param_content = param_match.group('content').strip()
                ref += ' {param}={quote}{content}{quote}'.format(
                    param=param, quote=quote, content=param_content)
            if content is not None:
                return ref + u'>%s</ref>' % content.strip()
            else:
                return ref + ' />'

        new_text = re.sub(ref_regex, replaceRef, text)
        if new_text != text:
            text = re.sub(ref_regex, repairNamesAndTidy, new_text)
            replaced.append(u'oprava referencí')
        return text
