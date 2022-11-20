__all__ = (
    'format_dictionary',
    'format_list',
    'QUOTES_SINGLE',
    'QUOTES_DOUBLE',
)

QUOTES_SINGLE = 1
QUOTES_DOUBLE = 2


def _indent(level, **kwargs):
    if kwargs.get('use_tabs') is True:
        return (level + 1) * '\t'
    else:
        return ((level + 1) * 4) * ' '


def _wrap_quotes(text, quote):
    if quote in text:
        text = text.replace(quote, '\\' + quote)
    return f'{quote}{text}{quote}'


def _format_string(text, **kwargs):
    opt = kwargs.get('force_quotes', 0)
    if opt == QUOTES_SINGLE:
        text = _wrap_quotes(text, "'")
    elif opt == QUOTES_DOUBLE:
        text = _wrap_quotes(text, '"')
    else:
        assert opt == 0
        text = (_wrap_quotes(text, '"')
                if "'" in text else _wrap_quotes(text, "'"))
    return text


def _format_key(key, **kwargs):
    if key is None:
        return '[nil]'
    elif isinstance(key, (int, float)):
        key = str(key)
        return f'[{key.lower()}]'  # lower for booleans (which are ints)
    else:
        assert isinstance(key, str)
        if not key.isalnum() or kwargs.get('quotes_always') is True:
            return '[%s]' % _format_string(key, **kwargs)
        else:
            return key


def _format_value(value, level, **kwargs):
    if isinstance(value, dict):
        return _format_dictionary(value, level + 1, **kwargs)
    elif isinstance(value, (list, tuple)):
        return _format_list(value, level + 1, **kwargs)
    elif isinstance(value, (int, float)):
        return str(value).lower()  # lower for booleans (which are ints)
    else:
        return _format_string(value, **kwargs)


def _format_pair(key, value, level, **kwargs):
    return '%s = %s,' % (_format_key(key, **kwargs),
                         _format_value(value, level, **kwargs))


def _format_list(data, level, **kwargs):
    init = '\n' + _indent(level, **kwargs)
    string = ''
    if kwargs.get('show_keys') is True:
        for i, item in enumerate(data, start=1):
            string += init + _format_pair(i, item, **kwargs)
    else:
        for item in data:
            string += init + _format_value(item, level, **kwargs) + ','
    return '{' + string + '\n' + _indent(level-1, **kwargs) + '}'


def _format_dictionary(data, level, **kwargs):
    init = '\n' + _indent(level, **kwargs)
    string = ''
    keys = data.keys()
    if kwargs.get('sort_keys') is True:
        keys = sorted(keys)
    for key in keys:
        string += init + _format_pair(key, data[key], level, **kwargs)
    return '{' + string + '\n' + _indent(level-1, **kwargs) + '}'


def format_list(data, level=0, **kwargs):
    assert isinstance(data, (list, tuple))
    return _format_list(data, level, **kwargs)


def format_dictionary(data, level=0, **kwargs):
    assert isinstance(data, dict)
    return _format_dictionary(data, level, **kwargs)
