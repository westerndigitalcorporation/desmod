Changlog
========

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
