import string

_formatter = string.Formatter()


def partial_format(format_string, **kwargs):
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
