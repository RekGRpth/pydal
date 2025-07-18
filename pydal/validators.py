#!/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=line-too-long,invalid-name

"""
| This file is part of the web2py Web Framework
| Copyrighted by Massimo Di Pierro <mdipierro@cs.depaul.edu>
| License: BSD
| Thanks to ga2arch for help with IS_IN_DB and IS_NOT_IN_DB on GAE

Validators
-----------
"""

import binascii
import datetime
import decimal
import encodings.idna
import hashlib
import hmac
import json
import math
import os
import re
import struct
import time
import unicodedata
import uuid
from functools import reduce

from ._compat import (
    PY2,
    StringIO,
    basestring,
    integer_types,
    ipaddress,
    string_types,
    to_bytes,
    to_native,
    to_unicode,
    unichr,
    unicodeT,
    urllib_unquote,
    urlparse,
)
from .objects import Field, FieldMethod, FieldVirtual, Table

JSONErrors = (NameError, TypeError, ValueError, AttributeError, KeyError)

__all__ = [
    "ANY_OF",
    "CLEANUP",
    "CRYPT",
    "IS_ALPHANUMERIC",
    "IS_DATE_IN_RANGE",
    "IS_DATE",
    "IS_DATETIME_IN_RANGE",
    "IS_DATETIME",
    "IS_DECIMAL_IN_RANGE",
    "IS_EMAIL",
    "IS_LIST_OF_EMAILS",
    "IS_EMPTY_OR",
    "IS_EXPR",
    "IS_FILE",
    "IS_FLOAT_IN_RANGE",
    "IS_IMAGE",
    "IS_IN_DB",
    "IS_IN_SET",
    "IS_INT_IN_RANGE",
    "IS_IPV4",
    "IS_IPV6",
    "IS_IPADDRESS",
    "IS_LENGTH",
    "IS_LIST_OF",
    "IS_LIST_OF_STRINGS",
    "IS_LIST_OF_INTS",
    "IS_LOWER",
    "IS_MATCH",
    "IS_EQUAL_TO",
    "IS_NOT_EMPTY",
    "IS_NOT_IN_DB",
    "IS_NULL_OR",
    "IS_SAFE",
    "IS_SLUG",
    "IS_STRONG",
    "IS_TIME",
    "IS_UPLOAD_FILENAME",
    "IS_UPPER",
    "IS_URL",
    "IS_JSON",
]


def options_sorter(x, y):
    return (str(x[1]).upper() > str(y[1]).upper() and 1) or -1


def translate(text):
    return Validator.translator(text)


def quote_token(token):
    token = str(token)
    if any(c in token for c in r',; "'):
        token = token.replace('"', '\\"')
        return f'"{token}"'
    return token


def parse_tokens(line):
    tokens = []
    token = ""
    in_quotes = False
    escaped = False
    i = 0
    while i < len(line):
        c = line[i]
        if in_quotes:
            if escaped:
                token += c
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_quotes = False
            else:
                token += c
        else:
            if c in ",; ":
                token = token.strip()
                if token:
                    tokens.append(token)
                token = ""
            elif c == '"':
                in_quotes = True
            else:
                token += c
        i += 1
    token = token.strip()
    if token:
        tokens.append(token)
    return tokens


class ValidationError(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


class Validator(object):
    """
    Root for all validators, mainly for documentation purposes.

    Validators are classes used to validate input fields (including forms
    generated from database tables).

    Here is an example of using a validator with a FORM::

        INPUT(_name='a', requires=IS_INT_IN_RANGE(0, 10))

    Here is an example of how to require a validator for a table field::

        db.define_table('person', Field('name'))
        db.person.name.requires=IS_NOT_EMPTY()

    Validators are always assigned using the requires attribute of a field. A
    field can have a single validator or multiple validators. Multiple
    validators are made part of a list::

        db.person.name.requires=[IS_NOT_EMPTY(), IS_NOT_IN_DB(db, 'person.id')]

    Validators are called by the function accepts on a FORM or other HTML
    helper object that contains a form. They are always called in the order in
    which they are listed.

    Built-in validators have constructors that take the optional argument error
    message which allows you to change the default error message.
    Here is an example of a validator on a database table::

        db.person.name.requires=IS_NOT_EMPTY(error_message=T('Fill this'))

    where we have used the translation operator T to allow for
    internationalization.

    Notice that default error messages are not translated.
    """

    translator = staticmethod(lambda text: text)

    def formatter(self, value):
        """
        For some validators returns a formatted version (matching the validator)
        of value. Otherwise just returns the value.
        """
        return value

    @staticmethod
    def validate(value, record_id=None):
        return value

    def __call__(self, value, record_id=None):
        try:
            return self.validate(value, record_id), None
        except ValidationError as e:
            return value, e.message


def validator_caller(func, value, record_id=None):
    validate = getattr(func, "validate", None)
    if validate and validate is not Validator.validate:
        return validate(value, record_id)
    value, error = func(value)
    if error is not None:
        raise ValidationError(error)
    return value


class IS_MATCH(Validator):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='name', requires=IS_MATCH('.+'))

    The argument of IS_MATCH is a regular expression::

        >>> IS_MATCH('.+')('hello')
        ('hello', None)

        >>> IS_MATCH('hell')('hello')
        ('hello', None)

        >>> IS_MATCH('hell.*', strict=False)('hello')
        ('hello', None)

        >>> IS_MATCH('hello')('shello')
        ('shello', 'invalid expression')

        >>> IS_MATCH('hello', search=True)('shello')
        ('shello', None)

        >>> IS_MATCH('hello', search=True, strict=False)('shellox')
        ('shellox', None)

        >>> IS_MATCH('.*hello.*', search=True, strict=False)('shellox')
        ('shellox', None)

        >>> IS_MATCH('.+')('')
        ('', 'invalid expression')

    """

    def __init__(
        self,
        expression,
        error_message="Invalid expression",
        strict=False,
        search=False,
        extract=False,
        is_unicode=False,
    ):
        if strict or not search:
            if not expression.startswith("^"):
                expression = "^(%s)" % expression
        if strict:
            if not expression.endswith("$"):
                expression = "(%s)$" % expression
        if is_unicode:
            if not isinstance(expression, unicodeT):
                expression = expression.decode("utf8")
            self.regex = re.compile(expression, re.UNICODE)
        else:
            self.regex = re.compile(expression)
        self.error_message = error_message
        self.extract = extract
        self.is_unicode = is_unicode or not PY2

    def validate(self, value, record_id=None):
        if not PY2:  # PY3 convert bytes to unicode
            value = to_unicode(value)

        if self.is_unicode or not PY2:
            if not isinstance(value, unicodeT):
                match = self.regex.search(str(value).decode("utf8"))
            else:
                match = self.regex.search(value)
        else:
            if not isinstance(value, unicodeT):
                match = self.regex.search(str(value))
            else:
                match = self.regex.search(value.encode("utf8"))
        if match is not None:
            return self.extract and match.group() or value
        raise ValidationError(self.translator(self.error_message))


class IS_EQUAL_TO(Validator):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='password')
            INPUT(_type='text', _name='password2',
                  requires=IS_EQUAL_TO(request.vars.password))

    The argument of IS_EQUAL_TO is a string::

        >>> IS_EQUAL_TO('aaa')('aaa')
        ('aaa', None)

        >>> IS_EQUAL_TO('aaa')('aab')
        ('aab', 'no match')

    """

    def __init__(self, expression, error_message="No match"):
        self.expression = expression
        self.error_message = error_message

    def validate(self, value, record_id=None):
        if value != self.expression:
            raise ValidationError(self.translator(self.error_message))
        return value


class IS_EXPR(Validator):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='name',
                requires=IS_EXPR('5 < int(value) < 10'))

    The argument of IS_EXPR must be python condition::

        >>> IS_EXPR('int(value) < 2')('1')
        ('1', None)

        >>> IS_EXPR('int(value) < 2')('2')
        ('2', 'invalid expression')

    """

    def __init__(
        self, expression, error_message="Invalid expression", environment=None
    ):
        self.expression = expression
        self.error_message = error_message
        self.environment = environment or {}

    def validate(self, value, record_id=None):
        if callable(self.expression):
            message = self.expression(value)
            if message:
                raise ValidationError(message)
            return value
        # for backward compatibility
        self.environment.update(value=value)
        exec("__ret__=" + self.expression, self.environment)
        if self.environment["__ret__"]:
            return value
        raise ValidationError(self.translator(self.error_message))


class IS_LENGTH(Validator):
    """
    Checks if length of field's value fits between given boundaries. Works
    for both text and file inputs.

    Args:
        maxsize: maximum allowed length / size
        minsize: minimum allowed length / size

    Examples:
        Check if text string is shorter than 33 characters::

            INPUT(_type='text', _name='name', requires=IS_LENGTH(32))

        Check if password string is longer than 5 characters::

            INPUT(_type='password', _name='name', requires=IS_LENGTH(minsize=6))

        Check if uploaded file has size between 1KB and 1MB::

            INPUT(_type='file', _name='name', requires=IS_LENGTH(1048576, 1024))

        Other examples::

            >>> IS_LENGTH()('')
            ('', None)
            >>> IS_LENGTH()('1234567890')
            ('1234567890', None)
            >>> IS_LENGTH(maxsize=5, minsize=0)('1234567890')  # too long
            ('1234567890', 'enter from 0 to 5 characters')
            >>> IS_LENGTH(maxsize=50, minsize=20)('1234567890')  # too short
            ('1234567890', 'enter from 20 to 50 characters')
    """

    def __init__(
        self,
        maxsize=255,
        minsize=0,
        error_message="Enter from %(min)g to %(max)g characters",
    ):
        self.maxsize = maxsize
        self.minsize = minsize
        self.error_message = error_message

    def validate(self, value, record_id=None):
        if value is None:
            length = 0
        elif isinstance(value, str):
            try:
                length = len(to_unicode(value))
            except:
                length = len(value)
        elif isinstance(value, unicodeT):
            length = len(value)
            value = value.encode("utf8")
        elif isinstance(value, (bytes, bytearray, tuple, list)):
            length = len(value)
        elif hasattr(value, "file") and hasattr(value, "filename"):
            if value.file:
                value.file.seek(0, os.SEEK_END)
                length = value.file.tell()
                value.file.seek(0, os.SEEK_SET)
            elif hasattr(value, "value"):
                val = value.value
                if val:
                    length = len(val)
                else:
                    length = 0
        else:
            value = str(value)
            length = len(str(value))
        if self.minsize <= length <= self.maxsize:
            return value
        raise ValidationError(
            self.translator(self.error_message)
            % dict(min=self.minsize, max=self.maxsize)
        )


class IS_JSON(Validator):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='name',
                requires=IS_JSON(error_message="This is not a valid json input")

            >>> IS_JSON()('{"a": 100}')
            ({u'a': 100}, None)

            >>> IS_JSON()('spam1234')
            ('spam1234', 'invalid json')
    """

    def __init__(self, error_message="Invalid json", native_json=False):
        self.native_json = native_json
        self.error_message = error_message

    def validate(self, value, record_id=None):
        if value is None or value == "null":
            return None
        if isinstance(value, (str, bytes)):
            try:
                if self.native_json:
                    json.loads(value)  # raises error in case of malformed json
                    return value  # the serialized value is not passed
                else:
                    return json.loads(value)
            except JSONErrors:
                raise ValidationError(self.translator(self.error_message))
        else:
            return value

    def formatter(self, value):
        if value is None:
            return "null"
        if self.native_json:
            return value
        else:
            return json.dumps(value, ensure_ascii=False)


class IS_IN_SET(Validator):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='name',
                  requires=IS_IN_SET(['max', 'john'],zero=''))

    The argument of IS_IN_SET must be a list or set::

        >>> IS_IN_SET(['max', 'john'])('max')
        ('max', None)
        >>> IS_IN_SET(['max', 'john'])('massimo')
        ('massimo', 'value not allowed')
        >>> IS_IN_SET(['max', 'john'], multiple=True)(('max', 'john'))
        (('max', 'john'), None)
        >>> IS_IN_SET(['max', 'john'], multiple=True)(('bill', 'john'))
        (('bill', 'john'), 'value not allowed')
        >>> IS_IN_SET(('id1','id2'), ['first label','second label'])('id1') # Traditional way
        ('id1', None)
        >>> IS_IN_SET({'id1':'first label', 'id2':'second label'})('id1')
        ('id1', None)
        >>> import itertools
        >>> IS_IN_SET(itertools.chain(['1','3','5'],['2','4','6']))('1')
        ('1', None)
        >>> IS_IN_SET([('id1','first label'), ('id2','second label')])('id1') # Redundant way
        ('id1', None)

    """

    def __init__(
        self,
        theset,
        labels=None,
        error_message="Value not allowed",
        multiple=False,
        zero="",
        sort=False,
    ):
        self.theset = theset
        self.labels = labels
        self.error_message = error_message
        self.multiple = multiple
        self.zero = zero
        self.sort = sort

    def options(self, zero=True):
        # could be a lasy set
        iset = self.theset() if callable(self.theset) else self.theset
        # this could be an interator
        if isinstance(iset, dict):
            theset = map(str, iset)
            labels = list(iset.values())
        else:
            # in case theset is an iterator
            iset = list(iset)
            if iset and isinstance(iset[0], (list, tuple)) and len(iset[0]) == 2:
                labels = [str(label) for _, label in iset]
                theset = [str(key) for key, _ in iset]
            else:
                theset = map(str, iset)
                labels = self.labels
        if not labels:
            items = [(k, k) for (i, k) in enumerate(theset)]
        else:
            items = [(k, list(labels)[i]) for (i, k) in enumerate(theset)]
        if self.sort:
            items.sort(key=lambda o: str(o[1]).upper())
        if zero and self.zero is not None and not self.multiple:
            items.insert(0, ("", self.zero))
        return items

    def validate(self, value, record_id=None):
        valuemap = dict(self.options(zero=False))
        if self.multiple:
            # if below was values = re.compile("[\w\-:]+").findall(str(value))
            if not value:
                values = []
            elif isinstance(value, (tuple, list)):
                values = value
            else:
                values = [value]
            if isinstance(self.multiple, (tuple, list)):
                if not self.multiple[0] <= len(values) < self.multiple[1]:
                    raise ValidationError(self.translator(self.error_message))
        else:
            values = [value]
        strkeys = map(str, valuemap)
        failures = [x for x in values if not str(x) in strkeys]
        if failures and self.theset:
            raise ValidationError(self.translator(self.error_message))
        return values if self.multiple else value


class IS_IN_DB(Validator):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='name',
                  requires=IS_IN_DB(db, db.mytable.myfield, zero=''))

    used for reference fields, rendered as a dropbox
    """

    REGEX_TABLE_DOT_FIELD = r"^(\w+)\.(\w+)$"
    REGEX_INTERP_CONV_SPECIFIER = r"%\((\w+)\)\d*(?:\.\d+)?[a-zA-Z]"

    def __init__(
        self,
        dbset,
        field,
        label=None,
        error_message="Value not in database",
        orderby=None,
        groupby=None,
        distinct=None,
        cache=None,
        multiple=False,
        zero="",
        sort=False,
        _and=None,
        left=None,
        delimiter=None,
        auto_add=False,
    ):
        if hasattr(dbset, "define_table"):
            self.dbset = dbset()
        else:
            self.dbset = dbset

        table = None
        if isinstance(field, Table):
            table = field
            field = table._id
            fname = str(field)
        if isinstance(field, Field):
            fname = str(field)
        elif isinstance(field, str):
            items = field.split(".")
            if len(items) == 1 or items[1] == "id":
                table = self.dbset._db.get(items[0])
                fname = items[0] + ".id"
            else:
                fname = field
        else:
            raise RuntimeError("IS_IN_DB: a field argument must be specified")
        (ktable, kfield) = fname.split(".")
        if not label:
            # if we have a table and it has a _format, use it
            if table and table._format:
                label = table._format
            # else format using the field value
            else:
                label = "%%(%s)s" % kfield
        if isinstance(label, str):
            m = re.match(self.REGEX_TABLE_DOT_FIELD, label)
            if m:
                label = "%%(%s)s" % m.group(2)
            fieldnames = re.findall(self.REGEX_INTERP_CONV_SPECIFIER, label)
            if kfield not in fieldnames:
                fieldnames.append(kfield)  # kfield must be last
        elif isinstance(label, Field):
            fieldnames = [label.name, kfield]  # kfield must be last
            label = "%%(%s)s" % label.name
        elif callable(label):
            fieldnames = "*"
        else:
            raise NotImplementedError

        self.fieldnames = fieldnames  # fields requires to build the formatting
        self.label = label
        self.ktable = ktable
        self.kfield = kfield
        self.error_message = error_message
        self.theset = None
        self.orderby = orderby
        self.groupby = groupby
        self.distinct = distinct
        self.cache = cache
        self.multiple = multiple
        self.zero = zero
        self.sort = sort
        self._and = _and
        self.left = left
        self.delimiter = delimiter
        self.auto_add = auto_add

    def set_self_id(self, id):
        if self._and:
            self._and.record_id = id

    def build_set(self):
        table = self.dbset.db[self.ktable]
        if self.fieldnames == "*":
            fields = [f for f in table]
        else:
            fields = [table[k] for k in self.fieldnames]
        ignore = (FieldVirtual, FieldMethod)
        fields = [f for f in fields if not isinstance(f, ignore)]
        if self.dbset.db._dbname != "gae":
            orderby = self.orderby or reduce(lambda a, b: a | b, fields)
            groupby = self.groupby
            distinct = self.distinct
            left = self.left
            dd = dict(
                orderby=orderby,
                groupby=groupby,
                distinct=distinct,
                cache=self.cache,
                cacheable=True,
                left=left,
            )
            records = self.dbset(table).select(*fields, **dd)
        else:
            orderby = self.orderby or reduce(
                lambda a, b: a | b, (f for f in fields if not f.name == "id")
            )
            dd = dict(orderby=orderby, cache=self.cache, cacheable=True)
            records = self.dbset(table).select(table.ALL, **dd)
        self.theset = [str(r[self.kfield]) for r in records]
        if isinstance(self.label, str):
            self.labels = [self.label % r for r in records]
        else:
            self.labels = [self.label(r) for r in records]

    def options(self, zero=True):
        self.build_set()
        items = [(k, self.labels[i]) for (i, k) in enumerate(self.theset)]
        if self.sort:
            items.sort(key=lambda o: str(o[1]).upper())
        if zero and self.zero is not None and not self.multiple:
            items.insert(0, ("", self.zero))
        return items

    def maybe_add(self, table, fieldname, value):
        d = {fieldname: value}
        record = table(**d)
        if record:
            return record.id
        else:
            return table.insert(**d)

    def validate(self, value, record_id=None):
        table = self.dbset.db[self.ktable]
        field = table[self.kfield]

        if self.multiple:
            if self._and:
                raise NotImplementedError
            if isinstance(value, list):
                values = value
            elif self.delimiter:
                values = value.split(self.delimiter)  # because of autocomplete
            elif value:
                values = [value]
            else:
                values = []

            if field.type in ("id", "integer"):
                new_values = []
                for value in values:
                    if not (isinstance(value, integer_types) or value.isdigit()):
                        if self.auto_add:
                            value = str(
                                self.maybe_add(table, self.fieldnames[0], value)
                            )
                        else:
                            raise ValidationError(self.translator(self.error_message))
                    new_values.append(value)
                values = new_values

            if (
                isinstance(self.multiple, (tuple, list))
                and not self.multiple[0] <= len(values) < self.multiple[1]
            ):
                raise ValidationError(self.translator(self.error_message))
            if self.theset:
                if not [v for v in values if str(v) not in self.theset]:
                    return values
            else:

                def count(values, s=self.dbset, f=field):
                    return s(f.belongs(list(map(int, values)))).count()

                if self.dbset.db._adapter.dbengine == "firestore":
                    range_ids = range(0, len(values), 30)
                    total = sum(count(values[i : i + 30]) for i in range_ids)
                    if total == len(values):
                        return values
                elif count(values) == len(values):
                    return values
        else:
            if field.type in ("id", "integer"):
                if isinstance(value, integer_types) or (
                    isinstance(value, string_types) and value.isdigit()
                ):
                    value = int(value)
                elif self.auto_add:
                    value = self.maybe_add(table, self.fieldnames[0], value)
                else:
                    raise ValidationError(self.translator(self.error_message))

                try:
                    value = int(value)
                except TypeError:
                    raise ValidationError(self.translator(self.error_message))

            if self.theset:
                if str(value) in self.theset:
                    if self._and:
                        return validator_caller(self._and, value, record_id)
                    return value
            else:
                if self.dbset(field == value).count():
                    if self._and:
                        return validator_caller(self._and, value, record_id)
                    return value
        raise ValidationError(self.translator(self.error_message))


