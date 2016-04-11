import functools
import re

import simpy
from vcd import VCDWriter


class Tracer(object):

    cfg_scope = 'sim.xxx'

    def __init__(self, env):
        self.enabled = env.config.get(self.cfg_scope + '.enable', False)
        self.env = env
        include_pat = env.config.get(self.cfg_scope + '.include_pat', ['.*'])
        exclude_pat = env.config.get(self.cfg_scope + '.exclude_pat', [])
        self._include_re = [re.compile(pat) for pat in include_pat]
        self._exclude_re = [re.compile(pat) for pat in exclude_pat]

    def is_probe_enabled(self, probe):
        return (self.enabled and
                any(r.match(probe.scope) for r in self._include_re) and
                not any(r.match(probe.scope) for r in self._exclude_re))

    def open(self):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()

    def activate_probe(self, probe):
        raise NotImplementedError()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class VCDTracer(Tracer):

    cfg_scope = 'sim.vcd'

    def open(self):
        dump_filename = self.env.config['sim.vcd.dump_file']
        timescale = self.env.config['sim.timescale']
        self.dump_file = open(dump_filename, 'w')  # TODO try 'wb'
        self.vcd = VCDWriter(self.dump_file, timescale=timescale)
        if self.env.config.get('sim.gtkw.live'):
            from vcd.gtkw import spawn_gtkwave_interactive
            save_filename = self.env.config['sim.gtkw.file']
            spawn_gtkwave_interactive(dump_filename, save_filename, quiet=True)

    def close(self):
        self.vcd.close(self.env.now)
        self.dump_file.close()

    def activate_probe(self, probe):
        assert self.enabled
        vcd_hints = probe.hints.get('vcd', {})
        var_type = vcd_hints.get('var_type')
        if var_type is None:
            if isinstance(probe.target, simpy.Container):
                if isinstance(probe.target.level, float):
                    var_type = 'real'
                else:
                    var_type = 'integer'
            elif isinstance(probe.target, (simpy.Resource, simpy.Store)):
                var_type = 'integer'
            else:
                raise ValueError(
                    'Could not infer VCD var_type for {}'.format(probe.scope))

        kwargs = {k: vcd_hints[k]
                  for k in ['size', 'init', 'ident']
                  if k in vcd_hints}

        if var_type == 'integer':
            register_meth = self.vcd.register_int
        elif var_type == 'real':
            register_meth = self.vcd.register_real
        elif var_type == 'event':
            register_meth = self.vcd.register_event
        else:
            register_meth = self.vcd_register_var
            kwargs['var_type'] = var_type

        if 'init' not in kwargs:
            if isinstance(probe.target, simpy.Container):
                kwargs['init'] = probe.target.level
            elif isinstance(probe.target, simpy.Resource):
                kwargs['init'] = (len(probe.target.users)
                                  if probe.target.users else 'z')
            elif isinstance(probe.target, simpy.Store):
                kwargs['init'] = len(probe.target.items)

        var = register_meth(probe.parent_scope, probe.name, **kwargs)

        return functools.partial(self.vcd.change, var)
