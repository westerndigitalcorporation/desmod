"""Component is the building block for desmod models.

Hierarchy
---------

A desmod model consists of a directed acyclical graph (DAG) of
:class:`Component` subclasses. Each Component is composed of zero or more child
Components. A single top-level Component class is passed to the
:func:`~desmod.simulation.simulate()` function to initiate simulation.

The :class:`Component` hierarchy does not define the behavior of a model, but
instead exists as a tool to build large models out of composable and
encapsulated pieces.

Connections
-----------

Components connect to other components via connection objects. Each component
is responsible for declaring the names of external connections as well as make
connections for its child components. The final network of inter-component
connections is neither directed (a connection object may enable two-way
communication), acyclic (groups of components may form cyclical connections),
nor constrained to match the component hierarchy.

Ultimately, a connection between two components means that each component
instance has a [pythonic] reference to the connection object.

In the spirit of Python, the types connection objects are flexible and dynamic.
A connection object may be of any type--it is up to the connected components to
cooperatively decide how to use the connection object for communication. That
said, some object types are more useful than others for connections. Some
useful connection object types include:

 * :class:`desmod.queue.Queue`
 * :class:`simpy.resources.resource.Resource`

Processes
---------

A component may have zero or more simulation processes
(:class:`simpy.events.Process`). It is these processes that give a model its
simulation-time behavior. The process methods declared by components are
started at simulation time. These "standing" processes may dynamically launch
addtional processes using `self.env.process()`.

Use Cases
---------

Given the flexibility components to have zero or more children, zero or more
processes, and zero or more connections, it can be helpful to give names to
the various roles components may play in a model.

 * Structural Component -- a component with child components, but no processes
 * Behavioral Component -- a component with processes, but no child components
 * Hybrid Component -- a component with child components and processes
 * State Component -- a component with neither children or processes

It is typical for the top-level component in a model to be purely structural,
while behavioral components are leaves in the model DAG.

A component with neither children or processes may still be useful. Such a
component could, for example, be used as a connection object.

"""


class ConnectError(Exception):
    pass