class IS_NOT_IN_DB(Validator):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='name', requires=IS_NOT_IN_DB(db, db.table))

    makes the field unique
    """

    def __init__(
        self,
        dbset,
        field,
        error_message="Value already in database or empty",
        allowed_override=[],
        ignore_common_filters=False,
    ):
        if isinstance(field, Table):
            field = field._id
        self.dbset = dbset
        self.field = field
        self.error_message = error_message
        self.record_id = 0
        self.allowed_override = allowed_override
        self.ignore_common_filters = ignore_common_filters

    def set_self_id(self, id):
        # this is legacy  - web2py uses but nobody else should
        # it is not safe if the object is recycled
        self.record_id = id

    def validate(self, value, record_id=None):
        value = to_native(str(value))
        if not value.strip():
            raise ValidationError(self.translator(self.error_message))
        if value in self.allowed_override:
            return value
        (tablename, fieldname) = str(self.field).split(".")
        if hasattr(self.dbset, "define_table"):
            db = self.dbset
        else:
            db = self.dbset.db
        table = db[tablename]
        field = table[fieldname]
        dbset = self.dbset(
            field == value, ignore_common_filters=self.ignore_common_filters
        )

        # make sure exclude the record_id
        id = record_id or self.record_id
        if isinstance(id, dict):
            id = table(**id)
        record = dbset.select(table._id, limitby=(0, 1)).first()
        if record and record[table._id.name] != id:
            raise ValidationError(self.translator(self.error_message))
        return value


def range_error_message(error_message, what_to_enter, minimum, maximum):
    """build the error message for the number range validators"""
    if error_message is None:
        error_message = "Enter " + what_to_enter
        if minimum is not None and maximum is not None:
            error_message += " between %(min)g and %(max)g"
        elif minimum is not None:
            error_message += " greater than or equal to %(min)g"
        elif maximum is not None:
            error_message += " less than or equal to %(max)g"
    if type(maximum) in integer_types:
        maximum -= 1
    return str(translate(error_message)) % dict(min=minimum, max=maximum)


class IS_INT_IN_RANGE(Validator):
    """
    Determines that the argument is (or can be represented as) an int,
    and that it falls within the specified range. The range is interpreted
    in the Pythonic way, so the test is: min <= value < max.

    The minimum and maximum limits can be None, meaning no lower or upper limit,
    respectively.

    Example:
        Used as::

            INPUT(_type='text', _name='name', requires=IS_INT_IN_RANGE(0, 10))

            >>> IS_INT_IN_RANGE(1,5)('4')
            (4, None)
            >>> IS_INT_IN_RANGE(1,5)(4)
            (4, None)
            >>> IS_INT_IN_RANGE(1,5)(1)
            (1, None)
            >>> IS_INT_IN_RANGE(1,5)(5)
            (5, 'enter an integer between 1 and 4')
            >>> IS_INT_IN_RANGE(1,5)(5)
            (5, 'enter an integer between 1 and 4')
            >>> IS_INT_IN_RANGE(1,5)(3.5)
            (3.5, 'enter an integer between 1 and 4')
            >>> IS_INT_IN_RANGE(None,5)('4')
            (4, None)
            >>> IS_INT_IN_RANGE(None,5)('6')
            ('6', 'enter an integer less than or equal to 4')
            >>> IS_INT_IN_RANGE(1,None)('4')
            (4, None)
            >>> IS_INT_IN_RANGE(1,None)('0')
            ('0', 'enter an integer greater than or equal to 1')
            >>> IS_INT_IN_RANGE()(6)
            (6, None)
            >>> IS_INT_IN_RANGE()('abc')
            ('abc', 'enter an integer')
    """

    REGEX_INT = r"^[+-]?\d+$"

    def __init__(self, minimum=None, maximum=None, error_message=None):
        self.minimum = int(minimum) if minimum is not None else None
        self.maximum = int(maximum) if maximum is not None else None
        self.error_message = error_message

    def validate(self, value, record_id=None):
        if re.match(self.REGEX_INT, str(value)):
            v = int(value)
            if (self.minimum is None or v >= self.minimum) and (
                self.maximum is None or v < self.maximum
            ):
                return v
        raise ValidationError(
            range_error_message(
                self.error_message, "an integer", self.minimum, self.maximum
            )
        )


def str2dec(number):
    s = str(number)
    if "." not in s:
        s += ".00"
    else:
        s += "0" * (2 - len(s.split(".")[1]))
    return s


class IS_FLOAT_IN_RANGE(Validator):
    """
    Determines that the argument is (or can be represented as) a float,
    and that it falls within the specified inclusive range.
    The comparison is made with native arithmetic.

    The minimum and maximum limits can be None, meaning no lower or upper limit,
    respectively.

    Example:
        Used as::

            INPUT(_type='text', _name='name', requires=IS_FLOAT_IN_RANGE(0, 10))

            >>> IS_FLOAT_IN_RANGE(1,5)('4')
            (4.0, None)
            >>> IS_FLOAT_IN_RANGE(1,5)(4)
            (4.0, None)
            >>> IS_FLOAT_IN_RANGE(1,5)(1)
            (1.0, None)
            >>> IS_FLOAT_IN_RANGE(1,5)(5.25)
            (5.25, 'enter a number between 1 and 5')
            >>> IS_FLOAT_IN_RANGE(1,5)(6.0)
            (6.0, 'enter a number between 1 and 5')
            >>> IS_FLOAT_IN_RANGE(1,5)(3.5)
            (3.5, None)
            >>> IS_FLOAT_IN_RANGE(1,None)(3.5)
            (3.5, None)
            >>> IS_FLOAT_IN_RANGE(None,5)(3.5)
            (3.5, None)
            >>> IS_FLOAT_IN_RANGE(1,None)(0.5)
            (0.5, 'enter a number greater than or equal to 1')
            >>> IS_FLOAT_IN_RANGE(None,5)(6.5)
            (6.5, 'enter a number less than or equal to 5')
            >>> IS_FLOAT_IN_RANGE()(6.5)
            (6.5, None)
            >>> IS_FLOAT_IN_RANGE()('abc')
            ('abc', 'enter a number')
    """

    def __init__(self, minimum=None, maximum=None, error_message=None, dot="."):
        self.minimum = float(minimum) if minimum is not None else None
        self.maximum = float(maximum) if maximum is not None else None
        self.dot = str(dot)
        self.error_message = error_message

    def validate(self, value, record_id=None):
        try:
            if self.dot == ".":
                v = float(value)
            else:
                v = float(str(value).replace(self.dot, "."))
            if (self.minimum is None or v >= self.minimum) and (
                self.maximum is None or v <= self.maximum
            ):
                return v
        except (ValueError, TypeError):
            pass
        raise ValidationError(
            range_error_message(
                self.error_message, "a number", self.minimum, self.maximum
            )
        )

    def formatter(self, value):
        if value is None:
            return None
        return str2dec(value).replace(".", self.dot)


class IS_DECIMAL_IN_RANGE(Validator):
    """
    Determines that the argument is (or can be represented as) a Python Decimal,
    and that it falls within the specified inclusive range.
    The comparison is made with Python Decimal arithmetic.

    The minimum and maximum limits can be None, meaning no lower or upper limit,
    respectively.

    Example:
        Used as::

            INPUT(_type='text', _name='name', requires=IS_DECIMAL_IN_RANGE(0, 10))

            >>> IS_DECIMAL_IN_RANGE(1,5)('4')
            (Decimal('4'), None)
            >>> IS_DECIMAL_IN_RANGE(1,5)(4)
            (Decimal('4'), None)
            >>> IS_DECIMAL_IN_RANGE(1,5)(1)
            (Decimal('1'), None)
            >>> IS_DECIMAL_IN_RANGE(1,5)(5.25)
            (5.25, 'enter a number between 1 and 5')
            >>> IS_DECIMAL_IN_RANGE(5.25,6)(5.25)
            (Decimal('5.25'), None)
            >>> IS_DECIMAL_IN_RANGE(5.25,6)('5.25')
            (Decimal('5.25'), None)
            >>> IS_DECIMAL_IN_RANGE(1,5)(6.0)
            (6.0, 'enter a number between 1 and 5')
            >>> IS_DECIMAL_IN_RANGE(1,5)(3.5)
            (Decimal('3.5'), None)
            >>> IS_DECIMAL_IN_RANGE(1.5,5.5)(3.5)
            (Decimal('3.5'), None)
            >>> IS_DECIMAL_IN_RANGE(1.5,5.5)(6.5)
            (6.5, 'enter a number between 1.5 and 5.5')
            >>> IS_DECIMAL_IN_RANGE(1.5,None)(6.5)
            (Decimal('6.5'), None)
            >>> IS_DECIMAL_IN_RANGE(1.5,None)(0.5)
            (0.5, 'enter a number greater than or equal to 1.5')
            >>> IS_DECIMAL_IN_RANGE(None,5.5)(4.5)
            (Decimal('4.5'), None)
            >>> IS_DECIMAL_IN_RANGE(None,5.5)(6.5)
            (6.5, 'enter a number less than or equal to 5.5')
            >>> IS_DECIMAL_IN_RANGE()(6.5)
            (Decimal('6.5'), None)
            >>> IS_DECIMAL_IN_RANGE(0,99)(123.123)
            (123.123, 'enter a number between 0 and 99')
            >>> IS_DECIMAL_IN_RANGE(0,99)('123.123')
            ('123.123', 'enter a number between 0 and 99')
            >>> IS_DECIMAL_IN_RANGE(0,99)('12.34')
            (Decimal('12.34'), None)
            >>> IS_DECIMAL_IN_RANGE()('abc')
            ('abc', 'enter a number')
    """

    def __init__(self, minimum=None, maximum=None, error_message=None, dot="."):
        self.minimum = decimal.Decimal(str(minimum)) if minimum is not None else None
        self.maximum = decimal.Decimal(str(maximum)) if maximum is not None else None
        self.dot = str(dot)
        self.error_message = error_message

    def validate(self, value, record_id=None):
        try:
            if not isinstance(value, decimal.Decimal):
                value = decimal.Decimal(str(value).replace(self.dot, "."))
            if (self.minimum is None or value >= self.minimum) and (
                self.maximum is None or value <= self.maximum
            ):
                return value
        except (ValueError, TypeError, decimal.InvalidOperation):
            pass
        raise ValidationError(
            range_error_message(
                self.error_message, "a number", self.minimum, self.maximum
            )
        )

    def formatter(self, value):
        if value is None:
            return None
        return str2dec(value).replace(".", self.dot)


def is_empty(value, empty_regex=None):
    _value = value
    """test empty field"""
    if isinstance(value, (str, unicodeT)):
        value = value.strip()
        if empty_regex is not None and empty_regex.match(value):
            value = ""
    if value is None or value == "" or value == b"" or value == []:
        return (_value, True)
    return (_value, False)


class IS_NOT_EMPTY(Validator):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='name', requires=IS_NOT_EMPTY())

            >>> IS_NOT_EMPTY()(1)
            (1, None)
            >>> IS_NOT_EMPTY()(0)
            (0, None)
            >>> IS_NOT_EMPTY()('x')
            ('x', None)
            >>> IS_NOT_EMPTY()(' x ')
            ('x', None)
            >>> IS_NOT_EMPTY()(None)
            (None, 'enter a value')
            >>> IS_NOT_EMPTY()('')
            ('', 'enter a value')
            >>> IS_NOT_EMPTY()('  ')
            ('', 'enter a value')
            >>> IS_NOT_EMPTY()(' \\n\\t')
            ('', 'enter a value')
            >>> IS_NOT_EMPTY()([])
            ([], 'enter a value')
            >>> IS_NOT_EMPTY(empty_regex='def')('def')
            ('', 'enter a value')
            >>> IS_NOT_EMPTY(empty_regex='de[fg]')('deg')
            ('', 'enter a value')
            >>> IS_NOT_EMPTY(empty_regex='def')('abc')
            ('abc', None)
    """

    def __init__(self, error_message="Enter a value", empty_regex=None):
        self.error_message = error_message
        if empty_regex is not None:
            self.empty_regex = re.compile(empty_regex)
        else:
            self.empty_regex = None

    def validate(self, value, record_id=None):
        value, empty = is_empty(value, empty_regex=self.empty_regex)
        if empty:
            raise ValidationError(self.translator(self.error_message))
        return value


class IS_SAFE(Validator):
    """
    Example:
        Used as::

            Field("html", 'text', requires=IS_SAFE())

            >>> IS_SAFE()("<div></div>")
            ("<div></div>, None)
            >>> from py4web import XML
            >>> sanitizer = lambda text: XML(text, sanitize=True)
            >>> IS_SAFE(sanitizer, mode="error")("<script></script>")
            ("<script></script>", "Unsafe Content")
            >>> IS_SAFE(sanitizer, node="sanitize")("<script></script>")
            ("", None)
    """

    def __init__(self, sanitizer=None, error_message="Unsafe Content", mode="error"):
        self.sanitizer = sanitizer or IS_SAFE.default_sanitizer
        self.error_message = error_message
        assert mode in ("error", "sanitize")
        self.mode = mode

    def validate(self, value, record_id=None):
        sanitized_value = self.sanitizer(value)
        if sanitized_value != value and self.mode == "error":
            raise ValidationError(self.translator(self.error_message))
        return sanitized_value

    default_regex = re.compile(
        r"(<\s*/?(script|embed|object|iframe|textarea|input|button).*>)|(<[^>]+ on\w+[^>]+>)",
        re.IGNORECASE | re.DOTALL,
    )

    @staticmethod
    def default_sanitizer(text):
        return IS_SAFE.default_regex.sub("", text)


class IS_ALPHANUMERIC(IS_MATCH):
    """
    Example:
        Used as::

            INPUT(_type='text', _name='name', requires=IS_ALPHANUMERIC())

            >>> IS_ALPHANUMERIC()('1')
            ('1', None)
            >>> IS_ALPHANUMERIC()('')
            ('', None)
            >>> IS_ALPHANUMERIC()('A_a')
            ('A_a', None)
            >>> IS_ALPHANUMERIC()('!')
            ('!', 'enter only letters, numbers, and underscore')
    """

    def __init__(self, error_message="Enter only letters, numbers, and underscore"):
        IS_MATCH.__init__(self, r"^[\w]*$", error_message)


class IS_EMAIL(Validator):
    """
    Checks if field's value is a valid email address. Can be set to disallow
    or force addresses from certain domain(s).

    Email regex adapted from
    http://haacked.com/archive/2007/08/21/i-knew-how-to-validate-an-email-address-until-i.aspx,
    generally following the RFCs, except that we disallow quoted strings
    and permit underscores and leading numerics in subdomain labels

    Args:
        banned: regex text for disallowed address domains
        forced: regex text for required address domains

    Both arguments can also be custom objects with a match(value) method.

    Example:
        Check for valid email address::

            INPUT(_type='text', _name='name',
                requires=IS_EMAIL())

        Check for valid email address that can't be from a .com domain::

            INPUT(_type='text', _name='name',
                requires=IS_EMAIL(banned='^.*\\.com(|\\..*)$'))

        Check for valid email address that must be from a .edu domain::

            INPUT(_type='text', _name='name',
                requires=IS_EMAIL(forced='^.*\\.edu(|\\..*)$'))

            >>> IS_EMAIL()('a@b.com')
            ('a@b.com', None)
            >>> IS_EMAIL()('abc@def.com')
            ('abc@def.com', None)
            >>> IS_EMAIL()('abc@3def.com')
            ('abc@3def.com', None)
            >>> IS_EMAIL()('abc@def.us')
            ('abc@def.us', None)
            >>> IS_EMAIL()('abc@d_-f.us')
            ('abc@d_-f.us', None)
            >>> IS_EMAIL()('@def.com')           # missing name
            ('@def.com', 'enter a valid email address')
            >>> IS_EMAIL()('"abc@def".com')      # quoted name
            ('"abc@def".com', 'enter a valid email address')
            >>> IS_EMAIL()('abc+def.com')        # no @
            ('abc+def.com', 'enter a valid email address')
            >>> IS_EMAIL()('abc@def.x')          # one-char TLD
            ('abc@def.x', 'enter a valid email address')
            >>> IS_EMAIL()('abc@def.12')         # numeric TLD
            ('abc@def.12', 'enter a valid email address')
            >>> IS_EMAIL()('abc@def..com')       # double-dot in domain
            ('abc@def..com', 'enter a valid email address')
            >>> IS_EMAIL()('abc@.def.com')       # dot starts domain
            ('abc@.def.com', 'enter a valid email address')
            >>> IS_EMAIL()('abc@def.c_m')        # underscore in TLD
            ('abc@def.c_m', 'enter a valid email address')
            >>> IS_EMAIL()('NotAnEmail')         # missing @
            ('NotAnEmail', 'enter a valid email address')
            >>> IS_EMAIL()('abc@NotAnEmail')     # missing TLD
            ('abc@NotAnEmail', 'enter a valid email address')
            >>> IS_EMAIL()('customer/department@example.com')
            ('customer/department@example.com', None)
            >>> IS_EMAIL()('$A12345@example.com')
            ('$A12345@example.com', None)
            >>> IS_EMAIL()('!def!xyz%abc@example.com')
            ('!def!xyz%abc@example.com', None)
            >>> IS_EMAIL()('_Yosemite.Sam@example.com')
            ('_Yosemite.Sam@example.com', None)
            >>> IS_EMAIL()('~@example.com')
            ('~@example.com', None)
            >>> IS_EMAIL()('.wooly@example.com')       # dot starts name
            ('.wooly@example.com', 'enter a valid email address')
            >>> IS_EMAIL()('wo..oly@example.com')      # adjacent dots in name
            ('wo..oly@example.com', 'enter a valid email address')
            >>> IS_EMAIL()('pootietang.@example.com')  # dot ends name
            ('pootietang.@example.com', 'enter a valid email address')
            >>> IS_EMAIL()('.@example.com')            # name is bare dot
            ('.@example.com', 'enter a valid email address')
            >>> IS_EMAIL()('Ima.Fool@example.com')
            ('Ima.Fool@example.com', None)
            >>> IS_EMAIL()('Ima Fool@example.com')     # space in name
            ('Ima Fool@example.com', 'enter a valid email address')
            >>> IS_EMAIL()('localguy@localhost')       # localhost as domain
            ('localguy@localhost', None)

    """

    # NOTE: use these with flags = re.VERBOSE | re.IGNORECASE
    REGEX_BODY = r"""
        ^(?!\.)                           # name may not begin with a dot
        (
          [-a-z0-9!\#$%&'*+/=?^_`{|}~]    # all legal characters except dot
          |
          (?<!\.)\.                       # single dots only
        )+
        (?<!\.)$                          # name may not end with a dot
    """
    REGEX_DOMAIN = r"""
        (
          localhost
          |
          (
            [a-z0-9]      # [sub]domain begins with alphanumeric
            (
              [-\w]*      # alphanumeric, underscore, dot, hyphen
              [a-z0-9]    # ending alphanumeric
            )?
          \.              # ending dot
          )+
          [a-z]{2,}       # TLD alpha-only
       )$
    """
    # regex_proposed_but_failed = re.compile(r'^([\w\!\#$\%\&\'\*\+\-\/\=\?\^\`{\|\}\~]+\.)*[\w\!\#$\%\&\'\*\+\-\/\=\?\^\`{\|\}\~]+@((((([a-z0-9]{1}[a-z0-9\-]{0,62}[a-z0-9]{1})|[a-z])\.)+[a-z]{2,6})|(\d{1,3}\.){3}\d{1,3}(\:\d{1,5})?)$', re.VERBOSE | re.IGNORECASE)

    def __init__(
        self, banned=None, forced=None, error_message="Enter a valid email address"
    ):
        if isinstance(banned, str):
            banned = re.compile(banned)
        if isinstance(forced, str):
            forced = re.compile(forced)
        self.banned = banned
        self.forced = forced
        self.error_message = error_message

    def validate(self, value, record_id=None):
        if (
            not (isinstance(value, (basestring, unicodeT)))
            or not value
            or "@" not in value
        ):
            raise ValidationError(self.translator(self.error_message))

        body, domain = value.rsplit("@", 1)

        try:
            regex_flags = re.VERBOSE | re.IGNORECASE
            match_body = re.match(self.REGEX_BODY, body, regex_flags)
            match_domain = re.match(self.REGEX_DOMAIN, domain, regex_flags)

            if not match_domain:
                # check for Internationalized Domain Names
                # see https://docs.python.org/2/library/codecs.html#module-encodings.idna
                domain_encoded = to_unicode(domain).encode("idna").decode("ascii")
                match_domain = re.match(self.REGEX_DOMAIN, domain_encoded, regex_flags)

            match = (match_body is not None) and (match_domain is not None)
        except (TypeError, UnicodeError):
            # Value may not be a string where we can look for matches.
            # Example: we're calling ANY_OF formatter and IS_EMAIL is asked to validate a date.
            match = None
        if match:
            if (not self.banned or not self.banned.match(domain)) and (
                not self.forced or self.forced.match(domain)
            ):
                return value
        raise ValidationError(self.translator(self.error_message))


