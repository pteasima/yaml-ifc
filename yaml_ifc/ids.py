import uuid

import ifcopenshell.guid

NAMESPACE = uuid.NAMESPACE_URL
PREFIX = "yaml-ifc:"


def derived_global_id(yaml_id):
    digest = uuid.uuid5(NAMESPACE, PREFIX + yaml_id)
    return ifcopenshell.guid.compress(str(digest))


def global_id(yaml_id, explicit=None):
    if explicit:
        return explicit
    return derived_global_id(yaml_id)


def is_derived(stored, yaml_id):
    return stored == derived_global_id(yaml_id)
