===========
Gas Station
===========

This example expands upon `SimPy's Gas Station Refueling example
<https://simpy.readthedocs.io/en/latest/examples/gas_station_refuel.html>`_,
demonstrating various desmod features.

.. note::

   Desmod's goal is to support large-scale modeling. Thus this example
   is somewhat larger-scale than the SimPy model it expands upon.

.. literalinclude:: code/gas_station.py

The simulation log, `sim.log`, shows what happened during the
simulation:

.. literalinclude:: code/sim.log

This example does not make heavy use of desmod's result-gathering
capability, but we can nonetheless see the minimal `results.yaml` file
generated from the simulation:

.. literalinclude:: code/results.yaml