class IS_LIST_OF_STRINGS(Validator):
    """
    validates a list of comma or semicolon separated strings, quoted or not quoted, or json
    hello, world
    hello; world
    hello, "world"
    hello, "hello world"
    ["hello", "hello world"]
    """

    def __init__(self, error_message="Enter a list of strings"):
        self.error_message = error_message

    def validate(self, value, record_id=None):
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        value = str(value)
        if value[:1] + value[-1:] == "[]":
            try:
                values = json.loads(value)
            except Exception:
                raise ValidationError(self.translator(self.error_message))
            return [str(item) for item in values]
        values = parse_tokens(value)
        return values

    def formatter(self, value):
        if not value:
            return ""
        if isinstance(value, list):
            return ", ".join(map(quote_token, value))
        return str(value)


class IS_LIST_OF_INTS(IS_LIST_OF_STRINGS):
    """
    validates a list of comma or semicolon integers or json
    1
    1, 2
    1; 2
    1, "2"
    [1, 2]
    """

    def __init__(self, error_message="Enter a list of integers"):
        self.error_message = error_message

    def validate(self, value, record_id=None):
        values = IS_LIST_OF_STRINGS.validate(self, value)
        try:
            return [int(item) for item in values]
        except ValueError as err:
            raise ValidationError(self.translator(self.error_message))


class IS_LIST_OF_EMAILS(IS_LIST_OF_STRINGS):
    """
    Example:
        Used as::

        Field('emails', 'list:string',
              widget=SQLFORM.widgets.text.widget,
              requires=IS_LIST_OF_EMAILS(),
              represent=lambda v, r: \
                XML(', '.join([A(x, _href='mailto:'+x).xml() for x in (v or [])]))
             )
    """

    def __init__(self, error_message="Invalid emails: %s"):
        self.error_message = error_message

    def validate(self, value, record_id=None):
        emails = IS_LIST_OF_STRINGS.validate(self, value)
        bad_emails = []
        check_email = IS_EMAIL()
        for email in emails:
            error = check_email(email)[1]
            if error and email not in bad_emails:
                bad_emails.append(email)
        if bad_emails:
            raise ValidationError(
                self.translator(self.error_message) % ", ".join(bad_emails)
            )
        return emails


# URL scheme source:
# <http://en.wikipedia.org/wiki/URI_scheme> obtained on 2008-Nov-10

official_url_schemes = [
    "aaa",
    "aaas",
    "acap",
    "cap",
    "cid",
    "crid",
    "data",
    "dav",
    "dict",
    "dns",
    "fax",
    "file",
    "ftp",
    "go",
    "gopher",
    "h323",
    "http",
    "https",
    "icap",
    "im",
    "imap",
    "info",
    "ipp",
    "iris",
    "iris.beep",
    "iris.xpc",
    "iris.xpcs",
    "iris.lws",
    "ldap",
    "mailto",
    "mid",
    "modem",
    "msrp",
    "msrps",
    "mtqp",
    "mupdate",
    "news",
    "nfs",
    "nntp",
    "opaquelocktoken",
    "pop",
    "pres",
    "prospero",
    "rtsp",
    "service",
    "shttp",
    "sip",
    "sips",
    "snmp",
    "soap.beep",
    "soap.beeps",
    "tag",
    "tel",
    "telnet",
    "tftp",
    "thismessage",
    "tip",
    "tv",
    "urn",
    "vemmi",
    "wais",
    "xmlrpc.beep",
    "xmlrpc.beep",
    "xmpp",
    "z39.50r",
    "z39.50s",
]
unofficial_url_schemes = [
    "about",
    "adiumxtra",
    "aim",
    "afp",
    "aw",
    "callto",
    "chrome",
    "cvs",
    "ed2k",
    "feed",
    "fish",
    "gg",
    "gizmoproject",
    "iax2",
    "irc",
    "ircs",
    "itms",
    "jar",
    "javascript",
    "keyparc",
    "lastfm",
    "ldaps",
    "magnet",
    "mms",
    "msnim",
    "mvn",
    "notes",
    "nsfw",
    "psyc",
    "paparazzi:http",
    "rmi",
    "rsync",
    "secondlife",
    "sgn",
    "skype",
    "ssh",
    "sftp",
    "smb",
    "sms",
    "soldat",
    "steam",
    "svn",
    "teamspeak",
    "unreal",
    "ut2004",
    "ventrilo",
    "view-source",
    "webcal",
    "wyciwyg",
    "xfire",
    "xri",
    "ymsgr",
]
all_url_schemes = [None] + official_url_schemes + unofficial_url_schemes
http_schemes = [None, "http", "https"]

# Defined in RFC 3490, Section 3.1, Requirement #1
# Use this regex to split the authority component of a unicode URL into
# its component labels
REGEX_AUTHORITY_SPLITTER = "[\u002e\u3002\uff0e\uff61]"


def escape_unicode(string):
    """
    Converts a unicode string into US-ASCII, using a simple conversion scheme.
    Each unicode character that does not have a US-ASCII equivalent is
    converted into a URL escaped form based on its hexadecimal value.
    For example, the unicode character '\\u4e86' will become the string '%4e%86'

    Args:
        string: unicode string, the unicode string to convert into an
            escaped US-ASCII form

    Returns:
        string: the US-ASCII escaped form of the inputted string

    @author: Jonathan Benn
    """
    returnValue = StringIO()

    for character in string:
        code = ord(character)
        if code > 0x7F:
            hexCode = hex(code)
            returnValue.write("%" + hexCode[2:4] + "%" + hexCode[4:6])
        else:
            returnValue.write(character)

    return returnValue.getvalue()


def unicode_to_ascii_authority(authority):
    """
    Follows the steps in RFC 3490, Section 4 to convert a unicode authority
    string into its ASCII equivalent.
    For example, u'www.Alliancefran\\xe7aise.nu' will be converted into
    'www.xn--alliancefranaise-npb.nu'

    Args:
        authority: unicode string, the URL authority component to convert,
            e.g. u'www.Alliancefran\\xe7aise.nu'

    Returns:
        string: the US-ASCII character equivalent to the inputted authority,
             e.g. 'www.xn--alliancefranaise-npb.nu'

    Raises:
        Exception: if the function is not able to convert the inputted
            authority

    @author: Jonathan Benn
    """
    # RFC 3490, Section 4, Step 1
    # The encodings.idna Python module assumes that AllowUnassigned == True

    # RFC 3490, Section 4, Step 2
    labels = re.split(REGEX_AUTHORITY_SPLITTER, authority)

    # RFC 3490, Section 4, Step 3
    # The encodings.idna Python module assumes that UseSTD3ASCIIRules == False

    # RFC 3490, Section 4, Step 4
    # We use the ToASCII operation because we are about to put the authority
    # into an IDN-unaware slot
    asciiLabels = []
    for label in labels:
        if label:
            asciiLabels.append(to_native(encodings.idna.ToASCII(label)))
        else:
            # encodings.idna.ToASCII does not accept an empty string, but
            # it is necessary for us to allow for empty labels so that we
            # don't modify the URL
            asciiLabels.append("")
    # RFC 3490, Section 4, Step 5
    return str(reduce(lambda x, y: x + unichr(0x002E) + y, asciiLabels))


def unicode_to_ascii_url(url, prepend_scheme):
    """
    Converts the inputted unicode url into a US-ASCII equivalent. This function
    goes a little beyond RFC 3490, which is limited in scope to the domain name
    (authority) only. Here, the functionality is expanded to what was observed
    on Wikipedia on 2009-Jan-22:

       Component    Can Use Unicode?
       ---------    ----------------
       scheme       No
       authority    Yes
       path         Yes
       query        Yes
       fragment     No

    The authority component gets converted to punycode, but occurrences of
    unicode in other components get converted into a pair of URI escapes (we
    assume 4-byte unicode). E.g. the unicode character U+4E2D will be
    converted into '%4E%2D'. Testing with Firefox v3.0.5 has shown that it can
    understand this kind of URI encoding.

    Args:
        url: unicode string, the URL to convert from unicode into US-ASCII
        prepend_scheme: string, a protocol scheme to prepend to the URL if
            we're having trouble parsing it.
            e.g. "http". Input None to disable this functionality

    Returns:
        string: a US-ASCII equivalent of the inputted url

    @author: Jonathan Benn
    """
    # convert the authority component of the URL into an ASCII punycode string,
    # but encode the rest using the regular URI character encoding
    components = urlparse.urlparse(url)
    prepended = False
    # If no authority was found
    if not components.netloc:
        # Try appending a scheme to see if that fixes the problem
        scheme_to_prepend = prepend_scheme or "http"
        components = urlparse.urlparse(to_unicode(scheme_to_prepend) + "://" + url)
        prepended = True

    # if we still can't find the authority
    if not components.netloc:
        # And it's not because the url is a relative url
        if not url.startswith("/"):
            raise Exception(
                "No authority component found, "
                + "could not decode unicode to US-ASCII"
            )

    # We're here if we found an authority, let's rebuild the URL
    scheme = components.scheme
    authority = components.netloc
    path = components.path
    query = components.query
    fragment = components.fragment

    if prepended:
        scheme = ""

    unparsed = urlparse.urlunparse(
        (
            scheme,
            unicode_to_ascii_authority(authority),
            escape_unicode(path),
            "",
            escape_unicode(query),
            str(fragment),
        )
    )
    if unparsed.startswith("//"):
        unparsed = unparsed[2:]  # Remove the // urlunparse puts in the beginning
    return unparsed


class IS_GENERIC_URL(Validator):
    """
    Rejects a URL string if any of the following is true:
       * The string is empty or None
       * The string uses characters that are not allowed in a URL
       * The URL scheme specified (if one is specified) is not valid

    Based on RFC 2396: http://www.faqs.org/rfcs/rfc2396.html

    This function only checks the URL's syntax. It does not check that the URL
    points to a real document, for example, or that it otherwise makes sense
    semantically. This function does automatically prepend 'http://' in front
    of a URL if and only if that's necessary to successfully parse the URL.
    Please note that a scheme will be prepended only for rare cases
    (e.g. 'google.ca:80')

    The list of allowed schemes is customizable with the allowed_schemes
    parameter. If you exclude None from the list, then abbreviated URLs
    (lacking a scheme such as 'http') will be rejected.

    The default prepended scheme is customizable with the prepend_scheme
    parameter. If you set prepend_scheme to None then prepending will be
    disabled. URLs that require prepending to parse will still be accepted,
    but the return value will not be modified.

    @author: Jonathan Benn

        >>> IS_GENERIC_URL()('http://user@abc.com')
        ('http://user@abc.com', None)

    Args:
        error_message: a string, the error message to give the end user
            if the URL does not validate
        allowed_schemes: a list containing strings or None. Each element
            is a scheme the inputted URL is allowed to use
        prepend_scheme: a string, this scheme is prepended if it's
            necessary to make the URL valid

    """

    def __init__(
        self,
        error_message="Enter a valid URL",
        allowed_schemes=None,
        prepend_scheme=None,
    ):
        self.error_message = error_message
        if allowed_schemes is None:
            self.allowed_schemes = all_url_schemes
        else:
            self.allowed_schemes = allowed_schemes
        self.prepend_scheme = prepend_scheme
        if self.prepend_scheme not in self.allowed_schemes:
            raise SyntaxError(
                "prepend_scheme='%s' is not in allowed_schemes=%s"
                % (self.prepend_scheme, self.allowed_schemes)
            )

    REGEX_GENERIC_URL = r"%[^0-9A-Fa-f]{2}|%[^0-9A-Fa-f][0-9A-Fa-f]|%[0-9A-Fa-f][^0-9A-Fa-f]|%$|%[0-9A-Fa-f]$|%[^0-9A-Fa-f]$"
    REGEX_GENERIC_URL_VALID = r"[A-Za-z0-9;/?:@&=+$,\-_\.!~*'\(\)%]+$"
    REGEX_URL_FRAGMENT_VALID = r"[|A-Za-z0-9;/?:@&=+$,\-_\.!~*'\(\)%]+$"

    def validate(self, value, record_id=None):
        """
        Args:
            value: a string, the URL to validate

        Returns:
            a tuple, where tuple[0] is the inputted value (possible
            prepended with prepend_scheme), and tuple[1] is either
            None (success!) or the string error_message
        """

        # if we dont have anything or the URL misuses the '%' character

        if not value or re.search(self.REGEX_GENERIC_URL, value):
            raise ValidationError(self.translator(self.error_message))

        if "#" in value:
            url, fragment_part = value.split("#")
        else:
            url, fragment_part = value, ""
        # if the URL is only composed of valid characters
        if not re.match(self.REGEX_GENERIC_URL_VALID, url) or (
            fragment_part and not re.match(self.REGEX_URL_FRAGMENT_VALID, fragment_part)
        ):
            raise ValidationError(self.translator(self.error_message))
        # Then parse the URL into its components and check on
        try:
            components = urlparse.urlparse(urllib_unquote(value))._asdict()
        except ValueError:
            raise ValidationError(self.translator(self.error_message))

        # Clean up the scheme before we check it
        scheme = components["scheme"]
        if len(scheme) == 0:
            scheme = None
        else:
            scheme = components["scheme"].lower()
        # If the scheme doesn't really exists
        if (
            scheme not in self.allowed_schemes
            or not scheme
            and ":" in components["path"]
        ):
            # for the possible case of abbreviated URLs with
            # ports, check to see if adding a valid scheme fixes
            # the problem (but only do this if it doesn't have
            # one already!)
            if "://" not in value and None in self.allowed_schemes:
                schemeToUse = self.prepend_scheme or "http"
                new_value = self.validate(schemeToUse + "://" + value)
                return new_value if self.prepend_scheme else value
            raise ValidationError(self.translator(self.error_message))
        return value


# Sources (obtained 2017-Nov-11):
#    http://data.iana.org/TLD/tlds-alpha-by-domain.txt
# see scripts/parse_top_level_domains.py for an easy update

