"""Single release identity for the Step06 desktop generator."""
STEP06_VERSION = '0.2.14'


def version_fields():
    return dict(step06_version=STEP06_VERSION,generator_version=STEP06_VERSION)


def preload_record():
    return dict(preload_target_n=20000.0,preload_local_component=1,preload_policy='PRESERVE_EXISTING_NO_LOAD_CREATED')