class Component(object):
    """Building block for composing models.

    This class is meant to be subclassed. Component subclasses must declare
    their children, connections, and processes.

    :param Component parent: Parent component or None for top-level Component.
    :param SimEnvironment env: SimPy simulation environment.
    :param str name: Optional name of Component instance.
    :param int index:
        Optional index of Component. This is used when multiple sibling
        components of the same type are instantiated as an array/list.
    :param TraceManager tracemgr:
        The :func:`desmod.simulation.simulate()` function is responsible for
        this TraceManager parameter.

    """

    #: Short/friendly name used in the scope (class attribute).
    base_name = ''

    def __init__(self, parent, env=None, name=None, index=None, tracemgr=None):
        assert parent or (env and tracemgr)

        #: The simulation environment; a :class:`SimEnvironment` instance.
        self.env = parent.env if env is None else env
        self.tracemgr = parent.tracemgr if tracemgr is None else tracemgr

        #: The component name (str).
        self.name = ((self.base_name if name is None else name) +
                     ('' if index is None else str(index)))

        #: Index of Component instance within group of sibling instances.
        #: Will be None for un-grouped Components.
        self.index = index

        if parent is None or not parent.scope:
            #: String indicating the full scope of Component instance in the
            #: Component DAG.
            self.scope = self.name
        else:
            self.scope = parent.scope + '.' + self.name

        if parent:
            parent._children.append(self)

        self._children = []
        self._processes = []
        self._connections = []
        self._not_connected = set()

        #: Log an error message.
        self.error = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'ERROR'})
        #: Log a warning message.
        self.warn = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'WARNING'})
        #: Log an informative message.
        self.info = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'INFO'})
        #: Log a debug message.
        self.debug = self.tracemgr.get_trace_function(
            self.scope, log={'level': 'DEBUG'})

    def add_process(self, process_func, *args, **kwargs):
        """Add a process method to be run at simulation-time.

        Subclasses should call this in `__init__()` to declare the process
        methods to be started at simulation-time.

        :param function process_func:
            Typically a bound method of the Component subclass.
        :param args: arguments to pass to `process_func`.
        :param kwargs: keyword arguments to pass to `process_func`.

        """
        self._processes.append((process_func, args, kwargs))

    def add_processes(self, *process_funcs):
        """Declare multiple processes at once.

        This is a convenience wrapper for :meth:`add_process()` that may be
        used to quickly declare a list of process methods that do not require
        any arguments.

        :param process_funcs: argument-less process functions (methods).

        """
        for process_func in process_funcs:
            self.add_process(process_func)

    def add_connections(self, *connection_names):
        """Declare names of externally-provided connection objects.

        The named connections must be connected (assigned) by an ancestor at
        elaboration time.

        """
        self._not_connected.update(connection_names)

    def connect(self, dst, dst_connection, src=None, src_connection=None,
                conn_obj=None):
        """Assign connection object from source to destination component.

        At elaboration-time, Components must call `connect()` to make the
        connections declared by descendant (child, grandchild, etc.)
        components.

        .. Note::

            :meth:`connect()` is nominally called from
            :meth:`connect_children()`.

        :param Component dst:
            Destination component being assigned the connection object.
        :param str dst_connection:
            Destination's name for the connection object.
        :param Component src:
            Source component providing the connection object. If omitted, the
            source component is assumed to be `self`.
        :param str src_connection:
            Source's name for the connection object. If omitted,
            `dst_connection` is used.
        :param conn_obj:
            The connection object to be assigned to the destination component.
            This parameter may typically be omitted in which case the
            connection object is resolved using `src` and `src_connection`.

        """
        if src is None:
            src = self
        if src_connection is None:
            src_connection = dst_connection
        if conn_obj is None:
            if hasattr(src, src_connection):
                conn_obj = getattr(src, src_connection)
            else:
                raise ConnectError(
                    'src "{}" (class {}) does not have attr "{}"'.format(
                        src.scope, type(src).__name__, src_connection))
        if dst_connection in dst._not_connected:
            setattr(dst, dst_connection, conn_obj)
            dst._not_connected.remove(dst_connection)
            dst._connections.append(
                (dst_connection, src, src_connection, conn_obj))
        else:
            raise ConnectError(
                'dst "{}" (class {}) does not declare connection "{}"'.format(
                    dst.scope, type(dst).__name__, dst_connection))

    def connect_children(self):
        """Make connections for descendant components.

        This method must be overridden in Component subclasses that need to
        make any connections on behalf of its descendant components.
        Connections are made using :meth:`connect()`.

        """
        if any(child._not_connected for child in self._children):
            raise ConnectError(
                '{0} has unconnected children; implement '
                '{0}.connect_children()'.format(type(self).__name__))

    def auto_probe(self, name, target=None, **hints):
        if target is None:
            target = getattr(self, name)
        target_scope = '.'.join([self.scope, name])
        self.tracemgr.auto_probe(target_scope, target, **hints)

    def get_trace_function(self, name, **hints):
        target_scope = '.'.join([self.scope, name])
        return self.tracemgr.get_trace_function(target_scope, **hints)

    @classmethod
    def pre_init(cls, env):
        """Override-able class method called prior to model initialization.

        Component subclasses may override this classmethod to gain access
        to the simulation environment (`env`) prior to :meth:`__init__()` being
        called.

        """
        pass

    def elaborate(self):
        """Recursively elaborate the model.

        The elaboration phase prepares the model for simulation. Descendant
        connections are made and components' processes are started at
        elaboration-time.

        """
        self.connect_children()
        for child in self._children:
            if child._not_connected:
                raise ConnectError('{scope}.{conn_name} not connected'.format(
                    scope=child.scope, conn_name=child._not_connected.pop()))
            child.elaborate()
        for proc, args, kwargs in self._processes:
            self.env.process(proc(*args, **kwargs))
        self.elab_hook()

    def elab_hook(self):
        """Hook called after elaboration and before simulation phase.

        Component subclasses may override :meth:`elab_hook()` to inject
        behavior after elaboration, but prior to simulation.

        """
        pass

    def post_simulate(self):
        """Recursively run post-simulation hooks."""
        for child in self._children:
            child.post_simulate()
        self.post_sim_hook()

    def post_sim_hook(self):
        """Hook called after simulation completes.

        Component subclasses may override `post_sim_hook()` to inject behavior
        after the simulation completes successfully. Note that
        `post_sim_hook()` will not be called if the simulation terminates with
        an unhandled exception.

        """
        pass

    def get_result(self, result):
        """Recursively compose simulation result dict.

        Upon successful completion of the simulation phase, each component in
        the model has the opportunity to add-to or modify the `result` dict via
        its :meth:`get_result_hook` method.

        The fully composed `result` dict is returned by :func:`simulate`.

        :param dict result: Result dictionary to be modified.

        """
        for child in self._children:
            child.get_result(result)
        self.get_result_hook(result)

    def get_result_hook(self, result):
        """Hook called after result is composed by descendant components."""
        pass
