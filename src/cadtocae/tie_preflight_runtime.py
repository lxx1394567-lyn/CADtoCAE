"""CAE 2020: stage constraints, check slave ownership, then create Ties."""


class Step05TieBatch(object):
    def __init__(self):
        self.entries = []
        self.created = []
        self.diagnostics = []
        self.region_records = {}

    def stage(self, model, master_surface_name, slave_surface_name,
              master_instance, slave_instance, **parameters):
        self.entries.append((model, parameters))
        key = (id(model), text(parameters['name']))
        self.region_records[key] = dict(tie_name=text(parameters['name']),
            master_surface=parameters['master'], master_surface_name=abaqus_name(master_surface_name),
            master_instance=abaqus_name(master_instance), slave_surface=parameters['slave'],
            slave_surface_name=abaqus_name(slave_surface_name), slave_instance=abaqus_name(slave_instance),
            slave_face_ids=[])
        for face in getattr(parameters['slave'], 'faces', ()):
            self.region_records[key]['slave_face_ids'].append(int(face.index))

    def slave_geometry_keys(self, surface, surface_name):
        keys = set()
        for face in getattr(surface, 'faces', ()):
            instance = abaqus_name(face.instanceName)
            if not instance:
                raise ValueError('Slave face has no Instance identity')
            keys.add((instance, int(face.index)))
        if not keys:
            raise ValueError('Cannot inspect empty/unsupported Tie slave region '+surface_name)
        return keys

    def check(self):
        candidates, models, names = [], [], set()
        for model, parameters in self.entries:
            key = (id(model), text(parameters['name']))
            if key in names:
                raise ValueError('Duplicate planned Tie name '+key[1])
            names.add(key)
            candidates.append((model, key[1], parameters['slave'], self.region_records[key]['slave_surface_name']))
            if model not in models:
                models.append(model)
        # Include unrelated active existing Ties; planned/reused names are checked above.
        for model in models:
            for name in model.constraints.keys():
                constraint = model.constraints[name]
                if (id(model), text(name)) in names or getattr(constraint, 'suppressed', False):
                    continue
                if not hasattr(constraint, 'slave') or not hasattr(constraint, 'positionToleranceMethod'):
                    continue
                surface_name = surface_key(model.rootAssembly, constraint.slave)
                surface = item(model.rootAssembly.surfaces, surface_name)
                candidates.append((model, text(name), surface, surface_name))
        owners = {}
        self.diagnostics = []
        print('SLAVE CONFLICT PREFLIGHT')
        for model, tie, surface, surface_name in candidates:
            keys = sorted(self.slave_geometry_keys(surface, surface_name))
            grouped = {}
            for instance_name, face_id in keys:
                grouped.setdefault(instance_name, []).append(face_id)
            for instance_name in sorted(grouped):
                instances = getattr(model.rootAssembly, 'instances', {})
                instance = item(instances, instance_name, True)
                mesh_available = instance is not None and len(getattr(instance, 'nodes', ())) > 0
                record = dict(tie=tie, slave_region=surface_name, slave_instance=instance_name,
                    slave_face_ids=grouped[instance_name], geometry_keys=[],
                    mesh_available=mesh_available, node_level_check='skipped')
                for face_id in grouped[instance_name]:
                    record['geometry_keys'].append((instance_name, face_id))
                self.diagnostics.append(record)
                print('Tie = %s; slave instance = %s; slave face ids = %s; geometry keys = %s; mesh available = %s; node-level check = skipped' %
                    (tie, instance_name, record['slave_face_ids'], record['geometry_keys'], mesh_available))
            for key in keys:
                identity = (id(model), key)
                if identity in owners:
                    other_tie, other_region = owners[identity]
                    message = ('same slave geometry participates in multiple Tie constraints; '
                        'instance=%s; tie names=%s, %s; overlapping slave regions=%s, %s; face id=%s' %
                        (key[0], other_tie, tie, other_region, surface_name, key[1]))
                    print(message)
                    raise ValueError(message)
                owners[identity] = (tie, surface_name)
        print('duplicate slave geometry = none')
        return len(candidates)

    def finish(self, path):
        result = dict(status='FAILED', created=[], errors=[])
        try:
            result['checked_ties'] = self.check()
            for model, parameters in self.entries:
                if item(model.constraints, parameters['name'], True) is None:
                    model.Tie(**parameters)
                    self.created.append(text(parameters['name']))
            for model, parameters in self.entries:
                model.rootAssembly.regenerate()
            result['status'] = 'SUCCESS'
            print('Tie slave preflight passed; all planned Ties are present')
        except Exception as exc:
            result['errors'].append(str(exc))
            raise
        finally:
            result['created'] = self.created[:]
            result['geometry_checks'] = self.diagnostics[:]
            result['node_level_check'] = 'skipped'
            with open(path) as handle:
                report = json.load(handle)
            report['slave_preflight'] = result
            report['overall_status'] = result['status']
            sections = [report]
            for name in ('column_column_tie', 'column_hoop_tie'):
                if name in report:
                    sections.append(report[name])
            if 'column_beam_tie' in report:
                sections.append(report['column_beam_tie'])
            for group_report in report.get('column_hoop_groups',{}).values():
                sections.append(group_report)
            for section in sections:
                if section.get('status') == 'PENDING_TIE_PREFLIGHT':
                    section['status'] = result['status']
                if 'tie_created' in section:
                    section['tie_created'] = False
                for connection in section.get('connections', []):
                    connection['tie_present'] = False
                    for model, parameters in self.entries:
                        if text(parameters['name']) == connection['tie']:
                            connection['tie_present'] = item(model.constraints, parameters['name'], True) is not None
                    if 'created' in connection:
                        connection['created'] = connection['tie'] in self.created
                    if 'tie_created' in section and connection['tie'] in self.created:
                        section['tie_created'] = True
                if 'tie' in section:
                    section['tie_created'] = section['tie'] in self.created
                    for model, parameters in self.entries:
                        if text(parameters['name']) == section['tie']:
                            section['tie_present'] = item(model.constraints, parameters['name'], True) is not None
            if result['status'] != 'SUCCESS':
                report['status'] = 'FAILED'
                report.setdefault('errors', []).extend(result['errors'])
            with open(path, 'w') as handle:
                json.dump(report, handle, ensure_ascii=True, indent=2)
