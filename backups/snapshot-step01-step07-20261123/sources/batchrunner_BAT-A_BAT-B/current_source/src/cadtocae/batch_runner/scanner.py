from dataclasses import dataclass, field, asdict
from pathlib import Path
import hashlib

SUFFIXES = (
    ('_create_parts_in_cae.py',), ('_assembly_frame.py',),
    ('_analysis_setup.py',), ('_step06_hole_setup.py',),
    ('_step07_01_tie_setup.py',), ('_step07_02_step_setup.py',),
    ('_step07_03_boundary_setup.py',), ('_step07_04_mesh_setup.py',),
    ('_step07_05_load_setup.py',),
)
STATUSES = ('SUCCESS', 'FAILED', 'MISSING', 'BLOCKED', 'PENDING', 'RUNNING', 'SKIPPED', 'STALE', 'READY', 'MISSING_INPUT', 'REVIEW_REQUIRED')

@dataclass
class Stage:
    number: int
    script: str | None = None
    status: str = 'MISSING'
    reasons: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    contract: dict = field(default_factory=dict)
    history_status: str | None = None
    checkpoint: dict = field(default_factory=dict)
    history_error: str | None = None
    outputs: list = field(default_factory=list)
    embedded_inputs: list = field(default_factory=list)
    inspected_source_sha256: str | None = None
    plan_action: str = 'MISSING'
    change_reasons: list = field(default_factory=list)

@dataclass
class Project:
    prefix: str
    folder: str
    stages: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    inventory: list = field(default_factory=list)

    @property
    def key(self):
        return hashlib.sha256((self.folder.casefold() + '/' + self.prefix.casefold()).encode()).hexdigest()[:20]

    def to_dict(self):
        return dict(key=self.key, plan=[s.number for s in self.stages if s.status in ('PENDING', 'READY')], **asdict(self))

def scan(root, exclude=()):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Project root must be a directory')
    groups = {}
    excluded = [Path(p).resolve() for p in exclude]
    for path in sorted(root.rglob('*.py')):
        if any(p == path or p in path.parents for p in excluded):
            continue
        if any(x in path.parts for x in ('.git', '__pycache__', '.batchrunner', 'build', 'dist', '过程文件', 'Step07_Logs', 'CAE_Results')):
            continue
        if path.is_symlink():
            continue
        for index, suffixes in enumerate(SUFFIXES):
            suffix = next((s for s in suffixes if path.name.lower().endswith(s)), None)
            if not suffix:
                continue
            prefix = path.name[:-len(suffix)]
            if not prefix:
                continue
            key = (str(path.parent.resolve()).casefold(), prefix.casefold())
            project = groups.setdefault(key, Project(prefix, str(path.parent.resolve()), [Stage(i+1) for i in range(len(SUFFIXES))]))
            stage = project.stages[index]
            if stage.script:
                project.conflicts.append('Multiple versions for stage %d: %s, %s' % (index+1, stage.script, path))
            else:
                stage.script = str(path.resolve())
                stage.status = 'PENDING'
    projects = list(groups.values())
    for p in projects:
        duplicates = [q.folder for q in projects if q.prefix.casefold() == p.prefix.casefold() and q.folder != p.folder]
        if duplicates:
            p.conflicts.append('Duplicate project prefix in directories: ' + ', '.join(duplicates))
    return projects
