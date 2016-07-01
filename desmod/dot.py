from itertools import cycle

from desmod.component import Component

_color_cycle = cycle([
    'dodgerblue4',
    'darkgreen',
    'darkorchid',
    'darkslategray',
    'deeppink4',
    'goldenrod4',
    'firebrick4',
])


def component_to_dot(top,
                     show_hierarchy=True,
                     show_connections=True,
                     show_processes=True):
    """Produce a dot stream from a component hierarchy.

    The DOT language representation of the component instance hierarchy can
    show the component hierarchy, the inter-component connections, components'
    processes, or any combination thereof.

    .. Note::
        The `top` component hierarchy must be initialized and all connections
        must be made in order for `component_to_dot()` to inspect these graphs.
        The :meth:`desmod.component.Component.elab_hook()` method is a good
        place to call `component_to_dot()` since the model is fully elaborated
        at that point and simulation has not yet started.

    :param Component top: Top-level component (instance).
    :param bool show_hierarchy:
        Should the component hierarchy be shown in the graph.
    :param bool show_connections:
        Should the inter-component connections be shown in the graph.
    :param bool show_processes:
        Should each component's processes be shown in the graph.
    :returns str:
        DOT language representation of the component/connection graph(s).

    """
    indent = '    '
    lines = ['strict digraph M {']
    lines.extend(indent + line
                 for line in _comp_hierarchy([top],
                                             show_hierarchy,
                                             show_connections,
                                             show_processes))
    if show_connections:
        lines.append('')
        lines.extend(indent + line
                     for line in _comp_connections(top))
    lines.append('}')
    return '\n'.join(lines)


def _comp_hierarchy(component_group,
                    show_hierarchy, show_connections, show_processes):
    component = component_group[0]
    if len(component_group) == 1:
        label_name = _comp_name(component)
    else:
        label_name = '{}..{}'.format(_comp_name(component_group[0]),
                                     _comp_name(component_group[-1]))

    if component._children and show_hierarchy:
        style = 'dotted'
    else:
        style = 'rounded'

    node_lines = [
        '{} [shape=box,style={},label=<'.format(_comp_id(component), style)
    ]

    label_lines = _comp_label(component, label_name, show_processes)
    if len(label_lines) == 1:
        node_lines[-1] += label_lines[0]
    else:
        node_lines.extend('    ' + line for line in label_lines)
    node_lines[-1] += '>];'

    if not component._children:
        return node_lines
    else:
        if show_hierarchy:
            indent = '    '
            lines = [
                'subgraph {} {{'.format(_cluster_id(component)),
                indent + 'label=<{}>'.format(_cluster_label(component_group))
            ]
        else:
            indent = ''
            lines = []
        if show_connections:
            lines.extend(indent + line for line in node_lines)
        for child_group in _child_type_groups(component):
            lines.extend(
                indent + line
                for line in _comp_hierarchy(child_group,
                                            show_hierarchy,
                                            show_connections,
                                            show_processes))
        if show_hierarchy:
            lines.append('}')
        return lines


def _comp_connections(component):
    lines = []
    for conn, src, src_conn, conn_obj in component._connections:
        attrs = {}
        if isinstance(conn_obj, Component):
            src = conn_obj
        elif (isinstance(conn_obj, list) and conn_obj and
              isinstance(conn_obj[0], Component)):
            src = conn_obj[0]
        else:
            attrs['label'] = '"{}"'.format(conn)
            attrs['color'] = attrs['fontcolor'] = next(_color_cycle)

        lines.append('{dst_id} -> {src_id} [{attrs}];'
                     .format(dst_id=_comp_id(component),
                             src_id=_comp_id(src),
                             attrs=_join_attrs(attrs)))

    for child_group in _child_type_groups(component):
        lines.extend(_comp_connections(child_group[0]))

    return lines


def _child_type_groups(component):
    child_type_groups = []
    child_types = {type(child) for child in component._children}
    for child_type in child_types:
        child_type_groups.append([child for child in component._children
                                  if type(child) is child_type])
    return child_type_groups


def _comp_name(component):
    if component.name:
        return component.name
    else:
        return type(component).__name__


def _comp_id(component):
    return '{}_{}'.format(_comp_name(component), id(component))


def _cluster_id(component):
    return 'cluster_{}_{}'.format(type(component).__name__, id(component))


def _cluster_label(component_group):
    if len(component_group) == 1:
        return '<b>{}</b>'.format(_comp_name(component_group[0]))
    else:
        return '<b>{}..{}</b>'.format(component_group[0].name,
                                      component_group[-1].name)


def _comp_label(component, label_name, show_processes):
    label_lines = ['<b>{}</b><br align="left"/>'.format(label_name)]
    if show_processes and component._processes:
        label_lines.append('<br/>')
        proc_funcs = set()
        for proc_func, _, _ in component._processes:
            if proc_func not in proc_funcs:
                proc_funcs.add(proc_func)
                label_lines.append(
                    '<i>{}</i><br align="left"/>'.format(proc_func.__name__))
    return label_lines


def _join_attrs(attrs):
    return ','.join('{}={}'.format(k, v)
                    for k, v in sorted(attrs.items()))
