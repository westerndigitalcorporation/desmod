import string

_formatter = string.Formatter()


def partial_format(format_string, *args, **kwargs):
    used_args = set()
    result, _ = _partial_format(format_string, args, kwargs, used_args)
    _formatter.check_unused_args(used_args, args, kwargs)
    return result


def _partial_format(format_string, args, kwargs, used_args, recursion_depth=2,
                    auto_arg_index=0):
    if recursion_depth < 0:
        raise ValueError('Max string recursion exceeded')
    result = []
    for literal_text, field_name, format_spec, conversion in \
            _formatter.parse(format_string):

        if literal_text:
            result.append(literal_text)

        if field_name is not None:
            if not field_name:
                if auto_arg_index is None:
                    raise ValueError('cannot switch from manual field '
                                     'numbering to automatic field numbering')
                field = str(auto_arg_index)
                auto_arg_index += 1
            elif field_name.isdigit():
                if auto_arg_index:
                    raise ValueError('cannot switch from automatic field '
                                     'numbering to manual field numbering')
                auto_arg_index = None
                field = field_name
            else:
                field = field_name

            try:
                obj, arg_used = _formatter.get_field(field, args, kwargs)
            except (KeyError, IndexError):
                spec_list = []
                if field_name or auto_arg_index is None:
                    spec_list.append(field)
                if conversion:
                    spec_list.extend(['!', conversion])
                if format_spec:
                    spec_list.extend([':', format_spec])
                inner_spec = ''.join(spec_list)
                formatted_inner_spec, auto_arg_index = _partial_format(
                    inner_spec, args, kwargs, used_args, recursion_depth-1,
                    auto_arg_index)
                result.extend(['{', formatted_inner_spec, '}'])
            else:
                used_args.add(arg_used)
                obj = _formatter.convert_field(obj, conversion)
                format_spec, auto_arg_index = _partial_format(
                    format_spec, args, kwargs, used_args, recursion_depth-1,
                    auto_arg_index)

                result.append(format(obj, format_spec))

    return ''.join(result), auto_arg_index
