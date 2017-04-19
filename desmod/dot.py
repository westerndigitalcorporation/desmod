"""Generate graphical representation of component hierarchy.

Component hierarchy, connections, and processes can be represented graphically
using the `Graphviz`_ `DOT language`_.

The :func:`component_to_dot()` function produces a DOT language string that can
be rendered into a variety of formats using Graphviz tools.  Because the
component hierarchy, connections, and processes are determined dynamically,
:func:`component_to_dot()` must be called with an instantiated component. A
good way to integrate this capabililty into a model is to call
:func:`component_to_dot()` from a component's
:meth:`desmod.component.Component.elab_hook()` method.

The ``dot`` program from `Graphviz`_ may be used to render the generated DOT
language description of the component hierarchy::

    dot -Tpng -o foo.png foo.dot

For large component hierarchies, the ``osage`` program (also part of Graphviz)
can produce a more compact layout::

    osage -Tpng -o foo.png foo.dot

.. _Graphviz: http://graphviz.org/
.. _DOT language: http://graphviz.org/content/dot-language

"""
from itertools import cycle, groupby

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


def generate_dot(top, config=None):
    """Generate dot files based on 'sim.dot' configuration.

    The ``sim.dot.enable`` configuration controls whether any dot file
    generation is performed. The remaining ``sim.dot`` configuration items have
    no effect unless ``sim.dot.enable`` is ``True``.

    The ``sim.dot.colorscheme`` configuration controls the colorscheme used in
    the generated DOT files. See :func:`component_to_dot` for more detail.

    The ``sim.dot.all.file``, ``sim.dot.hier.file``, and ``sim.dot.conn.file``
    configuration items control the names of the generated DOT files. These
    items can also be set to the empty string to disable generating a
    particular file.

    The nominal way to use this function is to call it from the top component's
    :meth:`Component.elab_hook()`. E.g.::

        def elab_hook(self):
            ...
            generate_dot(self)
            ...

    """
    config = top.env.config if config is None else config

    enable = config.setdefault('sim.dot.enable', False)
    colorscheme = config.setdefault('sim.dot.colorscheme', '')
    all_filename = config.setdefault('sim.dot.all.file', 'all.dot')
    hier_filename = config.setdefault('sim.dot.hier.file', 'hier.dot')
    conn_filename = config.setdefault('sim.dot.conn.file', 'conn.dot')

    if not enable:
        return

    if all_filename:
        with open(all_filename, 'w') as dot_file:
            dot_file.write(component_to_dot(top,
                                            show_hierarchy=True,
                                            show_connections=True,
                                            show_processes=True,
                                            colorscheme=colorscheme))

    if hier_filename:
        with open(hier_filename, 'w') as dot_file:
            dot_file.write(component_to_dot(top,
                                            show_hierarchy=True,
                                            show_connections=False,
                                            show_processes=False,
                                            colorscheme=colorscheme))

    if conn_filename:
        with open(conn_filename, 'w') as dot_file:
            dot_file.write(component_to_dot(top,
                                            show_hierarchy=False,
                                            show_connections=True,
                                            show_processes=False,
                                            colorscheme=colorscheme))


def component_to_dot(top,
                     show_hierarchy=True,
                     show_connections=True,
                     show_processes=True,
                     colorscheme=''):
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
    :param str colorscheme:
        One of the `Brewer color schemes`_ supported by graphviz, e.g. "blues8"
        or "set27". Each level of the component hierarchy will use a different
        color from the color scheme. N.B. Brewer color schemes have between 3
        and 12 colors; one should be chosen that has at least as many colors as
        the depth of the component hierarchy.
    :returns str:
        DOT language representation of the component/connection graph(s).

    .. _Brewer color schemes: http://graphviz.org/content/color-names#brewer

    """
    indent = '    '
    lines = ['strict digraph M {']
    lines.extend(indent + line
                 for line in _comp_hierarchy([top],
                                             show_hierarchy,
                                             show_connections,
                                             show_processes,
                                             colorscheme))
    if show_connections:
        lines.append('')
        lines.extend(indent + line
                     for line in _comp_connections(top))
    lines.append('}')
    return '\n'.join(lines)


def _comp_hierarchy(component_group,
                    show_hierarchy, show_connections, show_processes,
                    colorscheme, _level=1):
    component = component_group[0]
    if len(component_group) == 1:
        label_name = _comp_name(component)
    else:
        label_name = '{}..{}'.format(_comp_name(component_group[0]),
                                     _comp_name(component_group[-1]))

    if component._children and show_hierarchy:
        border_style = 'dotted'
    else:
        border_style = 'rounded'
    if colorscheme:
        style = 'style="{},filled",fillcolor="/{}/{}"'.format(
            border_style, colorscheme, _level)
    else:
        style = 'style=' + border_style

    node_lines = [
        '"{}" [shape=box,{},label=<'.format(_comp_scope(component), style)
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
                'subgraph "{}" {{'.format(_cluster_id(component)),
                indent + 'label=<{}>'.format(_cluster_label(component_group)),
            ]
            if colorscheme:
                lines.extend([
                    indent + 'style="filled"',
                    indent + 'fillcolor="/{}/{}"'.format(colorscheme, _level),
                ])
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
                                            show_processes,
                                            colorscheme,
                                            _level + 1))
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

        lines.append('"{dst_id}" -> "{src_id}" [{attrs}];'
                     .format(dst_id=_comp_scope(component),
                             src_id=_comp_scope(src),
                             attrs=_join_attrs(attrs)))

    for child_group in _child_type_groups(component):
        lines.extend(_comp_connections(child_group[0]))

    return lines


def _child_type_groups(component):
    children = sorted(component._children, key=_comp_name)
    for _, group in groupby(children, lambda child: str(type(child))):
        yield list(group)


def _comp_name(component):
    return component.name if component.name else type(component).__name__


def _comp_scope(component):
    return component.scope if component.scope else type(component).__name__


def _cluster_id(component):
    return 'cluster_' + _comp_scope(component)


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