official_top_level_domains = [
    # a
    "aaa",
    "aarp",
    "abarth",
    "abb",
    "abbott",
    "abbvie",
    "abc",
    "able",
    "abogado",
    "abudhabi",
    "ac",
    "academy",
    "accenture",
    "accountant",
    "accountants",
    "aco",
    "active",
    "actor",
    "ad",
    "adac",
    "ads",
    "adult",
    "ae",
    "aeg",
    "aero",
    "aetna",
    "af",
    "afamilycompany",
    "afl",
    "africa",
    "ag",
    "agakhan",
    "agency",
    "ai",
    "aig",
    "aigo",
    "airbus",
    "airforce",
    "airtel",
    "akdn",
    "al",
    "alfaromeo",
    "alibaba",
    "alipay",
    "allfinanz",
    "allstate",
    "ally",
    "alsace",
    "alstom",
    "am",
    "americanexpress",
    "americanfamily",
    "amex",
    "amfam",
    "amica",
    "amsterdam",
    "analytics",
    "android",
    "anquan",
    "anz",
    "ao",
    "aol",
    "apartments",
    "app",
    "apple",
    "aq",
    "aquarelle",
    "ar",
    "arab",
    "aramco",
    "archi",
    "army",
    "arpa",
    "art",
    "arte",
    "as",
    "asda",
    "asia",
    "associates",
    "at",
    "athleta",
    "attorney",
    "au",
    "auction",
    "audi",
    "audible",
    "audio",
    "auspost",
    "author",
    "auto",
    "autos",
    "avianca",
    "aw",
    "aws",
    "ax",
    "axa",
    "az",
    "azure",
    # b
    "ba",
    "baby",
    "baidu",
    "banamex",
    "bananarepublic",
    "band",
    "bank",
    "bar",
    "barcelona",
    "barclaycard",
    "barclays",
    "barefoot",
    "bargains",
    "baseball",
    "basketball",
    "bauhaus",
    "bayern",
    "bb",
    "bbc",
    "bbt",
    "bbva",
    "bcg",
    "bcn",
    "bd",
    "be",
    "beats",
    "beauty",
    "beer",
    "bentley",
    "berlin",
    "best",
    "bestbuy",
    "bet",
    "bf",
    "bg",
    "bh",
    "bharti",
    "bi",
    "bible",
    "bid",
    "bike",
    "bing",
    "bingo",
    "bio",
    "biz",
    "bj",
    "black",
    "blackfriday",
    "blanco",
    "blockbuster",
    "blog",
    "bloomberg",
    "blue",
    "bm",
    "bms",
    "bmw",
    "bn",
    "bnl",
    "bnpparibas",
    "bo",
    "boats",
    "boehringer",
    "bofa",
    "bom",
    "bond",
    "boo",
    "book",
    "booking",
    "boots",
    "bosch",
    "bostik",
    "boston",
    "bot",
    "boutique",
    "box",
    "br",
    "bradesco",
    "bridgestone",
    "broadway",
    "broker",
    "brother",
    "brussels",
    "bs",
    "bt",
    "budapest",
    "bugatti",
    "build",
    "builders",
    "business",
    "buy",
    "buzz",
    "bv",
    "bw",
    "by",
    "bz",
    "bzh",
    # c
    "ca",
    "cab",
    "cafe",
    "cal",
    "call",
    "calvinklein",
    "cam",
    "camera",
    "camp",
    "cancerresearch",
    "canon",
    "capetown",
    "capital",
    "capitalone",
    "car",
    "caravan",
    "cards",
    "care",
    "career",
    "careers",
    "cars",
    "cartier",
    "casa",
    "case",
    "caseih",
    "cash",
    "casino",
    "cat",
    "catering",
    "catholic",
    "cba",
    "cbn",
    "cbre",
    "cbs",
    "cc",
    "cd",
    "ceb",
    "center",
    "ceo",
    "cern",
    "cf",
    "cfa",
    "cfd",
    "cg",
    "ch",
    "chanel",
    "channel",
    "chase",
    "chat",
    "cheap",
    "chintai",
    "christmas",
    "chrome",
    "chrysler",
    "church",
    "ci",
    "cipriani",
    "circle",
    "cisco",
    "citadel",
    "citi",
    "citic",
    "city",
    "cityeats",
    "ck",
    "cl",
    "claims",
    "cleaning",
    "click",
    "clinic",
    "clinique",
    "clothing",
    "cloud",
    "club",
    "clubmed",
    "cm",
    "cn",
    "co",
    "coach",
    "codes",
    "coffee",
    "college",
    "cologne",
    "com",
    "comcast",
    "commbank",
    "community",
    "company",
    "compare",
    "computer",
    "comsec",
    "condos",
    "construction",
    "consulting",
    "contact",
    "contractors",
    "cooking",
    "cookingchannel",
    "cool",
    "coop",
    "corsica",
    "country",
    "coupon",
    "coupons",
    "courses",
    "cr",
    "credit",
    "creditcard",
    "creditunion",
    "cricket",
    "crown",
    "crs",
    "cruise",
    "cruises",
    "csc",
    "cu",
    "cuisinella",
    "cv",
    "cw",
    "cx",
    "cy",
    "cymru",
    "cyou",
    "cz",
    # d
    "dabur",
    "dad",
    "dance",
    "data",
    "date",
    "dating",
    "datsun",
    "day",
    "dclk",
    "dds",
    "de",
    "deal",
    "dealer",
    "deals",
    "degree",
    "delivery",
    "dell",
    "deloitte",
    "delta",
    "democrat",
    "dental",
    "dentist",
    "desi",
    "design",
    "dev",
    "dhl",
    "diamonds",
    "diet",
    "digital",
    "direct",
    "directory",
    "discount",
    "discover",
    "dish",
    "diy",
    "dj",
    "dk",
    "dm",
    "dnp",
    "do",
    "docs",
    "doctor",
    "dodge",
    "dog",
    "doha",
    "domains",
    "dot",
    "download",
    "drive",
    "dtv",
    "dubai",
    "duck",
    "dunlop",
    "duns",
    "dupont",
    "durban",
    "dvag",
    "dvr",
    "dz",
    # e
    "earth",
    "eat",
    "ec",
    "eco",
    "edeka",
    "edu",
    "education",
    "ee",
    "eg",
    "email",
    "emerck",
    "energy",
    "engineer",
    "engineering",
    "enterprises",
    "epost",
    "epson",
    "equipment",
    "er",
    "ericsson",
    "erni",
    "es",
    "esq",
    "estate",
    "esurance",
    "et",
    "etisalat",
    "eu",
    "eurovision",
    "eus",
    "events",
    "everbank",
    "exchange",
    "expert",
    "exposed",
    "express",
    "extraspace",
    # f
    "fage",
    "fail",
    "fairwinds",
    "faith",
    "family",
    "fan",
    "fans",
    "farm",
    "farmers",
    "fashion",
    "fast",
    "fedex",
    "feedback",
    "ferrari",
    "ferrero",
    "fi",
    "fiat",
    "fidelity",
    "fido",
    "film",
    "final",
    "finance",
    "financial",
    "fire",
    "firestone",
    "firmdale",
    "fish",
    "fishing",
    "fit",
    "fitness",
    "fj",
    "fk",
    "flickr",
    "flights",
    "flir",
    "florist",
    "flowers",
    "fly",
    "fm",
    "fo",
    "foo",
    "food",
    "foodnetwork",
    "football",
    "ford",
    "forex",
    "forsale",
    "forum",
    "foundation",
    "fox",
    "fr",
    "free",
    "fresenius",
    "frl",
    "frogans",
    "frontdoor",
    "frontier",
    "ftr",
    "fujitsu",
    "fujixerox",
    "fun",
    "fund",
    "furniture",
    "futbol",
    "fyi",
    # g
    "ga",
    "gal",
    "gallery",
    "gallo",
    "gallup",
    "game",
    "games",
    "gap",
    "garden",
    "gb",
    "gbiz",
    "gd",
    "gdn",
    "ge",
    "gea",
    "gent",
    "genting",
    "george",
    "gf",
    "gg",
    "ggee",
    "gh",
    "gi",
    "gift",
    "gifts",
    "gives",
    "giving",
    "gl",
    "glade",
    "glass",
    "gle",
    "global",
    "globo",
    "gm",
    "gmail",
    "gmbh",
    "gmo",
    "gmx",
    "gn",
    "godaddy",
    "gold",
    "goldpoint",
    "golf",
    "goo",
    "goodhands",
    "goodyear",
    "goog",
    "google",
    "gop",
    "got",
    "gov",
    "gp",
    "gq",
    "gr",
    "grainger",
    "graphics",
    "gratis",
    "green",
    "gripe",
    "grocery",
    "group",
    "gs",
    "gt",
    "gu",
    "guardian",
    "gucci",
    "guge",
    "guide",
    "guitars",
    "guru",
    "gw",
    "gy",
    # h
    "hair",
    "hamburg",
    "hangout",
    "haus",
    "hbo",
    "hdfc",
    "hdfcbank",
    "health",
    "healthcare",
    "help",
    "helsinki",
    "here",
    "hermes",
    "hgtv",
    "hiphop",
    "hisamitsu",
    "hitachi",
    "hiv",
    "hk",
    "hkt",
    "hm",
    "hn",
    "hockey",
    "holdings",
    "holiday",
    "homedepot",
    "homegoods",
    "homes",
    "homesense",
    "honda",
    "honeywell",
    "horse",
    "hospital",
    "host",
    "hosting",
    "hot",
    "hoteles",
    "hotels",
    "hotmail",
    "house",
    "how",
    "hr",
    "hsbc",
    "ht",
    "hu",
    "hughes",
    "hyatt",
    "hyundai",
    # i
    "ibm",
    "icbc",
    "ice",
    "icu",
    "id",
    "ie",
    "ieee",
    "ifm",
    "ikano",
    "il",
    "im",
    "imamat",
    "imdb",
    "immo",
    "immobilien",
    "in",
    "industries",
    "infiniti",
    "info",
    "ing",
    "ink",
    "institute",
    "insurance",
    "insure",
    "int",
    "intel",
    "international",
    "intuit",
    "investments",
    "io",
    "ipiranga",
    "iq",
    "ir",
    "irish",
    "is",
    "iselect",
    "ismaili",
    "ist",
    "istanbul",
    "it",
    "itau",
    "itv",
    "iveco",
    "iwc",
    # j
    "jaguar",
    "java",
    "jcb",
    "jcp",
    "je",
    "jeep",
    "jetzt",
    "jewelry",
    "jio",
    "jlc",
    "jll",
    "jm",
    "jmp",
    "jnj",
    "jo",
    "jobs",
    "joburg",
    "jot",
    "joy",
    "jp",
    "jpmorgan",
    "jprs",
    "juegos",
    "juniper",
    # k
    "kaufen",
    "kddi",
    "ke",
    "kerryhotels",
    "kerrylogistics",
    "kerryproperties",
    "kfh",
    "kg",
    "kh",
    "ki",
    "kia",
    "kim",
    "kinder",
    "kindle",
    "kitchen",
    "kiwi",
    "km",
    "kn",
    "koeln",
    "komatsu",
    "kosher",
    "kp",
    "kpmg",
    "kpn",
    "kr",
    "krd",
    "kred",
    "kuokgroup",
    "kw",
    "ky",
    "kyoto",
    "kz",
    # l
    "la",
    "lacaixa",
    "ladbrokes",
    "lamborghini",
    "lamer",
    "lancaster",
    "lancia",
    "lancome",
    "land",
    "landrover",
    "lanxess",
    "lasalle",
    "lat",
    "latino",
    "latrobe",
    "law",
    "lawyer",
    "lb",
    "lc",
    "lds",
    "lease",
    "leclerc",
    "lefrak",
    "legal",
    "lego",
    "lexus",
    "lgbt",
    "li",
    "liaison",
    "lidl",
    "life",
    "lifeinsurance",
    "lifestyle",
    "lighting",
    "like",
    "lilly",
    "limited",
    "limo",
    "lincoln",
    "linde",
    "link",
    "lipsy",
    "live",
    "living",
    "lixil",
    "lk",
    "loan",
    "loans",
    "localhost",
    "locker",
    "locus",
    "loft",
    "lol",
    "london",
    "lotte",
    "lotto",
    "love",
    "lpl",
    "lplfinancial",
    "lr",
    "ls",
    "lt",
    "ltd",
    "ltda",
    "lu",
    "lundbeck",
    "lupin",
    "luxe",
    "luxury",
    "lv",
    "ly",
    # m
    "ma",
    "macys",
    "madrid",
    "maif",
    "maison",
    "makeup",
    "man",
    "management",
    "mango",
    "map",
    "market",
    "marketing",
    "markets",
    "marriott",
    "marshalls",
    "maserati",
    "mattel",
    "mba",
    "mc",
    "mckinsey",
    "md",
    "me",
    "med",
    "media",
    "meet",
    "melbourne",
    "meme",
    "memorial",
    "men",
    "menu",
    "meo",
    "merckmsd",
    "metlife",
    "mg",
    "mh",
    "miami",
    "microsoft",
    "mil",
    "mini",
    "mint",
    "mit",
    "mitsubishi",
    "mk",
    "ml",
    "mlb",
    "mls",
    "mm",
    "mma",
    "mn",
    "mo",
    "mobi",
    "mobile",
    "mobily",
    "moda",
    "moe",
    "moi",
    "mom",
    "monash",
    "money",
    "monster",
    "mopar",
    "mormon",
    "mortgage",
    "moscow",
    "moto",
    "motorcycles",
    "mov",
    "movie",
    "movistar",
    "mp",
    "mq",
    "mr",
    "ms",
    "msd",
    "mt",
    "mtn",
    "mtr",
    "mu",
    "museum",
    "mutual",
    "mv",
    "mw",
    "mx",
    "my",
    "mz",
    # n
    "na",
    "nab",
    "nadex",
    "nagoya",
    "name",
    "nationwide",
    "natura",
    "navy",
    "nba",
    "nc",
    "ne",
    "nec",
    "net",
    "netbank",
    "netflix",
    "network",
    "neustar",
    "new",
    "newholland",
    "news",
    "next",
    "nextdirect",
    "nexus",
    "nf",
    "nfl",
    "ng",
    "ngo",
    "nhk",
    "ni",
    "nico",
    "nike",
    "nikon",
    "ninja",
    "nissan",
    "nissay",
    "nl",
    "no",
    "nokia",
    "northwesternmutual",
    "norton",
    "now",
    "nowruz",
    "nowtv",
    "np",
    "nr",
    "nra",
    "nrw",
    "ntt",
    "nu",
    "nyc",
    "nz",
    # o
    "obi",
    "observer",
    "off",
    "office",
    "okinawa",
    "olayan",
    "olayangroup",
    "oldnavy",
    "ollo",
    "om",
    "omega",
    "one",
    "ong",
    "onl",
    "online",
    "onyourside",
    "ooo",
    "open",
    "oracle",
    "orange",
    "org",
    "organic",
    "origins",
    "osaka",
    "otsuka",
    "ott",
    "ovh",
    # p
    "pa",
    "page",
    "panasonic",
    "panerai",
    "paris",
    "pars",
    "partners",
    "parts",
    "party",
    "passagens",
    "pay",
    "pccw",
    "pe",
    "pet",
    "pf",
    "pfizer",
    "pg",
    "ph",
    "pharmacy",
    "phd",
    "philips",
    "phone",
    "photo",
    "photography",
    "photos",
    "physio",
    "piaget",
    "pics",
    "pictet",
    "pictures",
    "pid",
    "pin",
    "ping",
    "pink",
    "pioneer",
    "pizza",
    "pk",
    "pl",
    "place",
    "play",
    "playstation",
    "plumbing",
    "plus",
    "pm",
    "pn",
    "pnc",
    "pohl",
    "poker",
    "politie",
    "porn",
    "post",
    "pr",
    "pramerica",
    "praxi",
    "press",
    "prime",
    "pro",
    "prod",
    "productions",
    "prof",
    "progressive",
    "promo",
    "properties",
    "property",
    "protection",
    "pru",
    "prudential",
    "ps",
    "pt",
    "pub",
    "pw",
    "pwc",
    "py",
    # q
    "qa",
    "qpon",
    "quebec",
    "quest",
    "qvc",
    # r
    "racing",
    "radio",
    "raid",
    "re",
    "read",
    "realestate",
    "realtor",
    "realty",
    "recipes",
    "red",
    "redstone",
    "redumbrella",
    "rehab",
    "reise",
    "reisen",
    "reit",
    "reliance",
    "ren",
    "rent",
    "rentals",
    "repair",
    "report",
    "republican",
    "rest",
    "restaurant",
    "review",
    "reviews",
    "rexroth",
    "rich",
    "richardli",
    "ricoh",
    "rightathome",
    "ril",
    "rio",
    "rip",
    "rmit",
    "ro",
    "rocher",
    "rocks",
    "rodeo",
    "rogers",
    "room",
    "rs",
    "rsvp",
    "ru",
    "rugby",
    "ruhr",
    "run",
    "rw",
    "rwe",
    "ryukyu",
    # s
    "sa",
    "saarland",
    "safe",
    "safety",
    "sakura",
    "sale",
    "salon",
    "samsclub",
    "samsung",
    "sandvik",
    "sandvikcoromant",
    "sanofi",
    "sap",
    "sapo",
    "sarl",
    "sas",
    "save",
    "saxo",
    "sb",
    "sbi",
    "sbs",
    "sc",
    "sca",
    "scb",
    "schaeffler",
    "schmidt",
    "scholarships",
    "school",
    "schule",
    "schwarz",
    "science",
    "scjohnson",
    "scor",
    "scot",
    "sd",
    "se",
    "search",
    "seat",
    "secure",
    "security",
    "seek",
    "select",
    "sener",
    "services",
    "ses",
    "seven",
    "sew",
    "sex",
    "sexy",
    "sfr",
    "sg",
    "sh",
    "shangrila",
    "sharp",
    "shaw",
    "shell",
    "shia",
    "shiksha",
    "shoes",
    "shop",
    "shopping",
    "shouji",
    "show",
    "showtime",
    "shriram",
    "si",
    "silk",
    "sina",
    "singles",
    "site",
    "sj",
    "sk",
    "ski",
    "skin",
    "sky",
    "skype",
    "sl",
    "sling",
    "sm",
    "smart",
    "smile",
    "sn",
    "sncf",
    "so",
    "soccer",
    "social",
    "softbank",
    "software",
    "sohu",
    "solar",
    "solutions",
    "song",
    "sony",
    "soy",
    "space",
    "spiegel",
    "spot",
    "spreadbetting",
    "sr",
    "srl",
    "srt",
    "st",
    "stada",
    "staples",
    "star",
    "starhub",
    "statebank",
    "statefarm",
    "statoil",
    "stc",
    "stcgroup",
    "stockholm",
    "storage",
    "store",
    "stream",
    "studio",
    "study",
    "style",
    "su",
    "sucks",
    "supplies",
    "supply",
    "support",
    "surf",
    "surgery",
    "suzuki",
    "sv",
    "swatch",
    "swiftcover",
    "swiss",
    "sx",
    "sy",
    "sydney",
    "symantec",
    "systems",
    "sz",
    # t
    "tab",
    "taipei",
    "talk",
    "taobao",
    "target",
    "tatamotors",
    "tatar",
    "tattoo",
    "tax",
    "taxi",
    "tc",
    "tci",
    "td",
    "tdk",
    "team",
    "tech",
    "technology",
    "tel",
    "telecity",
    "telefonica",
    "temasek",
    "tennis",
    "teva",
    "tf",
    "tg",
    "th",
    "thd",
    "theater",
    "theatre",
    "tiaa",
    "tickets",
    "tienda",
    "tiffany",
    "tips",
    "tires",
    "tirol",
    "tj",
    "tjmaxx",
    "tjx",
    "tk",
    "tkmaxx",
    "tl",
    "tm",
    "tmall",
    "tn",
    "to",
    "today",
    "tokyo",
    "tools",
    "top",
    "toray",
    "toshiba",
    "total",
    "tours",
    "town",
    "toyota",
    "toys",
    "tr",
    "trade",
    "trading",
    "training",
    "travel",
    "travelchannel",
    "travelers",
    "travelersinsurance",
    "trust",
    "trv",
    "tt",
    "tube",
    "tui",
    "tunes",
    "tushu",
    "tv",
    "tvs",
    "tw",
    "tz",
    # u
    "ua",
    "ubank",
    "ubs",
    "uconnect",
    "ug",
    "uk",
    "unicom",
    "university",
    "uno",
    "uol",
    "ups",
    "us",
    "uy",
    "uz",
    # v
    "va",
    "vacations",
    "vana",
    "vanguard",
    "vc",
    "ve",
    "vegas",
    "ventures",
    "verisign",
    "versicherung",
    "vet",
    "vg",
    "vi",
    "viajes",
    "video",
    "vig",
    "viking",
    "villas",
    "vin",
    "vip",
    "virgin",
    "visa",
    "vision",
    "vista",
    "vistaprint",
    "viva",
    "vivo",
    "vlaanderen",
    "vn",
    "vodka",
    "volkswagen",
    "volvo",
    "vote",
    "voting",
    "voto",
    "voyage",
    "vu",
    "vuelos",
    # w
    "wales",
    "walmart",
    "walter",
    "wang",
    "wanggou",
    "warman",
    "watch",
    "watches",
    "weather",
    "weatherchannel",
    "webcam",
    "weber",
    "website",
    "wed",
    "wedding",
    "weibo",
    "weir",
    "wf",
    "whoswho",
    "wien",
    "wiki",
    "williamhill",
    "win",
    "windows",
    "wine",
    "winners",
    "wme",
    "wolterskluwer",
    "woodside",
    "work",
    "works",
    "world",
    "wow",
    "ws",
    "wtc",
    "wtf",
    # x
    "xbox",
    "xerox",
    "xfinity",
    "xihuan",
    "xin",
    "xn--11b4c3d",
    "xn--1ck2e1b",
    "xn--1qqw23a",
    "xn--2scrj9c",
    "xn--30rr7y",
    "xn--3bst00m",
    "xn--3ds443g",
    "xn--3e0b707e",
    "xn--3hcrj9c",
    "xn--3oq18vl8pn36a",
    "xn--3pxu8k",
    "xn--42c2d9a",
    "xn--45br5cyl",
    "xn--45brj9c",
    "xn--45q11c",
    "xn--4gbrim",
    "xn--54b7fta0cc",
    "xn--55qw42g",
    "xn--55qx5d",
    "xn--5su34j936bgsg",
    "xn--5tzm5g",
    "xn--6frz82g",
    "xn--6qq986b3xl",
    "xn--80adxhks",
    "xn--80ao21a",
    "xn--80aqecdr1a",
    "xn--80asehdb",
    "xn--80aswg",
    "xn--8y0a063a",
    "xn--90a3ac",
    "xn--90ae",
    "xn--90ais",
    "xn--9dbq2a",
    "xn--9et52u",
    "xn--9krt00a",
    "xn--b4w605ferd",
    "xn--bck1b9a5dre4c",
    "xn--c1avg",
    "xn--c2br7g",
    "xn--cck2b3b",
    "xn--cg4bki",
    "xn--clchc0ea0b2g2a9gcd",
    "xn--czr694b",
    "xn--czrs0t",
    "xn--czru2d",
    "xn--d1acj3b",
    "xn--d1alf",
    "xn--e1a4c",
    "xn--eckvdtc9d",
    "xn--efvy88h",
    "xn--estv75g",
    "xn--fct429k",
    "xn--fhbei",
    "xn--fiq228c5hs",
    "xn--fiq64b",
    "xn--fiqs8s",
    "xn--fiqz9s",
    "xn--fjq720a",
    "xn--flw351e",
    "xn--fpcrj9c3d",
    "xn--fzc2c9e2c",
    "xn--fzys8d69uvgm",
    "xn--g2xx48c",
    "xn--gckr3f0f",
    "xn--gecrj9c",
    "xn--gk3at1e",
    "xn--h2breg3eve",
    "xn--h2brj9c",
    "xn--h2brj9c8c",
    "xn--hxt814e",
    "xn--i1b6b1a6a2e",
    "xn--imr513n",
    "xn--io0a7i",
    "xn--j1aef",
    "xn--j1amh",
    "xn--j6w193g",
    "xn--jlq61u9w7b",
    "xn--jvr189m",
    "xn--kcrx77d1x4a",
    "xn--kprw13d",
    "xn--kpry57d",
    "xn--kpu716f",
    "xn--kput3i",
    "xn--l1acc",
    "xn--lgbbat1ad8j",
    "xn--mgb9awbf",
    "xn--mgba3a3ejt",
    "xn--mgba3a4f16a",
    "xn--mgba7c0bbn0a",
    "xn--mgbaakc7dvf",
    "xn--mgbaam7a8h",
    "xn--mgbab2bd",
    "xn--mgbai9azgqp6j",
    "xn--mgbayh7gpa",
    "xn--mgbb9fbpob",
    "xn--mgbbh1a",
    "xn--mgbbh1a71e",
    "xn--mgbc0a9azcg",
    "xn--mgbca7dzdo",
    "xn--mgberp4a5d4ar",
    "xn--mgbgu82a",
    "xn--mgbi4ecexp",
    "xn--mgbpl2fh",
    "xn--mgbt3dhd",
    "xn--mgbtx2b",
    "xn--mgbx4cd0ab",
    "xn--mix891f",
    "xn--mk1bu44c",
    "xn--mxtq1m",
    "xn--ngbc5azd",
    "xn--ngbe9e0a",
    "xn--ngbrx",
    "xn--node",
    "xn--nqv7f",
    "xn--nqv7fs00ema",
    "xn--nyqy26a",
    "xn--o3cw4h",
    "xn--ogbpf8fl",
    "xn--p1acf",
    "xn--p1ai",
    "xn--pbt977c",
    "xn--pgbs0dh",
    "xn--pssy2u",
    "xn--q9jyb4c",
    "xn--qcka1pmc",
    "xn--qxam",
    "xn--rhqv96g",
    "xn--rovu88b",
    "xn--rvc1e0am3e",
    "xn--s9brj9c",
    "xn--ses554g",
    "xn--t60b56a",
    "xn--tckwe",
    "xn--tiq49xqyj",
    "xn--unup4y",
    "xn--vermgensberater-ctb",
    "xn--vermgensberatung-pwb",
    "xn--vhquv",
    "xn--vuq861b",
    "xn--w4r85el8fhu5dnra",
    "xn--w4rs40l",
    "xn--wgbh1c",
    "xn--wgbl6a",
    "xn--xhq521b",
    "xn--xkc2al3hye2a",
    "xn--xkc2dl3a5ee0h",
    "xn--y9a3aq",
    "xn--yfro4i67o",
    "xn--ygbi2ammx",
    "xn--zfr164b",
    "xperia",
    "xxx",
    "xyz",
    # y
    "yachts",
    "yahoo",
    "yamaxun",
    "yandex",
    "ye",
    "yodobashi",
    "yoga",
    "yokohama",
    "you",
    "youtube",
    "yt",
    "yun",
    # z
    "za",
    "zappos",
    "zara",
    "zero",
    "zip",
    "zippo",
    "zm",
    "zone",
    "zuerich",
    "zw",
]


