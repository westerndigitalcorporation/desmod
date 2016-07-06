"""Full-featured, high-level modeling using `SimPy`__.

__ https://simpy.readthedocs.io/en/latest/contents.html

The `desmod` package provides a variety of tools for composing, configuring,
running, monitoring, and analyzing discrete event simulation (DES) models. It
builds on top of the :mod:`simpy` simulation kernel, providing features useful
for building large-scale models which are out-of-scope for :mod:`simpy` itself.

An understanding of SimPy is required to use desmod effectively.

Components
==========

The primary building-block for `desmod` models is the
:class:`~desmod.component.Component` class. Components provide a means for
partitioning the system to be modeled into manageable pieces. Components can
play a structural role by parenting other components; or play a behavioral role
by having processes and connections to other components; or sometimes play both
roles at once.

The :func:`desmod.dot.component_to_dot()` function may be used to create a
`DOT`__ language representation of the component hierarchy and/or the component
connection graph. The resulting DOT representation may be rendered to a variety
of graphical formats using `GraphViz`__ tools.

__ http://graphviz.org/content/dot-language
__ http://graphviz.org/

Configuration
=============

It is common for models to have configurable paramaters. Desmod provides an
opinionated mechanism for simulation configuration. A single, comprehensive
configuration dictionary captures all configuration for the simulation. The
configuration dictionary is propogated to all Components via the
:class:`~desmod.simulation.SimEnvironment`.

The various components (or component hierarchies) may maintain separate
configuration namespaces within the configuration dictionary by use of keys
conforming to the dot-separated naming convention. For example,
"mymodel.compA.cfgitem".

The :mod:`desmod.config` module provides various functionality useful for
managing configuration dictionaries.

Simulation
==========

Desmod takes care of the details of running simulations to allow focus on the
act of modeling.

Running a simulation is accomplished with either
:func:`~desmod.simulation.simulate()` or
:func:`~desmod.simulation.simulate_factors()`, depending whether running a
single simulation or a multi-factor set of simulations. In either case, the key
ingredients are the configuration dict and the model's top-level
:class:`~desmod.component.Component`. The :func:`~desmod.simulation.simulate()`
function takes responsibility for taking the simulation through its various
phases:

 - *Initialization*: where the components' `__init__()` methods are called.
 - *Elaboration*: where inter-component connections are made and components'
   processes are started.
 - *Simulation*: where discrete event simulation occurs.
 - *Post-simulation*: where simulation results are gathered.

# TODO: simulation results

Monitoring
==========

# TODO: tracers, probes, logging, etc.

"""

__all__ = ()
