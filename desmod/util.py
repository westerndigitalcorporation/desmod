import string

_formatter = string.Formatter()


def partial_format(format_string, **kwargs):
    """Partially replace replacement fields in format string.

    Partial formatting allows a format string to be progressively formatted.
    This may be helpful to either amortize the expense of formatting or allow
    different entities (with access to different information) cooperatively
    format a string.

    Only named replacement fields are supported; positional replacement fields
    are not supported.

    :param str format_string: Format string to partially apply replacements.
    :param kwargs: Replacements for named fields.
    :returns: Partially formatted format string.

    """
    result = []
    for literal, field, spec, conversion in _formatter.parse(format_string):
        if literal:
            result.append(literal)
        if field is not None:
            spec_list = [field]
            if conversion:
                spec_list.extend(['!', conversion])
            if spec:
                spec_list.extend([':', spec])
            inner_spec = ''.join(spec_list)
            formatted_inner = partial_format(inner_spec, **kwargs)
            if not field or field.isdigit() or field not in kwargs:
                result.extend(['{{', formatted_inner, '}}'])
            else:
                result.extend(['{', formatted_inner, '}'])
    return ''.join(result).format(**kwargs)