class IS_HTTP_URL(Validator):
    """
    Rejects a URL string if any of the following is true:
       * The string is empty or None
       * The string uses characters that are not allowed in a URL
       * The string breaks any of the HTTP syntactic rules
       * The URL scheme specified (if one is specified) is not 'http' or 'https'
       * The top-level domain (if a host name is specified) does not exist

    Based on RFC 2616: http://www.faqs.org/rfcs/rfc2616.html

    This function only checks the URL's syntax. It does not check that the URL
    points to a real document, for example, or that it otherwise makes sense
    semantically. This function does automatically prepend 'http://' in front
    of a URL in the case of an abbreviated URL (e.g. 'google.ca').

    The list of allowed schemes is customizable with the allowed_schemes
    parameter. If you exclude None from the list, then abbreviated URLs
    (lacking a scheme such as 'http') will be rejected.

    The default prepended scheme is customizable with the prepend_scheme
    parameter. If you set prepend_scheme to None then prepending will be
    disabled. URLs that require prepending to parse will still be accepted,
    but the return value will not be modified.

    @author: Jonathan Benn

        >>> IS_HTTP_URL()('http://1.2.3.4')
        ('http://1.2.3.4', None)
        >>> IS_HTTP_URL()('http://abc.com')
        ('http://abc.com', None)
        >>> IS_HTTP_URL()('https://abc.com')
        ('https://abc.com', None)
        >>> IS_HTTP_URL()('httpx://abc.com')
        ('httpx://abc.com', 'enter a valid URL')
        >>> IS_HTTP_URL()('http://abc.com:80')
        ('http://abc.com:80', None)
        >>> IS_HTTP_URL()('http://user@abc.com')
        ('http://user@abc.com', None)
        >>> IS_HTTP_URL()('http://user@1.2.3.4')
        ('http://user@1.2.3.4', None)

    Args:
        error_message: a string, the error message to give the end user
            if the URL does not validate
        allowed_schemes: a list containing strings or None. Each element
            is a scheme the inputted URL is allowed to use
        prepend_scheme: a string, this scheme is prepended if it's
            necessary to make the URL valid
    """

    REGEX_GENERIC_VALID_IP = r"([\w.!~*'|;:&=+$,-]+@)?\d+\.\d+\.\d+\.\d+(:\d*)*$"
    REGEX_GENERIC_VALID_DOMAIN = r"([\w.!~*'|;:&=+$,-]+@)?(([A-Za-z0-9]+[A-Za-z0-9\-]*[A-Za-z0-9]+\.)*([A-Za-z0-9]+\.)*)*([A-Za-z]+[A-Za-z0-9\-]*[A-Za-z0-9]+)\.?(:\d*)*$"

    def __init__(
        self,
        error_message="Enter a valid URL",
        allowed_schemes=None,
        prepend_scheme="http",
        allowed_tlds=None,
    ):
        self.error_message = error_message
        if allowed_schemes is None:
            self.allowed_schemes = http_schemes
        else:
            self.allowed_schemes = allowed_schemes
        if allowed_tlds is None:
            self.allowed_tlds = official_top_level_domains
        else:
            self.allowed_tlds = allowed_tlds
        self.prepend_scheme = prepend_scheme

        for i in self.allowed_schemes:
            if i not in http_schemes:
                raise SyntaxError(
                    "allowed_scheme value '%s' is not in %s" % (i, http_schemes)
                )

        if self.prepend_scheme not in self.allowed_schemes:
            raise SyntaxError(
                "prepend_scheme='%s' is not in allowed_schemes=%s"
                % (self.prepend_scheme, self.allowed_schemes)
            )

    def validate(self, value, record_id=None):
        """
        Args:
            value: a string, the URL to validate

        Returns:
            a tuple, where tuple[0] is the inputted value
            (possible prepended with prepend_scheme), and tuple[1] is either
            None (success!) or the string error_message
        """
        try:
            # if the URL passes generic validation
            x = IS_GENERIC_URL(
                error_message=self.error_message,
                allowed_schemes=self.allowed_schemes,
                prepend_scheme=self.prepend_scheme,
            )
            if x(value)[1] is None:
                components = urlparse.urlparse(value)
                authority = components.netloc
                # if there is an authority component
                if authority:
                    # if authority is a valid IP address
                    if re.match(self.REGEX_GENERIC_VALID_IP, authority):
                        # Then this HTTP URL is valid
                        return value
                    else:
                        # else if authority is a valid domain name
                        domainMatch = re.match(
                            self.REGEX_GENERIC_VALID_DOMAIN, authority
                        )
                        if domainMatch:
                            # if the top-level domain really exists
                            if domainMatch.group(5).lower() in self.allowed_tlds:
                                # Then this HTTP URL is valid
                                return value
                else:
                    # else this is a relative/abbreviated URL, which will parse
                    # into the URL's path component
                    path = components.path
                    # relative case: if this is a valid path (if it starts with
                    # a slash)
                    if not path.startswith("/"):
                        # abbreviated case: if we haven't already, prepend a
                        # scheme and see if it fixes the problem
                        if "://" not in value and None in self.allowed_schemes:
                            schemeToUse = self.prepend_scheme or "http"
                            new_value = self.validate(schemeToUse + "://" + value)
                            return new_value if self.prepend_scheme else value
                    return value
        except:
            pass
        raise ValidationError(self.translator(self.error_message))


class IS_URL(Validator):
    """
    Rejects a URL string if any of the following is true:

       * The string is empty or None
       * The string uses characters that are not allowed in a URL
       * The string breaks any of the HTTP syntactic rules
       * The URL scheme specified (if one is specified) is not 'http' or 'https'
       * The top-level domain (if a host name is specified) does not exist

    (These rules are based on RFC 2616: http://www.faqs.org/rfcs/rfc2616.html)

    This function only checks the URL's syntax. It does not check that the URL
    points to a real document, for example, or that it otherwise makes sense
    semantically. This function does automatically prepend 'http://' in front
    of a URL in the case of an abbreviated URL (e.g. 'google.ca').

    If the parameter mode='generic' is used, then this function's behavior
    changes. It then rejects a URL string if any of the following is true:

       * The string is empty or None
       * The string uses characters that are not allowed in a URL
       * The URL scheme specified (if one is specified) is not valid

    (These rules are based on RFC 2396: http://www.faqs.org/rfcs/rfc2396.html)

    The list of allowed schemes is customizable with the allowed_schemes
    parameter. If you exclude None from the list, then abbreviated URLs
    (lacking a scheme such as 'http') will be rejected.

    The default prepended scheme is customizable with the prepend_scheme
    parameter. If you set prepend_scheme to None then prepending will be
    disabled. URLs that require prepending to parse will still be accepted,
    but the return value will not be modified.

    IS_URL is compatible with the Internationalized Domain Name (IDN) standard
    specified in RFC 3490 (http://tools.ietf.org/html/rfc3490). As a result,
    URLs can be regular strings or unicode strings.
    If the URL's domain component (e.g. google.ca) contains non-US-ASCII
    letters, then the domain will be converted into Punycode (defined in
    RFC 3492, http://tools.ietf.org/html/rfc3492). IS_URL goes a bit beyond
    the standards, and allows non-US-ASCII characters to be present in the path
    and query components of the URL as well. These non-US-ASCII characters will
    be escaped using the standard '%20' type syntax. e.g. the unicode
    character with hex code 0x4e86 will become '%4e%86'

    Args:
        error_message: a string, the error message to give the end user
            if the URL does not validate
        allowed_schemes: a list containing strings or None. Each element
            is a scheme the inputted URL is allowed to use
        prepend_scheme: a string, this scheme is prepended if it's
            necessary to make the URL valid

    Code Examples::

        INPUT(_type='text', _name='name', requires=IS_URL())
        >>> IS_URL()('abc.com')
        ('http://abc.com', None)

        INPUT(_type='text', _name='name', requires=IS_URL(mode='generic'))
        >>> IS_URL(mode='generic')('abc.com')
        ('abc.com', None)

        INPUT(_type='text', _name='name',
            requires=IS_URL(allowed_schemes=['https'], prepend_scheme='https'))
        >>> IS_URL(allowed_schemes=['https'], prepend_scheme='https')('https://abc.com')
        ('https://abc.com', None)

        INPUT(_type='text', _name='name',
            requires=IS_URL(prepend_scheme='https'))
        >>> IS_URL(prepend_scheme='https')('abc.com')
        ('https://abc.com', None)

        INPUT(_type='text', _name='name',
            requires=IS_URL(mode='generic', allowed_schemes=['ftps', 'https'],
                prepend_scheme='https'))
        >>> IS_URL(mode='generic', allowed_schemes=['ftps', 'https'], prepend_scheme='https')('https://abc.com')
        ('https://abc.com', None)
        >>> IS_URL(mode='generic', allowed_schemes=['ftps', 'https', None], prepend_scheme='https')('abc.com')
        ('abc.com', None)

    @author: Jonathan Benn
    """

    def __init__(
        self,
        error_message="Enter a valid URL",
        mode="http",
        allowed_schemes=None,
        prepend_scheme="http",
        allowed_tlds=None,
    ):
        self.error_message = error_message
        self.mode = mode.lower()
        if self.mode not in ["generic", "http"]:
            raise SyntaxError("invalid mode '%s' in IS_URL" % self.mode)
        self.allowed_schemes = allowed_schemes
        if allowed_tlds is None:
            self.allowed_tlds = official_top_level_domains
        else:
            self.allowed_tlds = allowed_tlds

        if self.allowed_schemes:
            if prepend_scheme not in self.allowed_schemes:
                raise SyntaxError(
                    "prepend_scheme='%s' is not in allowed_schemes=%s"
                    % (prepend_scheme, self.allowed_schemes)
                )

        # if allowed_schemes is None, then we will defer testing
        # prepend_scheme's validity to a sub-method

        self.prepend_scheme = prepend_scheme

    def validate(self, value, record_id=None):
        """
        Args:
            value: a unicode or regular string, the URL to validate

        Returns:
            a (string, string) tuple, where tuple[0] is the modified
            input value and tuple[1] is either None (success!) or the
            string error_message. The input value will never be modified in the
            case of an error. However, if there is success then the input URL
            may be modified to (1) prepend a scheme, and/or (2) convert a
            non-compliant unicode URL into a compliant US-ASCII version.
        """
        if self.mode == "generic":
            subMethod = IS_GENERIC_URL(
                error_message=self.error_message,
                allowed_schemes=self.allowed_schemes,
                prepend_scheme=self.prepend_scheme,
            )
        elif self.mode == "http":
            subMethod = IS_HTTP_URL(
                error_message=self.error_message,
                allowed_schemes=self.allowed_schemes,
                prepend_scheme=self.prepend_scheme,
                allowed_tlds=self.allowed_tlds,
            )
        else:
            raise SyntaxError("invalid mode '%s' in IS_URL" % self.mode)

        if isinstance(value, unicodeT):
            try:
                value = unicode_to_ascii_url(value, self.prepend_scheme)
            except Exception as e:
                # If we are not able to convert the unicode url into a
                # US-ASCII URL, then the URL is not valid
                raise ValidationError(self.translator(self.error_message))
        return subMethod.validate(value, record_id)


class IS_TIME(Validator):
    """
    Example:
        Use as::

            INPUT(_type='text', _name='name', requires=IS_TIME())

    understands the following formats
    hh:mm:ss [am/pm]
    hh:mm [am/pm]
    hh [am/pm]

    [am/pm] is optional, ':' can be replaced by any other non-space non-digit::

        >>> IS_TIME()('21:30')
        (datetime.time(21, 30), None)
        >>> IS_TIME()('21-30')
        (datetime.time(21, 30), None)
        >>> IS_TIME()('21.30')
        (datetime.time(21, 30), None)
        >>> IS_TIME()('21:30:59')
        (datetime.time(21, 30, 59), None)
        >>> IS_TIME()('5:30')
        (datetime.time(5, 30), None)
        >>> IS_TIME()('5:30 am')
        (datetime.time(5, 30), None)
        >>> IS_TIME()('5:30 pm')
        (datetime.time(17, 30), None)
        >>> IS_TIME()('5:30 whatever')
        ('5:30 whatever', 'enter time as hh:mm:ss (seconds, am, pm optional)')
        >>> IS_TIME()('5:30 20')
        ('5:30 20', 'enter time as hh:mm:ss (seconds, am, pm optional)')
        >>> IS_TIME()('24:30')
        ('24:30', 'enter time as hh:mm:ss (seconds, am, pm optional)')
        >>> IS_TIME()('21:60')
        ('21:60', 'enter time as hh:mm:ss (seconds, am, pm optional)')
        >>> IS_TIME()('21:30::')
        ('21:30::', 'enter time as hh:mm:ss (seconds, am, pm optional)')
        >>> IS_TIME()('')
        ('', 'enter time as hh:mm:ss (seconds, am, pm optional)')ù

    """

    REGEX_TIME = "((?P<h>[0-9]+))([^0-9 ]+(?P<m>[0-9 ]+))?([^0-9ap ]+(?P<s>[0-9]*))?((?P<d>[ap]m))?"

    def __init__(
        self, error_message="Enter time as hh:mm:ss (seconds, am, pm optional)"
    ):
        self.error_message = error_message

    def validate(self, value, record_id=None):
        try:
            ivalue = value
            value = re.match(self.REGEX_TIME, value.lower())
            (h, m, s) = (int(value.group("h")), 0, 0)
            if not value.group("m") is None:
                m = int(value.group("m"))
            if not value.group("s") is None:
                s = int(value.group("s"))
            if value.group("d") == "pm" and 0 < h < 12:
                h += 12
            if value.group("d") == "am" and h == 12:
                h = 0
            if not (h in range(24) and m in range(60) and s in range(60)):
                raise ValueError(
                    "Hours or minutes or seconds are outside of allowed range"
                )
            value = datetime.time(h, m, s)
            return value
        except Exception:
            raise ValidationError(self.translator(self.error_message))


# A UTC class.
class UTC(datetime.tzinfo):
    """UTC"""

    ZERO = datetime.timedelta(0)

    def utcoffset(self, dt):
        return UTC.ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return UTC.ZERO


utc = UTC()


class IS_DATE(Validator):
    """
    Examples:
        Use as::

            INPUT(_type='text', _name='name', requires=IS_DATE())

    date has to be in the ISO8960 format YYYY-MM-DD
    """

    def __init__(self, format="%Y-%m-%d", error_message="Enter date as %(format)s"):
        self.format = self.translator(format)
        self.error_message = str(error_message)
        self.extremes = {}

    def validate(self, value, record_id=None):
        if isinstance(value, datetime.date):
            return value
        try:
            (y, m, d, hh, mm, ss, t0, t1, t2) = time.strptime(value, str(self.format))
            value = datetime.date(y, m, d)
            return value
        except:
            self.extremes.update(IS_DATETIME.nice(self.format))
            raise ValidationError(self.translator(self.error_message) % self.extremes)

    def formatter(self, value):
        if value is None or value == "":
            return None
        format = self.format
        year = value.year
        y = "%.4i" % year
        format = format.replace("%y", y[-2:])
        format = format.replace("%Y", y)
        if year < 1900:
            year = 2000
        d = datetime.date(year, value.month, value.day)
        return d.strftime(format)


