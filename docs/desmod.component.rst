====================
``desmod.component``
====================

.. automodule:: desmod.component

.. autoclass:: desmod.component.Component

   .. autoinstanceattribute:: env
      :annotation:
   .. autoinstanceattribute:: name
      :annotation:
   .. autoinstanceattribute:: index
      :annotation:
   .. autoinstanceattribute:: scope
      :annotation:
   .. autoinstanceattribute:: children
      :annotation:
   .. autoinstanceattribute:: error(*values)
      :annotation:
   .. autoinstanceattribute:: warn(*values)
      :annotation:
   .. autoinstanceattribute:: info(*values)
      :annotation:
   .. autoinstanceattribute:: debug(*values)
      :annotation:
   .. automethod:: add_process
   .. automethod:: add_processes
   .. automethod:: add_connections
   .. automethod:: connect
   .. automethod:: connect_children
   .. automethod:: pre_init
   .. automethod:: elaborate
   .. automethod:: elab_hook
   .. automethod:: post_simulate
   .. automethod:: post_sim_hook
   .. automethod:: get_result
   .. automethod:: get_result_hook
