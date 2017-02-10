Changlog
========

desmod-0.3.1 (2017-02-10)
-------------------------
* [NEW] Add sim.vcd.start_time and sim.vcd.stop_time
* [NEW] Add unit tests for desmod.tracer
* [NEW] Dump configuration to file in workspace
* [NEW] Add unit tests for desmod.dot
* [FIX] Use component scope instead of id() for DOT nodes
* [NEW] Colored component hierarchy in DOT
* [FIX] Repair typo in fuzzy_match() exception

desmod-0.3.0 (2017-01-23)
-------------------------
* [CHANGE] Overhaul progress display
* [NEW] Flexible control of simulation stop criteria
* [FIX] Support progress notification on spawned processes
* [FIX] Remove dead path in test_simulation.py
* [FIX] Various doc repairs to SimEnvironment
* [CHANGE] Add t parameter to SimEnvironment.time()
* [CHANGE Parse unit in SimEnvironment.time()
* [NEW] Add desmod.config.fuzzy_match()
* [REMOVE] Remove desmod.config.short_special()
* [NEW] Add coveralls to travis test suite
* [NEW] Add flush() to tracing subsystem
* [CHANGE] Do not use tox with travis
* [NEW] Add Python 3.6 support in travis
* [FIX] Repair gas_station.py for Python 2

desmod-0.2.0 (2016-10-25)
-------------------------
* [CHANGE] simulate_factors() now has factors parameter
* [NEW] simulate() can suppress exceptions
* [FIX] simulate_factors() respects sim.workspace.overwrite
* [CHANGE] Update config with missing defaults at runtime

desmod-0.1.6 (2016-10-25)
-------------------------
* [NEW] Add env.time() and 'sim.now' result
* [FIX] Enter workspace directory before instantiating env
* [CHANGE] Use yaml.safe_dump()
* [FIX] Add dist to .gitignore
* [FIX] Squash warning in setup.cfg

desmod-0.1.5 (2016-10-17)
-------------------------
* [NEW] Add Queue.size and Queue.remaining properties (#9)
* [NEW] Trace Queue's remaining capacity (#10)
* [NEW] Add Queue.when_new() event (#11)

desmod-0.1.4 (2016-09-21)
-------------------------
* [NEW] Add desmod.simulation.simulate_many()
* [FIX] Repair various docstring typos
* [FIX] Disable progress bar for simulate_factors() on Windows
* [NEW] Add CHANGELOG.txt to long description in setup.py

desmod-0.1.3 (2016-07-28)
-------------------------
* [NEW] Cancelable Queue events
* [CHANGE] Connection errors now raise ConnectError
* [FIX] Update pytest-flake8 and flake8 dependencies (yet again)

desmod-0.1.2 (2016-07-26)
-------------------------
* [NEW] Add "sim.log.buffering" configuration
* [FIX] Repair unit tests (pytest-flake8 dependency)
* [NEW] New optional `Queue.name` attribute
* [FIX] Use `repr()` for exception string in result dict

desmod-0.1.1 (2016-07-14)
-------------------------
* [FIX] Using 'True' and 'False' in expressions from the command line
* [CHANGE] Improve simulation workspace handling (sim.workspace.overwrite)
* [CHANGE] Make some 'sim.xxx' configuration keys optional
* [NEW] Gas Station example in docs
* [NEW] Add this CHANGELOG.rst and History page in docs

desmod-0.1.0 (2016-07-06)
-------------------------
* Initial public release