class IS_DATETIME(Validator):
    """
    Examples:
        Use as::

            INPUT(_type='text', _name='name', requires=IS_DATETIME())

    datetime has to be in the ISO8960 format YYYY-MM-DD hh:mm:ss
    timezome must be None or a pytz.timezone("America/Chicago") object
    """

    isodatetime = "%Y-%m-%d %H:%M:%S"

    @staticmethod
    def nice(format):
        code = (
            ("%Y", "1963"),
            ("%y", "63"),
            ("%d", "28"),
            ("%m", "08"),
            ("%b", "Aug"),
            ("%B", "August"),
            ("%H", "14"),
            ("%I", "02"),
            ("%p", "PM"),
            ("%M", "30"),
            ("%S", "59"),
        )
        for a, b in code:
            format = format.replace(a, b)
        return dict(format=format)

    def __init__(
        self,
        format="%Y-%m-%d %H:%M:%S",
        error_message="Enter date and time as %(format)s",
        timezone=None,
    ):
        self.format = self.translator(format)
        self.error_message = str(error_message)
        self.extremes = {}
        self.timezone = timezone

    def validate(self, value, record_id=None):
        if isinstance(value, datetime.datetime):
            return value
        try:
            if self.format == self.isodatetime:
                value = value.replace("T", " ")
                if len(value) == 16:
                    value += ":00"
            (y, m, d, hh, mm, ss, t0, t1, t2) = time.strptime(value, str(self.format))
            value = datetime.datetime(y, m, d, hh, mm, ss)
            if self.timezone is not None:
                # TODO: https://github.com/web2py/web2py/issues/1094 (temporary solution)
                value = (
                    self.timezone.localize(value).astimezone(utc).replace(tzinfo=None)
                )
            return value
        except:
            self.extremes.update(IS_DATETIME.nice(self.format))
            raise ValidationError(self.translator(self.error_message) % self.extremes)

    def formatter(self, value):
        if value is None or value == "":
            return None
        format = self.format
        year = value.year
        y = "%.4i" % year
        format = format.replace("%y", y[-2:])
        format = format.replace("%Y", y)
        if year < 1900:
            year = 2000
        d = datetime.datetime(
            year, value.month, value.day, value.hour, value.minute, value.second
        )
        if self.timezone is not None:
            d = d.replace(tzinfo=utc).astimezone(self.timezone)
        return d.strftime(format)


class IS_DATE_IN_RANGE(IS_DATE):
    """
    Examples:
        Use as::

            >>> v = IS_DATE_IN_RANGE(minimum=datetime.date(2008,1,1), \
                                     maximum=datetime.date(2009,12,31), \
                                     format="%m/%d/%Y",error_message="Oops")

            >>> v('03/03/2008')
            (datetime.date(2008, 3, 3), None)

            >>> v('03/03/2010')
            ('03/03/2010', 'oops')

            >>> v(datetime.date(2008,3,3))
            (datetime.date(2008, 3, 3), None)

            >>> v(datetime.date(2010,3,3))
            (datetime.date(2010, 3, 3), 'oops')

    """

    def __init__(
        self, minimum=None, maximum=None, format="%Y-%m-%d", error_message=None
    ):
        self.minimum = minimum
        self.maximum = maximum
        if error_message is None:
            if minimum is None:
                error_message = "Enter date on or before %(max)s"
            elif maximum is None:
                error_message = "Enter date on or after %(min)s"
            else:
                error_message = "Enter date in range %(min)s %(max)s"
        IS_DATE.__init__(self, format=format, error_message=error_message)
        self.extremes = dict(min=self.formatter(minimum), max=self.formatter(maximum))

    def validate(self, value, record_id=None):
        value = IS_DATE.validate(self, value, record_id=None)
        if self.minimum and self.minimum > value:
            raise ValidationError(self.translator(self.error_message) % self.extremes)
        if self.maximum and value > self.maximum:
            raise ValidationError(self.translator(self.error_message) % self.extremes)
        return value


class IS_DATETIME_IN_RANGE(IS_DATETIME):
    """
    Examples:
        Use as::
            >>> v = IS_DATETIME_IN_RANGE(\
                    minimum=datetime.datetime(2008,1,1,12,20), \
                    maximum=datetime.datetime(2009,12,31,12,20), \
                    format="%m/%d/%Y %H:%M",error_message="Oops")
            >>> v('03/03/2008 12:40')
            (datetime.datetime(2008, 3, 3, 12, 40), None)

            >>> v('03/03/2010 10:34')
            ('03/03/2010 10:34', 'oops')

            >>> v(datetime.datetime(2008,3,3,0,0))
            (datetime.datetime(2008, 3, 3, 0, 0), None)

            >>> v(datetime.datetime(2010,3,3,0,0))
            (datetime.datetime(2010, 3, 3, 0, 0), 'oops')

    """

    def __init__(
        self,
        minimum=None,
        maximum=None,
        format="%Y-%m-%d %H:%M:%S",
        error_message=None,
        timezone=None,
    ):
        self.minimum = minimum
        self.maximum = maximum
        if error_message is None:
            if minimum is None:
                error_message = "Enter date and time on or before %(max)s"
            elif maximum is None:
                error_message = "Enter date and time on or after %(min)s"
            else:
                error_message = "Enter date and time in range %(min)s %(max)s"
        IS_DATETIME.__init__(
            self, format=format, error_message=error_message, timezone=timezone
        )
        self.extremes = dict(min=self.formatter(minimum), max=self.formatter(maximum))

    def validate(self, value, record_id=None):
        value = IS_DATETIME.validate(self, value, record_id=None)
        if self.minimum and self.minimum > value:
            raise ValidationError(self.translator(self.error_message) % self.extremes)
        if self.maximum and value > self.maximum:
            raise ValidationError(self.translator(self.error_message) % self.extremes)
        return value


class IS_LIST_OF(IS_LIST_OF_STRINGS):
    def __init__(self, other=None, minimum=None, maximum=None, error_message=None):
        self.other = other
        self.minimum = minimum
        self.maximum = maximum
        self.error_message = error_message

    def validate(self, value, record_id=None):
        value = IS_LIST_OF_STRINGS.validate(self, value)
        if self.minimum is not None and len(value) < self.minimum:
            raise ValidationError(
                self.translator(self.error_message or "Minimum length is %(min)s")
                % dict(min=self.minimum, max=self.maximum)
            )
        if self.maximum is not None and len(value) > self.maximum:
            raise ValidationError(
                self.translator(self.error_message or "Maximum length is %(max)s")
                % dict(min=self.minimum, max=self.maximum)
            )
        new_value = []
        other = self.other
        if self.other:
            if not isinstance(other, (list, tuple)):
                other = [other]
            for item in value:
                for validator in other:
                    item = validator_caller(validator, item, record_id)
                new_value.append(item)
            value = new_value
        return value


class IS_LOWER(Validator):
    """
    Converts to lowercase::

        >>> IS_LOWER()('ABC')
        ('abc', None)
        >>> IS_LOWER()('Ñ')
        ('\\xc3\\xb1', None)

    """

    def validate(self, value, record_id=None):
        cast_back = lambda x: x
        if isinstance(value, str):
            cast_back = to_native
        elif isinstance(value, bytes):
            cast_back = to_bytes
        value = to_unicode(value).lower()
        return cast_back(value)


class IS_UPPER(Validator):
    """
    Converts to uppercase::

        >>> IS_UPPER()('abc')
        ('ABC', None)
        >>> IS_UPPER()('ñ')
        ('\\xc3\\x91', None)

    """

    def validate(self, value, record_id=None):
        cast_back = lambda x: x
        if isinstance(value, str):
            cast_back = to_native
        elif isinstance(value, bytes):
            cast_back = to_bytes
        value = to_unicode(value).upper()
        return cast_back(value)


def urlify(s, maxlen=80, keep_underscores=False):
    """
    Converts incoming string to a simplified ASCII subset.
    if (keep_underscores): underscores are retained in the string
    else: underscores are translated to hyphens (default)
    """
    s = to_unicode(s)  # to unicode
    s = s.lower()  # to lowercase
    s = unicodedata.normalize("NFKD", s)  # replace special characters
    s = to_native(s, charset="ascii", errors="ignore")  # encode as ASCII
    s = re.sub(r"&\w+?;", "", s)  # strip html entities
    if keep_underscores:
        s = re.sub(r"\s+", "-", s)  # whitespace to hyphens
        s = re.sub(r"[^\w\-]", "", s)
        # strip all but alphanumeric/underscore/hyphen
    else:
        s = re.sub(r"[\s_]+", "-", s)  # whitespace & underscores to hyphens
        s = re.sub(r"[^a-z0-9\-]", "", s)  # strip all but alphanumeric/hyphen
    s = re.sub(r"[-_][-_]+", "-", s)  # collapse strings of hyphens
    s = s.strip("-")  # remove leading and trailing hyphens
    return s[:maxlen]  # enforce maximum length


class IS_SLUG(Validator):
    """
    converts arbitrary text string to a slug::

        >>> IS_SLUG()('abc123')
        ('abc123', None)
        >>> IS_SLUG()('ABC123')
        ('abc123', None)
        >>> IS_SLUG()('abc-123')
        ('abc-123', None)
        >>> IS_SLUG()('abc--123')
        ('abc-123', None)
        >>> IS_SLUG()('abc 123')
        ('abc-123', None)
        >>> IS_SLUG()('abc\t_123')
        ('abc-123', None)
        >>> IS_SLUG()('-abc-')
        ('abc', None)
        >>> IS_SLUG()('--a--b--_ -c--')
        ('a-b-c', None)
        >>> IS_SLUG()('abc&amp;123')
        ('abc123', None)
        >>> IS_SLUG()('abc&amp;123&amp;def')
        ('abc123def', None)
        >>> IS_SLUG()('ñ')
        ('n', None)
        >>> IS_SLUG(maxlen=4)('abc123')
        ('abc1', None)
        >>> IS_SLUG()('abc_123')
        ('abc-123', None)
        >>> IS_SLUG(keep_underscores=False)('abc_123')
        ('abc-123', None)
        >>> IS_SLUG(keep_underscores=True)('abc_123')
        ('abc_123', None)
        >>> IS_SLUG(check=False)('abc')
        ('abc', None)
        >>> IS_SLUG(check=True)('abc')
        ('abc', None)
        >>> IS_SLUG(check=False)('a bc')
        ('a-bc', None)
        >>> IS_SLUG(check=True)('a bc')
        ('a bc', 'must be slug')
    """

    @staticmethod
    def urlify(value, maxlen=80, keep_underscores=False):
        return urlify(value, maxlen, keep_underscores)

    def __init__(
        self,
        maxlen=80,
        check=False,
        error_message="Must be slug",
        keep_underscores=False,
    ):
        self.maxlen = maxlen
        self.check = check
        self.error_message = error_message
        self.keep_underscores = keep_underscores

    def validate(self, value, record_id=None):
        if self.check and value != urlify(value, self.maxlen, self.keep_underscores):
            raise ValidationError(self.translator(self.error_message))
        return urlify(value, self.maxlen, self.keep_underscores)


class ANY_OF(Validator):
    """
    Tests if any of the validators in a list returns successfully::

        >>> ANY_OF([IS_EMAIL(),IS_ALPHANUMERIC()])('a@b.co')
        ('a@b.co', None)
        >>> ANY_OF([IS_EMAIL(),IS_ALPHANUMERIC()])('abco')
        ('abco', None)
        >>> ANY_OF([IS_EMAIL(),IS_ALPHANUMERIC()])('@ab.co')
        ('@ab.co', 'enter only letters, numbers, and underscore')
        >>> ANY_OF([IS_ALPHANUMERIC(),IS_EMAIL()])('@ab.co')
        ('@ab.co', 'enter a valid email address')

    """

    def __init__(self, subs, error_message=None):
        self.subs = subs
        self.error_message = error_message

    def validate(self, value, record_id=None):
        for validator in self.subs:
            v, e = validator(value)
            if not e:
                return v
        raise ValidationError(e)

    def formatter(self, value):
        # Use the formatter of the first subvalidator
        # that validates the value and has a formatter
        for validator in self.subs:
            if hasattr(validator, "formatter") and validator(value)[1] is None:
                return validator.formatter(value)


class IS_EMPTY_OR(Validator):
    """
    Dummy class for testing IS_EMPTY_OR::

        >>> IS_EMPTY_OR(IS_EMAIL())('abc@def.com')
        ('abc@def.com', None)
        >>> IS_EMPTY_OR(IS_EMAIL())('   ')
        (None, None)
        >>> IS_EMPTY_OR(IS_EMAIL(), null='abc')('   ')
        ('abc', None)
        >>> IS_EMPTY_OR(IS_EMAIL(), null='abc', empty_regex='def')('def')
        ('abc', None)
        >>> IS_EMPTY_OR(IS_EMAIL())('abc')
        ('abc', 'enter a valid email address')
        >>> IS_EMPTY_OR(IS_EMAIL())(' abc ')
        ('abc', 'enter a valid email address')
    """

    def __init__(self, other, null=None, empty_regex=None):
        (self.other, self.null) = (other, null)
        if empty_regex is not None:
            self.empty_regex = re.compile(empty_regex)
        else:
            self.empty_regex = None
        if hasattr(other, "multiple"):
            self.multiple = other.multiple
        if hasattr(other, "options"):
            self.options = self._options

    def _options(self, *args, **kwargs):
        options = self.other.options(*args, **kwargs)
        if (not options or options[0][0] != "") and not self.multiple:
            options.insert(0, ("", ""))
        return options

    def set_self_id(self, id):
        if isinstance(self.other, (list, tuple)):
            for item in self.other:
                if hasattr(item, "set_self_id"):
                    item.set_self_id(id)
        else:
            if hasattr(self.other, "set_self_id"):
                self.other.set_self_id(id)

    def validate(self, value, record_id=None):
        value, empty = is_empty(value, empty_regex=self.empty_regex)
        if empty:
            return self.null
        if isinstance(self.other, (list, tuple)):
            for item in self.other:
                value = validator_caller(item, value, record_id)
            return value
        return validator_caller(self.other, value, record_id)

    def formatter(self, value):
        if hasattr(self.other, "formatter"):
            return self.other.formatter(value)
        return value


IS_NULL_OR = IS_EMPTY_OR  # for backward compatibility


class CLEANUP(Validator):
    """
    Examples:
        Use as::

            INPUT(_type='text', _name='name', requires=CLEANUP())

    removes special characters on validation
    """

    REGEX_CLEANUP = "[^\x09\x0a\x0d\x20-\x7e]"

    def __init__(self, regex=None):
        self.regex = (
            re.compile(self.REGEX_CLEANUP) if regex is None else re.compile(regex)
        )

    def validate(self, value, record_id=None):
        v = self.regex.sub("", str(value).strip())
        return v


def pbkdf2_hex(data, salt, iterations=1000, keylen=24, hashfunc=None):
    hashfunc = hashfunc or hashlib.sha1
    hmac = hashlib.pbkdf2_hmac(
        hashfunc().name, to_bytes(data), to_bytes(salt), iterations, keylen
    )
    return binascii.hexlify(hmac)


def simple_hash(text, key="", salt="", digest_alg="md5"):
    """Generate hash with the given text using the specified digest algorithm."""
    text = to_bytes(text)
    key = to_bytes(key)
    salt = to_bytes(salt)
    if not digest_alg:
        raise RuntimeError("simple_hash with digest_alg=None")
    elif not isinstance(digest_alg, str):  # manual approach
        h = digest_alg(text + key + salt)
    elif digest_alg.startswith("pbkdf2"):  # latest and coolest!
        iterations, keylen, alg = digest_alg[7:-1].split(",")
        return to_native(
            pbkdf2_hex(text, salt, int(iterations), int(keylen), get_digest(alg))
        )
    elif key:  # use hmac
        digest_alg = get_digest(digest_alg)
        h = hmac.new(key + salt, text, digest_alg)
    else:  # compatible with third party systems
        h = get_digest(digest_alg)()
        h.update(text + salt)
    return h.hexdigest()


def get_digest(value):
    """Return a hashlib digest algorithm from a string."""
    if isinstance(value, str):
        value = value.lower()
        if value not in ("md5", "sha1", "sha224", "sha256", "sha384", "sha512"):
            raise ValueError("Invalid digest algorithm: %s" % value)
        value = getattr(hashlib, value)
    return value


DIGEST_ALG_BY_SIZE = {
    128 // 4: "md5",
    160 // 4: "sha1",
    224 // 4: "sha224",
    256 // 4: "sha256",
    384 // 4: "sha384",
    512 // 4: "sha512",
}


class LazyCrypt(object):
    """
    Stores a lazy password hash
    """

    def __init__(self, crypt, password):
        """
        crypt is an instance of the CRYPT validator,
        password is the password as inserted by the user
        """
        self.crypt = crypt
        self.password = password
        self.crypted = None

    def __str__(self):
        """
        Encrypted self.password and caches it in self.crypted.
        If self.crypt.salt the output is in the format <algorithm>$<salt>$<hash>

        Try get the digest_alg from the key (if it exists)
        else assume the default digest_alg. If not key at all, set key=''

        If a salt is specified use it, if salt is True, set salt to uuid
        (this should all be backward compatible)

        Options:
        key = 'uuid'
        key = 'md5:uuid'
        key = 'sha512:uuid'
        ...
        key = 'pbkdf2(1000,64,sha512):uuid' 1000 iterations and 64 chars length
        """
        if self.crypted:
            return self.crypted
        if self.crypt.key:
            if ":" in self.crypt.key:
                digest_alg, key = self.crypt.key.split(":", 1)
            else:
                digest_alg, key = self.crypt.digest_alg, self.crypt.key
        else:
            digest_alg, key = self.crypt.digest_alg, ""
        if self.crypt.salt:
            if self.crypt.salt is True:
                salt = str(uuid.uuid4()).replace("-", "")[-16:]
            else:
                salt = self.crypt.salt
        else:
            salt = ""
        hashed = simple_hash(self.password, key, salt, digest_alg)
        self.crypted = "%s$%s$%s" % (digest_alg, salt, hashed)
        return self.crypted

    def __eq__(self, stored_password):
        """
        compares the current lazy crypted password with a stored password
        """

        # LazyCrypt objects comparison
        if isinstance(stored_password, self.__class__):
            return (self is stored_password) or (
                (self.crypt.key == stored_password.crypt.key)
                and (self.password == stored_password.password)
            )

        if self.crypt.key:
            if ":" in self.crypt.key:
                key = self.crypt.key.split(":")[1]
            else:
                key = self.crypt.key
        else:
            key = ""
        if stored_password is None:
            return False
        elif stored_password.count("$") == 2:
            (digest_alg, salt, hash) = stored_password.split("$")
            h = simple_hash(self.password, key, salt, digest_alg)
            temp_pass = "%s$%s$%s" % (digest_alg, salt, h)
        else:  # no salting
            # guess digest_alg
            digest_alg = DIGEST_ALG_BY_SIZE.get(len(stored_password), None)
            if not digest_alg:
                return False
            else:
                temp_pass = simple_hash(self.password, key, "", digest_alg)
        return temp_pass == stored_password

    def __ne__(self, other):
        return not self.__eq__(other)


