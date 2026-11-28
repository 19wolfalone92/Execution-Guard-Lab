"""Fail-closed validator for the fixed registry's Draft 2020-12 vocabulary.

This adapter avoids native rpds in WASI. The tests compare its supported
contracts and validation decisions against the repository's full validator.
"""
import math
import re

_TYPES = {
    'object': lambda v: type(v) is dict,
    'array': lambda v: type(v) is list,
    'null': lambda v: v is None,
    'boolean': lambda v: type(v) is bool,
    'string': lambda v: type(v) is str,
    'number': lambda v: type(v) is int or type(v) is float and math.isfinite(v),
    'integer': lambda v: type(v) is int or type(v) is float and v.is_integer(),
}
_ALLOWED = {
    'type', 'properties', 'required', 'additionalProperties', 'enum', 'items',
    'minItems', 'maxItems', 'maxLength', 'pattern', 'minimum', 'exclusiveMinimum', 'maximum',
}

def valid(schema, value):
    types = schema['type']
    if isinstance(types, str):
        types = (types,)
    if not any(_TYPES[kind](value) for kind in types):
        return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    if type(value) is dict:
        props = schema['properties']
        return (all(k in value for k in schema['required'])
                and all(k in props and valid(props[k], item) for k, item in value.items()))
    if type(value) is list:
        return (schema.get('minItems', 0) <= len(value) <= schema['maxItems']
                and all(valid(schema['items'], item) for item in value))
    if type(value) is str:
        return (len(value) <= schema.get('maxLength', len(value))
                and ('pattern' not in schema or re.search(schema['pattern'], value) is not None))
    if type(value) in (int, float):
        return (('minimum' not in schema or value >= schema['minimum'])
                and ('exclusiveMinimum' not in schema or value > schema['exclusiveMinimum'])
                and ('maximum' not in schema or value <= schema['maximum']))
    return True

class Draft202012Validator:
    def __init__(self, schema):
        self.schema = schema

    def is_valid(self, value):
        return valid(self.schema, value)

    @classmethod
    def check_schema(cls, schema):
        types = schema['type']
        if isinstance(types, str):
            types = (types,)
        if set(schema) - _ALLOWED or set(types) - _TYPES.keys():
            raise ValueError('unsupported_schema')
        if 'object' in types:
            if schema.get('additionalProperties') is not False or set(schema['required']) - schema['properties'].keys():
                raise ValueError('unsupported_object_schema')
            for child in schema['properties'].values():
                cls.check_schema(child)
        if 'array' in types:
            if 'maxItems' not in schema:
                raise ValueError('unsupported_array_schema')
            cls.check_schema(schema['items'])
