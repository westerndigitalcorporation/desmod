=====================
``desmod.simulation``
=====================

.. automodule:: desmod.simulation

.. autoclass:: desmod.simulation.SimEnvironment

   .. autoinstanceattribute:: config
      :annotation:
   .. autoinstanceattribute:: rand
      :annotation:
   .. autoinstanceattribute:: timescale
      :annotation:
   .. autoinstanceattribute:: duration
      :annotation:
   .. autoattribute:: now
   .. autoattribute:: active_process
   .. automethod:: process(generator)
   .. automethod:: timeout(delay, value)
   .. automethod:: event()
   .. automethod:: all_of(events)
   .. automethod:: any_of(events)
   .. automethod:: schedule
   .. automethod:: peek
   .. automethod:: step

.. autofunction:: desmod.simulation.simulate

.. autofunction:: desmod.simulation.simulate_factors