class CRYPT(Validator):
    """
    Examples:
        Use as::

            INPUT(_type='text', _name='name', requires=CRYPT())

    encodes the value on validation with a digest.

    If no arguments are provided CRYPT uses the MD5 algorithm.
    If the key argument is provided the HMAC+MD5 algorithm is used.
    If the digest_alg is specified this is used to replace the
    MD5 with, for example, SHA512. The digest_alg can be
    the name of a hashlib algorithm as a string or the algorithm itself.

    min_length is the minimal password length (default 4) - IS_STRONG for serious security
    error_message is the message if password is too short

    Notice that an empty password is accepted but invalid. It will not allow login back.
    Stores junk as hashed password.

    Specify an algorithm or by default we will use sha512.

    Typical available algorithms:
      md5, sha1, sha224, sha256, sha384, sha512

    If salt, it hashes a password with a salt.
    If salt is True, this method will automatically generate one.
    Either case it returns an encrypted password string in the following format:

      <algorithm>$<salt>$<hash>

    Important: hashed password is returned as a LazyCrypt object and computed only if needed.
    The LasyCrypt object also knows how to compare itself with an existing salted password

    Supports standard algorithms

        >>> for alg in ('md5','sha1','sha256','sha384','sha512'):
        ...     print(str(CRYPT(digest_alg=alg,salt=True)('test')[0]))
        md5$...$...
        sha1$...$...
        sha256$...$...
        sha384$...$...
        sha512$...$...

    The syntax is always alg$salt$hash

    Supports for pbkdf2

        >>> alg = 'pbkdf2(1000,20,sha512)'
        >>> print(str(CRYPT(digest_alg=alg,salt=True)('test')[0]))
        pbkdf2(1000,20,sha512)$...$...

    An optional hmac_key can be specified and it is used as salt prefix

        >>> a = str(CRYPT(digest_alg='md5',key='mykey',salt=True)('test')[0])
        >>> print(a)
        md5$...$...

    Even if the algorithm changes the hash can still be validated

        >>> CRYPT(digest_alg='sha1',key='mykey',salt=True)('test')[0] == a
        True

    If no salt is specified CRYPT can guess the algorithms from length:

        >>> a = str(CRYPT(digest_alg='sha1',salt=False)('test')[0])
        >>> a
        'sha1$$a94a8fe5ccb19ba61c4c0873d391e987982fbbd3'
        >>> CRYPT(digest_alg='sha1',salt=False)('test')[0] == a
        True
        >>> CRYPT(digest_alg='sha1',salt=False)('test')[0] == a[6:]
        True
        >>> CRYPT(digest_alg='md5',salt=False)('test')[0] == a
        True
        >>> CRYPT(digest_alg='md5',salt=False)('test')[0] == a[6:]
        True
    """

    STARS = "******"

    def __init__(
        self,
        key=None,
        digest_alg="pbkdf2(1000,20,sha512)",
        min_length=0,
        error_message="Too short",
        salt=True,
        max_length=1024,
    ):
        """
        important, digest_alg='md5' is not the default hashing algorithm for
        web2py. This is only an example of usage of this function.

        The actual hash algorithm is determined from the key which is
        generated by web2py in tools.py. This defaults to hmac+sha512.
        """
        self.key = key
        self.digest_alg = digest_alg
        self.min_length = min_length
        self.max_length = max_length
        self.error_message = error_message
        self.salt = salt

    def validate(self, value, record_id=None):
        if value == self.STARS:
            return None
        v = value and str(value)[: self.max_length]
        if not v or len(v) < self.min_length:
            raise ValidationError(self.translator(self.error_message))
        if isinstance(value, LazyCrypt):
            return value
        return LazyCrypt(self, value)

    def formatter(self, value):
        return self.STARS


#  entropy calculator for IS_STRONG
#
lowerset = frozenset(b"abcdefghijklmnopqrstuvwxyz")
upperset = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ")
numberset = frozenset(b"0123456789")
sym1set = frozenset(b"!@#$%^&*() ")
sym2set = frozenset(b"~`-_=+[]{}\\|;:'\",.<>?/")
otherset = frozenset(b"".join(chr(x) if PY2 else chr(x).encode() for x in range(256)))


def calc_entropy(string):
    """calculates a simple entropy for a given string"""
    alphabet = 0  # alphabet size
    other = set()
    seen = set()
    lastset = None
    string = to_bytes(string or "")
    for c in string:
        # classify this character
        inset = None
        for cset in (lowerset, upperset, numberset, sym1set, sym2set, otherset):
            if c in cset:
                inset = cset
                break
        assert inset is not None
        # calculate effect of character on alphabet size
        if inset not in seen:
            seen.add(inset)
            alphabet += len(inset)  # credit for a new character set
        elif c not in other:
            alphabet += 1  # credit for unique characters
            other.add(c)
        if inset is not lastset:
            alphabet += 1  # credit for set transitions
            lastset = cset
    entropy = len(string) * math.log(alphabet or 1) / 0.6931471805599453  # math.log(2)
    return round(entropy, 2)


class IS_STRONG(Validator):
    """
    Examples:
        Use as::

            INPUT(_type='password', _name='passwd',
            requires=IS_STRONG(min=10, special=2, upper=2))

    enforces complexity requirements on a field

        >>> IS_STRONG(es=True)('Abcd1234')
        ('Abcd1234',
         'Must include at least 1 of the following: ~!@#$%^&*()_+-=?<>,.:;{}[]|')
        >>> IS_STRONG(es=True)('Abcd1234!')
        ('Abcd1234!', None)
        >>> IS_STRONG(es=True, entropy=1)('a')
        ('a', None)
        >>> IS_STRONG(es=True, entropy=1, min=2)('a')
        ('a', 'Minimum length is 2')
        >>> IS_STRONG(es=True, entropy=100)('abc123')
        ('abc123', 'Password too simple (32.35/100)')
        >>> IS_STRONG(es=True, entropy=100)('and')
        ('and', 'Password too simple (14.57/100)')
        >>> IS_STRONG(es=True, entropy=100)('aaa')
        ('aaa', 'Password too simple (14.42/100)')
        >>> IS_STRONG(es=True, entropy=100)('a1d')
        ('a1d', 'Password too simple (15.97/100)')
        >>> IS_STRONG(es=True, entropy=100)('añd')
        ('a\\xc3\\xb1d', 'Password too simple (31.26/10)')

    """

    def __init__(
        self,
        min=None,
        max=None,
        upper=None,
        lower=None,
        number=None,
        entropy=None,
        special=None,
        specials=r"~!@#$%^&*()_+-=?<>,.:;{}[]|",
        invalid=' "',
        error_message=None,
        es=False,
    ):
        self.entropy = entropy
        if entropy is None:
            # enforce default requirements
            self.min = 8 if min is None else min
            self.max = max  # was 20, but that doesn't make sense
            self.upper = 1 if upper is None else upper
            self.lower = 1 if lower is None else lower
            self.number = 1 if number is None else number
            self.special = 1 if special is None else special
        else:
            # by default, an entropy spec is exclusive
            self.min = min
            self.max = max
            self.upper = upper
            self.lower = lower
            self.number = number
            self.special = special
        self.specials = specials
        self.invalid = invalid
        self.error_message = error_message
        self.estring = es  # return error message as string (for doctest)

    def validate(self, value, record_id=None):
        failures = []
        if value is None:
            value = ""
        if value and len(value) == value.count("*") > 4:
            return value
        if self.entropy is not None:
            entropy = calc_entropy(value)
            if entropy < self.entropy:
                failures.append(
                    self.translator("Password too simple (%(have)s/%(need)s)")
                    % dict(have=entropy, need=self.entropy)
                )
        if isinstance(self.min, int) and self.min > 0:
            if not len(value) >= self.min:
                failures.append(self.translator("Minimum length is %s") % self.min)
        if isinstance(self.max, int) and self.max > 0:
            if not len(value) <= self.max:
                failures.append(self.translator("Maximum length is %s") % self.max)
        if isinstance(self.special, int):
            all_special = [ch in value for ch in self.specials]
            if self.special > 0:
                if not all_special.count(True) >= self.special:
                    failures.append(
                        self.translator("Must include at least %s of the following: %s")
                        % (self.special, self.specials)
                    )
            elif self.special == 0 and self.special is not False:
                if len([item for item in all_special if item]) > 0:
                    failures.append(
                        self.translator("May not contain any of the following: %s")
                        % self.specials
                    )
        if self.invalid:
            all_invalid = [ch in value for ch in self.invalid]
            if all_invalid.count(True) > 0:
                failures.append(
                    self.translator("May not contain any of the following: %s")
                    % self.invalid
                )
        if isinstance(self.upper, int):
            all_upper = re.findall("[A-Z]", value)
            if self.upper > 0:
                if not len(all_upper) >= self.upper:
                    failures.append(
                        self.translator("Must include at least %s uppercase")
                        % str(self.upper)
                    )
            elif self.upper == 0 and self.upper is not False:
                if len(all_upper) > 0:
                    failures.append(
                        self.translator("May not include any uppercase letters")
                    )
        if isinstance(self.lower, int):
            all_lower = re.findall("[a-z]", value)
            if self.lower > 0:
                if not len(all_lower) >= self.lower:
                    failures.append(
                        self.translator("Must include at least %s lowercase")
                        % str(self.lower)
                    )
            elif self.lower == 0 and self.lower is not False:
                if len(all_lower) > 0:
                    failures.append(
                        self.translator("May not include any lowercase letters")
                    )
        if isinstance(self.number, int):
            all_number = re.findall("[0-9]", value)
            if self.number > 0:
                numbers = "number"
                if self.number > 1:
                    numbers = "numbers"
                numbers = self.translator(numbers)
                if not len(all_number) >= self.number:
                    failures.append(
                        self.translator("Must include at least %s %s")
                        % (str(self.number), numbers)
                    )
            elif self.number == 0 and self.number is not False:
                if len(all_number) > 0:
                    failures.append(self.translator("May not include any numbers"))
        if len(failures) == 0:
            return value
        if not self.error_message:
            if self.estring:
                raise ValidationError("|".join(map(str, failures)))
            raise ValidationError(", ".join(failures))
        else:
            raise ValidationError(self.translator(self.error_message))


class IS_IMAGE(Validator):
    """
    Checks if file uploaded through file input was saved in one of selected
    image formats and has dimensions (width and height) within given boundaries.

    Does *not* check for maximum file size (use IS_LENGTH for that). Returns
    validation failure if no data was uploaded.

    Supported file formats: BMP, GIF, JPEG, PNG.

    Code parts taken from
    http://mail.python.org/pipermail/python-list/2007-June/617126.html

    Args:
        extensions: iterable containing allowed *lowercase* image file extensions
        ('jpg' extension of uploaded file counts as 'jpeg')
        maxsize: iterable containing maximum width and height of the image
        minsize: iterable containing minimum width and height of the image
        aspectratio: iterable containing target aspect ratio

    Use (-1, -1) as minsize to pass image size check.
    Use (-1, -1) as aspectratio to pass aspect ratio check.

    Examples:
        Check if uploaded file is in any of supported image formats:

            INPUT(_type='file', _name='name', requires=IS_IMAGE())

        Check if uploaded file is either JPEG or PNG:

            INPUT(_type='file', _name='name',
                requires=IS_IMAGE(extensions=('jpeg', 'png')))

        Check if uploaded file is PNG with maximum size of 200x200 pixels:

            INPUT(_type='file', _name='name',
                requires=IS_IMAGE(extensions=('png'), maxsize=(200, 200)))

        Check if uploaded file has a 16:9 aspect ratio:

            INPUT(_type='file', _name='name',
                requires=IS_IMAGE(aspectratio=(16, 9)))
    """

    def __init__(
        self,
        extensions=("bmp", "gif", "jpeg", "png"),
        maxsize=(10000, 10000),
        minsize=(0, 0),
        aspectratio=(-1, -1),
        error_message="Invalid image",
    ):
        self.extensions = extensions
        self.maxsize = maxsize
        self.minsize = minsize
        self.aspectratio = aspectratio
        self.error_message = error_message

    def validate(self, value, record_id=None):
        try:
            extension = value.filename.rfind(".")
            assert extension >= 0
            extension = value.filename[extension + 1 :].lower()
            if extension == "jpg":
                extension = "jpeg"
            assert extension in self.extensions
            if extension == "bmp":
                width, height = self.__bmp(value.file)
            elif extension == "gif":
                width, height = self.__gif(value.file)
            elif extension == "jpeg":
                width, height = self.__jpeg(value.file)
            elif extension == "png":
                width, height = self.__png(value.file)
            else:
                width = -1
                height = -1

            assert (
                self.minsize[0] <= width <= self.maxsize[0]
                and self.minsize[1] <= height <= self.maxsize[1]
            )

            if self.aspectratio > (-1, -1):
                target_ratio = (1.0 * self.aspectratio[1]) / self.aspectratio[0]
                actual_ratio = (1.0 * height) / width

                assert actual_ratio == target_ratio

            value.file.seek(0)
            return value
        except Exception as e:
            raise ValidationError(self.translator(self.error_message))

    def __bmp(self, stream):
        if stream.read(2) == b"BM":
            stream.read(16)
            return struct.unpack("<LL", stream.read(8))
        return (-1, -1)

    def __gif(self, stream):
        if stream.read(6) in (b"GIF87a", b"GIF89a"):
            stream = stream.read(5)
            if len(stream) == 5:
                return tuple(struct.unpack("<HHB", stream)[:-1])
        return (-1, -1)

    def __jpeg(self, stream):
        if stream.read(2) == b"\xff\xd8":
            while True:
                (marker, code, length) = struct.unpack("!BBH", stream.read(4))
                if marker != 0xFF:
                    break
                elif code >= 0xC0 and code <= 0xC3:
                    return tuple(reversed(struct.unpack("!xHH", stream.read(5))))
                else:
                    stream.read(length - 2)
        return (-1, -1)

    def __png(self, stream):
        if stream.read(8) == b"\211PNG\r\n\032\n":
            stream.read(4)
            if stream.read(4) == b"IHDR":
                return struct.unpack("!LL", stream.read(8))
        return (-1, -1)


class IS_FILE(Validator):
    """
    Checks if name and extension of file uploaded through file input matches
    given criteria.

    Does *not* ensure the file type in any way. Returns validation failure
    if no data was uploaded.

    Args:
        filename: string/compiled regex or a list of strings/regex of valid filenames
        extension: string/compiled regex or a list of strings/regex of valid extensions
        lastdot: which dot should be used as a filename / extension separator:
            True means last dot, eg. file.jpg.png -> file.jpg / png
            False means first dot, eg. file.tar.gz -> file / tar.gz
        case: 0 - keep the case, 1 - transform the string into lowercase (default),
            2 - transform the string into uppercase

    If there is no dot present, extension checks will be done against empty
    string and filename checks against whole value.

    Examples:
        Check if file has a pdf extension (case insensitive):

        INPUT(_type='file', _name='name',
                requires=IS_FILE(extension='pdf'))

        Check if file is called 'thumbnail' and has a jpg or png extension
        (case insensitive):

        INPUT(_type='file', _name='name',
                requires=IS_FILE(filename='thumbnail',
                extension=['jpg', 'png']))

        Check if file has a tar.gz extension and name starting with backup:

        INPUT(_type='file', _name='name',
                requires=IS_FILE(filename=re.compile('backup.*'),
                extension='tar.gz', lastdot=False))

        Check if file has no extension and name matching README
        (case sensitive):

            INPUT(_type='file', _name='name',
                requires=IS_FILE(filename='README',
                extension='', case=0)

    """

    def __init__(
        self,
        filename=None,
        extension=None,
        lastdot=True,
        case=1,
        error_message="Enter valid filename",
    ):
        self.filename = filename
        self.extension = extension
        self.lastdot = lastdot
        self.case = case
        self.error_message = error_message

    def match(self, value1, value2):
        if isinstance(value1, (list, tuple)):
            for v in value1:
                if self.match(v, value2):
                    return True
            return False
        elif callable(getattr(value1, "match", None)):
            return value1.match(value2)
        elif isinstance(value1, str):
            return value1 == value2

    def validate(self, value, record_id=None):
        try:
            string = value.filename
        except:
            raise ValidationError(self.translator(self.error_message))
        if self.case == 1:
            string = string.lower()
        elif self.case == 2:
            string = string.upper()
        if self.lastdot:
            dot = string.rfind(".")
        else:
            dot = string.find(".")
        if dot == -1:
            dot = len(string)
        if self.filename and not self.match(self.filename, string[:dot]):
            raise ValidationError(self.translator(self.error_message))
        elif self.extension and not self.match(self.extension, string[dot + 1 :]):
            raise ValidationError(self.translator(self.error_message))
        else:
            return value


class IS_UPLOAD_FILENAME(Validator):
    """
    For new applications, use IS_FILE().

    Checks if name and extension of file uploaded through file input matches
    given criteria.

    Does *not* ensure the file type in any way. Returns validation failure
    if no data was uploaded.

    Args:
        filename: filename (before dot) regex
        extension: extension (after dot) regex
        lastdot: which dot should be used as a filename / extension separator:
            True means last dot, eg. file.png -> file / png
            False means first dot, eg. file.tar.gz -> file / tar.gz
        case: 0 - keep the case, 1 - transform the string into lowercase (default),
            2 - transform the string into uppercase

    If there is no dot present, extension checks will be done against empty
    string and filename checks against whole value.

    Examples:
        Check if file has a pdf extension (case insensitive):

        INPUT(_type='file', _name='name',
                requires=IS_UPLOAD_FILENAME(extension='pdf'))

        Check if file has a tar.gz extension and name starting with backup:

        INPUT(_type='file', _name='name',
                requires=IS_UPLOAD_FILENAME(filename='backup.*',
                extension='tar.gz', lastdot=False))

        Check if file has no extension and name matching README
        (case sensitive):

            INPUT(_type='file', _name='name',
                requires=IS_UPLOAD_FILENAME(filename='^README$',
                extension='^$', case=0)

    """

    def __init__(
        self,
        filename=None,
        extension=None,
        lastdot=True,
        case=1,
        error_message="Enter valid filename",
    ):
        if isinstance(filename, str):
            filename = re.compile(filename)
        if isinstance(extension, str):
            extension = re.compile(extension)
        self.filename = filename
        self.extension = extension
        self.lastdot = lastdot
        self.case = case
        self.error_message = error_message

    def validate(self, value, record_id=None):
        try:
            string = value.filename
        except:
            raise ValidationError(self.translator(self.error_message))
        if self.case == 1:
            string = string.lower()
        elif self.case == 2:
            string = string.upper()
        if self.lastdot:
            dot = string.rfind(".")
        else:
            dot = string.find(".")
        if dot == -1:
            dot = len(string)
        if self.filename and not self.filename.match(string[:dot]):
            raise ValidationError(self.translator(self.error_message))
        elif self.extension and not self.extension.match(string[dot + 1 :]):
            raise ValidationError(self.translator(self.error_message))
        else:
            return value


class IS_IPV4(Validator):
    """
    Checks if field's value is an IP version 4 address in decimal form. Can
    be set to force addresses from certain range.

    IPv4 regex taken from: http://regexlib.com/REDetails.aspx?regexp_id=1411

    Args:

        minip: lowest allowed address; accepts:

            - str, eg. 192.168.0.1
            - list or tuple of octets, eg. [192, 168, 0, 1]
        maxip: highest allowed address; same as above
        invert: True to allow addresses only from outside of given range; note
            that range boundaries are not matched this way
        is_localhost: localhost address treatment:

            - None (default): indifferent
            - True (enforce): query address must match localhost address (127.0.0.1)
            - False (forbid): query address must not match localhost address
        is_private: same as above, except that query address is checked against
            two address ranges: 172.16.0.0 - 172.31.255.255 and
            192.168.0.0 - 192.168.255.255
        is_automatic: same as above, except that query address is checked against
            one address range: 169.254.0.0 - 169.254.255.255

    Minip and maxip may also be lists or tuples of addresses in all above
    forms (str, int, list / tuple), allowing setup of multiple address ranges::

        minip = (minip1, minip2, ... minipN)
                   |       |           |
                   |       |           |
        maxip = (maxip1, maxip2, ... maxipN)

    Longer iterable will be truncated to match length of shorter one.

    Examples:
        Check for valid IPv4 address:

            INPUT(_type='text', _name='name', requires=IS_IPV4())

        Check for valid IPv4 address belonging to specific range:

            INPUT(_type='text', _name='name',
                requires=IS_IPV4(minip='100.200.0.0', maxip='100.200.255.255'))

        Check for valid IPv4 address belonging to either 100.110.0.0 -
        100.110.255.255 or 200.50.0.0 - 200.50.0.255 address range:

            INPUT(_type='text', _name='name',
                requires=IS_IPV4(minip=('100.110.0.0', '200.50.0.0'),
                             maxip=('100.110.255.255', '200.50.0.255')))

        Check for valid IPv4 address belonging to private address space:

            INPUT(_type='text', _name='name', requires=IS_IPV4(is_private=True))

        Check for valid IPv4 address that is not a localhost address:

            INPUT(_type='text', _name='name', requires=IS_IPV4(is_localhost=False))

            >>> IS_IPV4()('1.2.3.4')
            ('1.2.3.4', None)
            >>> IS_IPV4()('255.255.255.255')
            ('255.255.255.255', None)
            >>> IS_IPV4()('1.2.3.4 ')
            ('1.2.3.4 ', 'enter valid IPv4 address')
            >>> IS_IPV4()('1.2.3.4.5')
            ('1.2.3.4.5', 'enter valid IPv4 address')
            >>> IS_IPV4()('123.123')
            ('123.123', 'enter valid IPv4 address')
            >>> IS_IPV4()('1111.2.3.4')
            ('1111.2.3.4', 'enter valid IPv4 address')
            >>> IS_IPV4()('0111.2.3.4')
            ('0111.2.3.4', 'enter valid IPv4 address')
            >>> IS_IPV4()('256.2.3.4')
            ('256.2.3.4', 'enter valid IPv4 address')
            >>> IS_IPV4()('300.2.3.4')
            ('300.2.3.4', 'enter valid IPv4 address')
            >>> IS_IPV4(minip='1.2.3.4', maxip='1.2.3.4')('1.2.3.4')
            ('1.2.3.4', None)
            >>> IS_IPV4(minip='1.2.3.5', maxip='1.2.3.9', error_message='Bad ip')('1.2.3.4')
            ('1.2.3.4', 'bad ip')
            >>> IS_IPV4(maxip='1.2.3.4', invert=True)('127.0.0.1')
            ('127.0.0.1', None)
            >>> IS_IPV4(maxip='1.2.3.4', invert=True)('1.2.3.4')
            ('1.2.3.4', 'enter valid IPv4 address')
            >>> IS_IPV4(is_localhost=True)('127.0.0.1')
            ('127.0.0.1', None)
            >>> IS_IPV4(is_localhost=True)('1.2.3.4')
            ('1.2.3.4', 'enter valid IPv4 address')
            >>> IS_IPV4(is_localhost=False)('127.0.0.1')
            ('127.0.0.1', 'enter valid IPv4 address')
            >>> IS_IPV4(maxip='100.0.0.0', is_localhost=True)('127.0.0.1')
            ('127.0.0.1', 'enter valid IPv4 address')

    """

    REGEX_IPV4 = re.compile(
        r"^(([1-9]?\d|1\d\d|2[0-4]\d|25[0-5])\.){3}([1-9]?\d|1\d\d|2[0-4]\d|25[0-5])$"
    )
    numbers = (16777216, 65536, 256, 1)
    localhost = 2130706433
    private = ((2886729728, 2886795263), (3232235520, 3232301055))
    automatic = (2851995648, 2852061183)

    def __init__(
        self,
        minip="0.0.0.0",
        maxip="255.255.255.255",
        invert=False,
        is_localhost=None,
        is_private=None,
        is_automatic=None,
        error_message="Enter valid IPv4 address",
    ):
        for n, value in enumerate((minip, maxip)):
            temp = []
            if isinstance(value, str):
                temp.append(value.split("."))
            elif isinstance(value, (list, tuple)):
                if (
                    len(value)
                    == len([item for item in value if isinstance(item, int)])
                    == 4
                ):
                    temp.append(value)
                else:
                    for item in value:
                        if isinstance(item, str):
                            temp.append(item.split("."))
                        elif isinstance(item, (list, tuple)):
                            temp.append(item)
            numbers = []
            for item in temp:
                number = 0
                for i, j in zip(self.numbers, item):
                    number += i * int(j)
                numbers.append(number)
            if n == 0:
                self.minip = numbers
            else:
                self.maxip = numbers
        self.invert = invert
        self.is_localhost = is_localhost
        self.is_private = is_private
        self.is_automatic = is_automatic
        self.error_message = error_message

    def validate(self, value, record_id=None):
        if re.match(self.REGEX_IPV4, value):
            number = 0
            for i, j in zip(self.numbers, value.split(".")):
                number += i * int(j)
            ok = False

            for bottom, top in zip(self.minip, self.maxip):
                if self.invert != (bottom <= number <= top):
                    ok = True

            if (
                ok
                and self.is_localhost is not None
                and self.is_localhost != (number == self.localhost)
            ):
                ok = False

            private = any(
                [
                    private_number[0] <= number <= private_number[1]
                    for private_number in self.private
                ]
            )
            if ok and self.is_private is not None and self.is_private != private:
                ok = False

            automatic = self.automatic[0] <= number <= self.automatic[1]
            if ok and self.is_automatic is not None and self.is_automatic != automatic:
                ok = False

            if ok:
                return value

        raise ValidationError(self.translator(self.error_message))


class IS_IPV6(Validator):
    """
    Checks if field's value is an IP version 6 address.

    Uses the ipaddress from the Python 3 standard library
    and its Python 2 backport (in contrib/ipaddress.py).

    Args:
        is_private: None (default): indifferent
                    True (enforce): address must be in fc00::/7 range
                    False (forbid): address must NOT be in fc00::/7 range
        is_link_local: Same as above but uses fe80::/10 range
        is_reserved: Same as above but uses IETF reserved range
        is_multicast: Same as above but uses ff00::/8 range
        is_routeable: Similar to above but enforces not private, link_local,
                      reserved or multicast
        is_6to4: Same as above but uses 2002::/16 range
        is_teredo: Same as above but uses 2001::/32 range
        subnets: value must be a member of at least one from list of subnets

    Examples:
        Check for valid IPv6 address:

            INPUT(_type='text', _name='name', requires=IS_IPV6())

        Check for valid IPv6 address is a link_local address:

            INPUT(_type='text', _name='name', requires=IS_IPV6(is_link_local=True))

        Check for valid IPv6 address that is Internet routeable:

            INPUT(_type='text', _name='name', requires=IS_IPV6(is_routeable=True))

        Check for valid IPv6 address in specified subnet:

            INPUT(_type='text', _name='name', requires=IS_IPV6(subnets=['2001::/32'])

            >>> IS_IPV6()('fe80::126c:8ffa:fe22:b3af')
            ('fe80::126c:8ffa:fe22:b3af', None)
            >>> IS_IPV6()('192.168.1.1')
            ('192.168.1.1', 'enter valid IPv6 address')
            >>> IS_IPV6(error_message='Bad ip')('192.168.1.1')
            ('192.168.1.1', 'bad ip')
            >>> IS_IPV6(is_link_local=True)('fe80::126c:8ffa:fe22:b3af')
            ('fe80::126c:8ffa:fe22:b3af', None)
            >>> IS_IPV6(is_link_local=False)('fe80::126c:8ffa:fe22:b3af')
            ('fe80::126c:8ffa:fe22:b3af', 'enter valid IPv6 address')
            >>> IS_IPV6(is_link_local=True)('2001::126c:8ffa:fe22:b3af')
            ('2001::126c:8ffa:fe22:b3af', 'enter valid IPv6 address')
            >>> IS_IPV6(is_multicast=True)('2001::126c:8ffa:fe22:b3af')
            ('2001::126c:8ffa:fe22:b3af', 'enter valid IPv6 address')
            >>> IS_IPV6(is_multicast=True)('ff00::126c:8ffa:fe22:b3af')
            ('ff00::126c:8ffa:fe22:b3af', None)
            >>> IS_IPV6(is_routeable=True)('2001::126c:8ffa:fe22:b3af')
            ('2001::126c:8ffa:fe22:b3af', None)
            >>> IS_IPV6(is_routeable=True)('ff00::126c:8ffa:fe22:b3af')
            ('ff00::126c:8ffa:fe22:b3af', 'enter valid IPv6 address')
            >>> IS_IPV6(subnets='2001::/32')('2001::8ffa:fe22:b3af')
            ('2001::8ffa:fe22:b3af', None)
            >>> IS_IPV6(subnets='fb00::/8')('2001::8ffa:fe22:b3af')
            ('2001::8ffa:fe22:b3af', 'enter valid IPv6 address')
            >>> IS_IPV6(subnets=['fc00::/8','2001::/32'])('2001::8ffa:fe22:b3af')
            ('2001::8ffa:fe22:b3af', None)
            >>> IS_IPV6(subnets='invalidsubnet')('2001::8ffa:fe22:b3af')
            ('2001::8ffa:fe22:b3af', 'invalid subnet provided')

    """

    def __init__(
        self,
        is_private=None,
        is_link_local=None,
        is_reserved=None,
        is_multicast=None,
        is_routeable=None,
        is_6to4=None,
        is_teredo=None,
        subnets=None,
        error_message="Enter valid IPv6 address",
    ):
        self.is_private = is_private
        self.is_link_local = is_link_local
        self.is_reserved = is_reserved
        self.is_multicast = is_multicast
        self.is_routeable = is_routeable
        self.is_6to4 = is_6to4
        self.is_teredo = is_teredo
        self.subnets = subnets
        self.error_message = error_message

    def validate(self, value, record_id=None):
        try:
            ip = ipaddress.IPv6Address(to_unicode(value))
            ok = True
        except ipaddress.AddressValueError:
            raise ValidationError(self.translator(self.error_message))

        if self.subnets:
            # iterate through self.subnets to see if value is a member
            ok = False
            if isinstance(self.subnets, str):
                self.subnets = [self.subnets]
            for network in self.subnets:
                try:
                    ipnet = ipaddress.IPv6Network(to_unicode(network))
                except (ipaddress.NetmaskValueError, ipaddress.AddressValueError):
                    raise ValidationError(self.translator("invalid subnet provided"))
                if ip in ipnet:
                    ok = True

        if self.is_routeable:
            self.is_private = False
            self.is_reserved = False
            self.is_multicast = False

        if ok and self.is_private is not None and self.is_private != ip.is_private:
            ok = False
        if (
            ok
            and self.is_link_local is not None
            and self.is_link_local != ip.is_link_local
        ):
            ok = False
        if ok and self.is_reserved is not None and self.is_reserved != ip.is_reserved:
            ok = False
        if (
            ok
            and self.is_multicast is not None
            and self.is_multicast != ip.is_multicast
        ):
            ok = False
        if ok and self.is_6to4 is not None and self.is_6to4 != bool(ip.sixtofour):
            ok = False
        if ok and self.is_teredo is not None and self.is_teredo != bool(ip.teredo):
            ok = False

        if ok:
            return value

        raise ValidationError(self.translator(self.error_message))


class IS_IPADDRESS(Validator):
    """
    Checks if field's value is an IP Address (v4 or v6). Can be set to force
    addresses from within a specific range. Checks are done with the correct
    IS_IPV4 and IS_IPV6 validators.

    Uses the ipaddress from the Python 3 standard library
    and its Python 2 backport (in contrib/ipaddress.py).

    Args:
        minip: lowest allowed address; accepts:
               str, eg. 192.168.0.1
               list or tuple of octets, eg. [192, 168, 0, 1]
        maxip: highest allowed address; same as above
        invert: True to allow addresses only from outside of given range; note
                that range boundaries are not matched this way

    IPv4 specific arguments:

        - is_localhost: localhost address treatment:

            - None (default): indifferent
            - True (enforce): query address must match localhost address
              (127.0.0.1)
            - False (forbid): query address must not match localhost address
        - is_private: same as above, except that query address is checked against
          two address ranges: 172.16.0.0 - 172.31.255.255 and
          192.168.0.0 - 192.168.255.255
        - is_automatic: same as above, except that query address is checked against
          one address range: 169.254.0.0 - 169.254.255.255
        - is_ipv4: either:

            - None (default): indifferent
            - True (enforce): must be an IPv4 address
            - False (forbid): must NOT be an IPv4 address

    IPv6 specific arguments:

        - is_link_local: Same as above but uses fe80::/10 range
        - is_reserved: Same as above but uses IETF reserved range
        - is_multicast: Same as above but uses ff00::/8 range
        - is_routeable: Similar to above but enforces not private, link_local,
          reserved or multicast
        - is_6to4: Same as above but uses 2002::/16 range
        - is_teredo: Same as above but uses 2001::/32 range
        - subnets: value must be a member of at least one from list of subnets
        - is_ipv6: either:

            - None (default): indifferent
            - True (enforce): must be an IPv6 address
            - False (forbid): must NOT be an IPv6 address

    Minip and maxip may also be lists or tuples of addresses in all above
    forms (str, int, list / tuple), allowing setup of multiple address ranges::

        minip = (minip1, minip2, ... minipN)
                   |       |           |
                   |       |           |
        maxip = (maxip1, maxip2, ... maxipN)

    Longer iterable will be truncated to match length of shorter one.

        >>> IS_IPADDRESS()('192.168.1.5')
        ('192.168.1.5', None)
        >>> IS_IPADDRESS(is_ipv6=False)('192.168.1.5')
        ('192.168.1.5', None)
        >>> IS_IPADDRESS()('255.255.255.255')
        ('255.255.255.255', None)
        >>> IS_IPADDRESS()('192.168.1.5 ')
        ('192.168.1.5 ', 'enter valid IP address')
        >>> IS_IPADDRESS()('192.168.1.1.5')
        ('192.168.1.1.5', 'enter valid IP address')
        >>> IS_IPADDRESS()('123.123')
        ('123.123', 'enter valid IP address')
        >>> IS_IPADDRESS()('1111.2.3.4')
        ('1111.2.3.4', 'enter valid IP address')
        >>> IS_IPADDRESS()('0111.2.3.4')
        ('0111.2.3.4', 'enter valid IP address')
        >>> IS_IPADDRESS()('256.2.3.4')
        ('256.2.3.4', 'enter valid IP address')
        >>> IS_IPADDRESS()('300.2.3.4')
        ('300.2.3.4', 'enter valid IP address')
        >>> IS_IPADDRESS(minip='192.168.1.0', maxip='192.168.1.255')('192.168.1.100')
        ('192.168.1.100', None)
        >>> IS_IPADDRESS(minip='1.2.3.5', maxip='1.2.3.9', error_message='Bad ip')('1.2.3.4')
        ('1.2.3.4', 'bad ip')
        >>> IS_IPADDRESS(maxip='1.2.3.4', invert=True)('127.0.0.1')
        ('127.0.0.1', None)
        >>> IS_IPADDRESS(maxip='192.168.1.4', invert=True)('192.168.1.4')
        ('192.168.1.4', 'enter valid IP address')
        >>> IS_IPADDRESS(is_localhost=True)('127.0.0.1')
        ('127.0.0.1', None)
        >>> IS_IPADDRESS(is_localhost=True)('192.168.1.10')
        ('192.168.1.10', 'enter valid IP address')
        >>> IS_IPADDRESS(is_localhost=False)('127.0.0.1')
        ('127.0.0.1', 'enter valid IP address')
        >>> IS_IPADDRESS(maxip='100.0.0.0', is_localhost=True)('127.0.0.1')
        ('127.0.0.1', 'enter valid IP address')

        >>> IS_IPADDRESS()('fe80::126c:8ffa:fe22:b3af')
        ('fe80::126c:8ffa:fe22:b3af', None)
        >>> IS_IPADDRESS(is_ipv4=False)('fe80::126c:8ffa:fe22:b3af')
        ('fe80::126c:8ffa:fe22:b3af', None)
        >>> IS_IPADDRESS()('fe80::126c:8ffa:fe22:b3af  ')
        ('fe80::126c:8ffa:fe22:b3af  ', 'enter valid IP address')
        >>> IS_IPADDRESS(is_ipv4=True)('fe80::126c:8ffa:fe22:b3af')
        ('fe80::126c:8ffa:fe22:b3af', 'enter valid IP address')
        >>> IS_IPADDRESS(is_ipv6=True)('192.168.1.1')
        ('192.168.1.1', 'enter valid IP address')
        >>> IS_IPADDRESS(is_ipv6=True, error_message='Bad ip')('192.168.1.1')
        ('192.168.1.1', 'bad ip')
        >>> IS_IPADDRESS(is_link_local=True)('fe80::126c:8ffa:fe22:b3af')
        ('fe80::126c:8ffa:fe22:b3af', None)
        >>> IS_IPADDRESS(is_link_local=False)('fe80::126c:8ffa:fe22:b3af')
        ('fe80::126c:8ffa:fe22:b3af', 'enter valid IP address')
        >>> IS_IPADDRESS(is_link_local=True)('2001::126c:8ffa:fe22:b3af')
        ('2001::126c:8ffa:fe22:b3af', 'enter valid IP address')
        >>> IS_IPADDRESS(is_multicast=True)('2001::126c:8ffa:fe22:b3af')
        ('2001::126c:8ffa:fe22:b3af', 'enter valid IP address')
        >>> IS_IPADDRESS(is_multicast=True)('ff00::126c:8ffa:fe22:b3af')
        ('ff00::126c:8ffa:fe22:b3af', None)
        >>> IS_IPADDRESS(is_routeable=True)('2001::126c:8ffa:fe22:b3af')
        ('2001::126c:8ffa:fe22:b3af', None)
        >>> IS_IPADDRESS(is_routeable=True)('ff00::126c:8ffa:fe22:b3af')
        ('ff00::126c:8ffa:fe22:b3af', 'enter valid IP address')
        >>> IS_IPADDRESS(subnets='2001::/32')('2001::8ffa:fe22:b3af')
        ('2001::8ffa:fe22:b3af', None)
        >>> IS_IPADDRESS(subnets='fb00::/8')('2001::8ffa:fe22:b3af')
        ('2001::8ffa:fe22:b3af', 'enter valid IP address')
        >>> IS_IPADDRESS(subnets=['fc00::/8','2001::/32'])('2001::8ffa:fe22:b3af')
        ('2001::8ffa:fe22:b3af', None)
        >>> IS_IPADDRESS(subnets='invalidsubnet')('2001::8ffa:fe22:b3af')
        ('2001::8ffa:fe22:b3af', 'invalid subnet provided')
    """

    def __init__(
        self,
        minip="0.0.0.0",
        maxip="255.255.255.255",
        invert=False,
        is_localhost=None,
        is_private=None,
        is_automatic=None,
        is_ipv4=None,
        is_link_local=None,
        is_reserved=None,
        is_multicast=None,
        is_routeable=None,
        is_6to4=None,
        is_teredo=None,
        subnets=None,
        is_ipv6=None,
        error_message="Enter valid IP address",
    ):
        self.minip = (minip,)
        self.maxip = (maxip,)
        self.invert = invert
        self.is_localhost = is_localhost
        self.is_private = is_private
        self.is_automatic = is_automatic
        self.is_ipv4 = is_ipv4 or is_ipv6 is False
        self.is_private = is_private
        self.is_link_local = is_link_local
        self.is_reserved = is_reserved
        self.is_multicast = is_multicast
        self.is_routeable = is_routeable
        self.is_6to4 = is_6to4
        self.is_teredo = is_teredo
        self.subnets = subnets
        self.is_ipv6 = is_ipv6 or is_ipv4 is False
        self.error_message = error_message

    def validate(self, value, record_id=None):
        IPAddress = ipaddress.ip_address
        IPv6Address = ipaddress.IPv6Address
        IPv4Address = ipaddress.IPv4Address

        try:
            ip = IPAddress(to_unicode(value))
        except ValueError:
            raise ValidationError(self.translator(self.error_message))

        if self.is_ipv4 and isinstance(ip, IPv6Address):
            raise ValidationError(self.translator(self.error_message))
        elif self.is_ipv6 and isinstance(ip, IPv4Address):
            raise ValidationError(self.translator(self.error_message))
        elif self.is_ipv4 or isinstance(ip, IPv4Address):
            return IS_IPV4(
                minip=self.minip,
                maxip=self.maxip,
                invert=self.invert,
                is_localhost=self.is_localhost,
                is_private=self.is_private,
                is_automatic=self.is_automatic,
                error_message=self.error_message,
            ).validate(value, record_id)
        elif self.is_ipv6 or isinstance(ip, IPv6Address):
            return IS_IPV6(
                is_private=self.is_private,
                is_link_local=self.is_link_local,
                is_reserved=self.is_reserved,
                is_multicast=self.is_multicast,
                is_routeable=self.is_routeable,
                is_6to4=self.is_6to4,
                is_teredo=self.is_teredo,
                subnets=self.subnets,
                error_message=self.error_message,
            ).validate(value, record_id)
        else:
            raise ValidationError(self.translator(self.error_message))
