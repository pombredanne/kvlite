﻿#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#   Simple key-value datastore

#   some ideas taked from PyMongo interface http://api.mongodb.org/python/current/index.html
#   kvlite2 tutorial http://code.google.com/p/kvlite/wiki/kvlite2
#
__author__ = 'Andrey Usov <https://github.com/ownport/kvlite>'
__version__ = '0.5.1'
__license__ = """
Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice,
  this list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 'AS IS'
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE."""

import os
import sys
import json
import zlib
import uuid
import types
import string
import random
import sqlite3
import binascii
import cPickle as pickle

__all__ = [
    'open', 'remove', 'get_uuid', 'dict2flat', 'docs_struct',
    'BaseCollection', 'BaseCollectionManager',
    'CollectionManager',
    'CompressedJsonSerializer', 'cPickleSerializer',
    'MysqlCollection', 'SqliteCollection',
    'MysqlCollectionManager', 'SqliteCollectionManager',
]

try:
    import MySQLdb
except ImportError:
    pass

# ITEMS_PER_REQUEST is used in Collection._get_many()
ITEMS_PER_REQUEST = 100

# the length of key 
_KEY_LENGTH = 40
    
SUPPORTED_BACKENDS = ['mysql', 'sqlite', ]

SUPPORTED_VALUE_TYPES = {
    types.NoneType: {
        'name': 'none_type',
    },
    types.BooleanType: {
        'name': 'boolean_type',
    },
    types.IntType: {
        'name': 'integer_type',
    },
    types.LongType: {
        'name': 'long_type',
    },
    types.FloatType: {
        'name': 'float_type',
    },
    types.ComplexType: {
        'name': 'complex_type',
    },
    types.StringType: {
        'name': 'string_type',
    },
    types.UnicodeType: {
        'name': 'unicode_type',
    },
    types.TupleType: {
        'name': 'tuple_type',
    },
    types.ListType: {
        'name': 'list_type',
    },
    types.DictType: {
        'name': 'dict_type',
    },
}

# -----------------------------------------------------------------
# cPickleSerializer class
# -----------------------------------------------------------------

class cPickleSerializer(object):
    ''' cPickleSerializer 
    '''

    @staticmethod
    def dumps(v):
        ''' dumps value 
        '''
        if isinstance(v, unicode):
            v = str(v)
        return pickle.dumps(v)

    @staticmethod
    def loads(v):
        ''' loads value  
        '''
        return pickle.loads(v)

# -----------------------------------------------------------------
# CompressedJsonSerializer class
# -----------------------------------------------------------------

class CompressedJsonSerializer(object):
    ''' CompressedJsonSerializer 
    '''

    @staticmethod
    def dumps(v):
        ''' dumps value 
        '''
        return zlib.compress(json.dumps(v))

    @staticmethod
    def loads(v):
        ''' loads value  
        '''
        return json.loads(zlib.decompress(v))

# -----------------------------------------------------------------
# SERIALIZERS 
# -----------------------------------------------------------------
''' the name of class or module to serialize msgs with, must have methods or 
functions named ``dumps`` and ``loads``, cPickleSerializer is the default
'''
SERIALIZERS = {
    'pickle': cPickleSerializer,
    'completed_json': CompressedJsonSerializer,
}


# -----------------------------------------------------------------
# KVLite utils
# -----------------------------------------------------------------
def open(uri, serializer_name='pickle'):
    ''' open collection by URI, 
    
    if collection does not exist kvlite will try to create it
        
    serializer_name: see details in SERIALIZERS section

    returns MysqlCollection or SqliteCollection object in case of successful 
    opening or creation new collection    
    '''
    # TODO use `None` for serializer to store messages in plain text, suitable for strings, integers, etc

    manager = CollectionManager(uri)
    params = manager.parse_uri(uri)
    if params['collection'] not in manager.collections():
        manager.create(params['collection'])
        
    collection = manager.collection_class(manager.connection, 
                                        params['collection'], 
                                        SERIALIZERS[serializer_name])
    if collection.meta is None:
        collection.meta = {
            'name': params['collection'],
            'serializer': serializer_name,
            'kvlite-version': __version__,
        } 
    return collection

def remove(uri):
    ''' remove collection by URI
    ''' 
    manager = CollectionManager(uri)
    params = manager.parse_uri(uri)
    if params['collection'] in manager.collections():
        manager.remove(params['collection'])

def copy(source, target):
    ''' copy data from source to target
    
    where
        source = Collection object to source
        target = Collection object to target
    '''
    if not isinstance(source, (MysqlCollection, SqliteCollection)):
        raise RuntimeError('The source should be MysqlCollection or SqliteCollection object, not %s', type(source))
    if not isinstance(target, (MysqlCollection, SqliteCollection)):
        raise RuntimeError('The source should be MysqlCollection or SqliteCollection object, not %s', type(target))
    
    data = [kv for kv in source]
    target.put(data)
    target.commit()

def get_uuid(amount=100):
    ''' return UUIDs 
    '''
    
    uuids = list()
    for _ in xrange(amount):
        u = str(uuid.uuid4()).replace('-', '')
        uuids.append(("%040s" % u).replace(' ','0'))
    return uuids

def dict2flat(root_name, source, removeEmptyFields=False):
    ''' returns a simplified "flat" form of the complex hierarchical dictionary 
    '''
    
    def is_simple_elements(source):
        ''' check if the source contains simple element types,
        not lists, tuples, dicts
        '''
        for i in source:
            if isinstance(i, (list, tuple, dict)):
                return False
        return True
    
    flat_dict = {}
    if isinstance(source, (list, tuple)):
        if not is_simple_elements(source):
            for i,e in enumerate(source):
                new_root_name = "%s[%d]" % (root_name,i)
                for k,v in dict2flat(new_root_name,e).items():
                    flat_dict[k] = v
        else:
            flat_dict[root_name] = source
    elif isinstance(source, dict):
        for k,v in source.items():
            if root_name:
                new_root_name = "%s.%s" % (root_name, k)
            else:
                new_root_name = "%s" % k
            for kk, vv in dict2flat(new_root_name,v).items():
                flat_dict[kk] = vv
    else:
        if source is not None:
            flat_dict[root_name] = source
    return flat_dict

def docs_struct(documents):
    ''' returns structure for all documents in the list 
    '''
    
    def seq_struct(items):
        struct = dict()
        for item in items:
            item_type = SUPPORTED_VALUE_TYPES[type(item)]['name']
            
            if item_type in struct:
                struct[item_type] += 1
            else:
                struct[item_type] = 1
        return struct
    
    def doc_struct(document):
        struct = list()
        for name, value in dict2flat('', document).items():
            field = dict()
            field['name'] = name
            field_type = SUPPORTED_VALUE_TYPES[type(value)]['name']
            field['types'] = { field_type: 1 }
            
            if field_type == 'list_type':
                field['types'][field_type] = seq_struct(value)
            if field_type == 'tuple_type':
                field['types'][field_type] = seq_struct(value)
            struct.append(field)
        return struct
    
    struct = list()
    total_documents = 0
    for k,document in documents:
        total_documents += 1

        for s in doc_struct(document):
            names = [f['name'] for f in struct]
            if s['name'] in names:
                idx = names.index(s['name'])
                for t in s['types']:
                    if t in struct[idx]['types']:
                        if t == 'list_type':
                            list_types = set(s['types'][t]) | set(struct[idx]['types'][t])
                            for n in list_types:
                                struct[idx]['types'][t][n] = struct[idx]['types'][t].get(n, 0) + s['types'][t].get(n,0)
                        else:
                            struct[idx]['types'][t] += s['types'][t]
                    else:
                        struct[idx]['types'][t] = s['types'][t]
            else:
                struct.append(s)
    return { 
        'total_documents': total_documents,
        'structure': struct,
    }

def tmp_name(size = 10):
    ''' generate temporary collection name 
    '''
    name = ''.join(random.choice(string.ascii_lowercase) for x in range(int(size * .8)))
    name += ''.join(random.choice(string.digits) for x in range(int(size * .2))) 
    return name
    
# -----------------------------------------------------------------
# CollectionManager class
# -----------------------------------------------------------------
class CollectionManager(object):
    ''' Collection Manager
    '''
    
    def __init__(self, uri):
    
        self.backend_manager = None
        
        if not uri or uri.find('://') <= 0:
            raise RuntimeError('Incorrect URI definition: {}'.format(uri))
        backend, rest_uri = uri.split('://')
        if backend in SUPPORTED_BACKENDS:
            if backend == 'mysql':
                self.backend_manager = MysqlCollectionManager(uri)
            elif backend == 'sqlite':
                self.backend_manager = SqliteCollectionManager(uri)
        else:
            raise RuntimeError('Unknown backend: {}'.format(backend))

    def parse_uri(self, uri):
        ''' parse_uri 
        '''
        return self.backend_manager.parse_uri(uri)

    def create(self, name):
        ''' create collection 
        '''
        self.backend_manager.create(name)
    
    @property
    def collection_class(self):
        ''' return object MysqlCollection or SqliteCollection 
        '''
        return self.backend_manager.collection_class
    
    @property
    def connection(self):
        ''' return reference to backend connection 
        '''
        return self.backend_manager.connection
    
    def collections(self):
        ''' return list of collections 
        '''
        return self.backend_manager.collections()
    
    def remove(self, name):
        ''' remove collection 
        '''
        self.backend_manager.remove(name)

# -----------------------------------------------------------------
# BaseCollectionManager class
# -----------------------------------------------------------------
class BaseCollectionManager(object):

    def __init__(self, connection):
        ''' init 
        '''
        self._conn = connection
        self._cursor = self._conn.cursor()

    @property
    def connection(self):
        ''' return connection 
        '''
        return self._conn
    
    def _collections(self, sql):
        ''' return collection list
        '''
        self._cursor.execute(sql)
        return [t[0] for t in self._cursor.fetchall()]

    def _create(self, sql_create_table, name):
        ''' create collection by name 
        '''
        self._cursor.execute(sql_create_table % name)
        self._conn.commit()

    def remove(self, name):
        ''' remove collection 
        '''
        if name in self.collections():
            self._cursor.execute('DROP TABLE %s;' % name)
            self._conn.commit()
        else:
            raise RuntimeError('No collection with name: {}'.format(name))

    def close(self):
        ''' close connection to database 
        '''
        try:
            self._conn.close()
        except:
            pass

# -----------------------------------------------------------------
# MysqlCollectionManager class
# -----------------------------------------------------------------
class MysqlCollectionManager(BaseCollectionManager):
    ''' MysqlCollectionManager 
    '''    
    def __init__(self, uri):
        
        params = self.parse_uri(uri) 
        
        try:
            self._conn = MySQLdb.connect(
                                host=params['host'], port = params['port'], 
                                user=params['username'], passwd=params['password'], 
                                db=params['db'])
        except MySQLdb.OperationalError,err:
            raise RuntimeError(err)
        
        super(MysqlCollectionManager, self).__init__(self._conn)

    @staticmethod
    def parse_uri(uri):
        '''parse URI 
        
        return driver, user, password, host, port, database, table
        '''
        parsed_uri = dict()
        parsed_uri['backend'], rest_uri = uri.split('://', 1)
        parsed_uri['username'], rest_uri = rest_uri.split(':', 1)
        parsed_uri['password'], rest_uri = rest_uri.split('@', 1)
        
        if ':' in rest_uri:
            parsed_uri['host'], rest_uri = rest_uri.split(':', 1)
            parsed_uri['port'], rest_uri = rest_uri.split('/', 1)
            parsed_uri['port'] = int(parsed_uri['port'])
        else:
            parsed_uri['host'], rest_uri = rest_uri.split('/')
            parsed_uri['port'] = 3306

        if '.' in rest_uri:
            parsed_uri['db'], parsed_uri['collection'] = rest_uri.split('.', 1)     
        else:
            parsed_uri['db'] = rest_uri
            parsed_uri['collection'] = None
        return parsed_uri
        
    def create(self, name):
        ''' create collection 
        '''
        SQL_CREATE_TABLE = '''CREATE TABLE IF NOT EXISTS %s (
                                __rowid__ INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                                k BINARY(20) NOT NULL, 
                                v MEDIUMBLOB,
                                UNIQUE KEY (k) ) ENGINE=InnoDB DEFAULT CHARSET utf8;'''
                                
        self._create(SQL_CREATE_TABLE, name)

    @property
    def collection_class(self):
        ''' return MysqlCollection object
        '''
        return MysqlCollection
    
    def collections(self):
        ''' return collection list
        '''
        return self._collections('SHOW TABLES;')

# -----------------------------------------------------------------
# SqliteCollectionManager class
# -----------------------------------------------------------------
class SqliteCollectionManager(BaseCollectionManager):
    ''' Sqlite Collection Manager 
    '''
    def __init__(self, uri):
        
        params = self.parse_uri(uri) 
        
        self._conn = sqlite3.connect(params['db'])       
        self._conn.text_factory = str

        super(SqliteCollectionManager, self).__init__(self._conn)

    @staticmethod
    def parse_uri(uri):
        ''' parse URI 
        
        return driver, database, collection
        '''
        parsed_uri = dict()
        parsed_uri['backend'], rest_uri = uri.split('://', 1)
        if ':' in rest_uri:
            parsed_uri['db'], parsed_uri['collection'] = rest_uri.split(':',1)
        else:
            parsed_uri['db'] = rest_uri
            parsed_uri['collection'] = None
        if parsed_uri['db'] == 'memory':
            parsed_uri['db'] = ':memory:'
        return parsed_uri

    @property
    def collection_class(self):
        ''' return SqliteCollection object
        '''
        return SqliteCollection

    def collections(self):
        ''' return collection list
        '''
        return self._collections('SELECT name FROM sqlite_master WHERE type="table";')

    def create(self, name):
        ''' create collection 
        '''
        SQL_CREATE_TABLE = '''CREATE TABLE IF NOT EXISTS %s (
                                k NOT NULL, v, UNIQUE (k) );'''
        self._create(SQL_CREATE_TABLE, name)

# -----------------------------------------------------------------
# BaseCollection class
# -----------------------------------------------------------------
class BaseCollection(object):
    ''' BaseCollection
    '''
    def __init__(self, connection, collection_name, serializer=cPickleSerializer):
        ''' __init__
        '''
        self._conn = connection
        self._cursor = self._conn.cursor()
        self._collection = collection_name
        self._serializer = serializer

        self._uuid_cache = list()
        self._ZEROS_KEY = self.prepare_key(0)

    @staticmethod
    def prepare_key(key):
        ''' prepare key
        
        - convert key to string if it's integer
        - zero fill key
        '''
        _key = key
        if isinstance(_key, int):
            _key = str(key)
        if len(_key) > _KEY_LENGTH:
            raise RuntimeError('The length of key is more than %d bytes' % (_KEY_LENGTH))
        return _key.zfill(_KEY_LENGTH)
    
    def prepare_kv(self, k, v, backend='sqlite'):
        ''' prepare key/value pair before insert to database
        
        backend can be 'mysql' or 'sqlite'
        '''
        
        k = self.prepare_key(k)
        if k == self._ZEROS_KEY:
            v = cPickleSerializer.dumps(v)
        else:
            v = self._serializer.dumps(v)
        
        if backend == 'sqlite':
            return (k,v) 
        elif backend == 'mysql':
            return (binascii.a2b_hex(k), v, v)
        else:
            raise RuntimeError('Uknown backend: %s' % backend)
                
    @property
    def meta(self):
        ''' return meta information from zero's key
        '''
        return self.get({'_key': self._ZEROS_KEY})[1]

    @meta.setter
    def meta(self, info):
        ''' set metadata to zero'skey
        '''
        if not isinstance(info, dict):
            raise RuntimeError('Metadata should be dictionary')
        self.put(self._ZEROS_KEY, info)

    @property
    def count(self):
        ''' return amount of documents in collection
        '''
        SQL = 'SELECT count(*) FROM %s' % self._collection
        self._cursor.execute(SQL + ' WHERE k <> ?;', (self._ZEROS_KEY,))
        return int(self._cursor.fetchone()[0])

    def get(self, criteria=None, offset=None, limit=ITEMS_PER_REQUEST):
        ''' returns documents selected from collection by criteria.
        
        - If the criteria is not defined, get() returns all documents.
        - Hint: the combination `offset` and `limit` paramters can be 
        used for pagination
        
        offset  - starts with this position in database
        limit   - how many document will be returned
        '''
        if criteria is None:
            if offset >=0 and limit > 0:
                return self._get_paged(offset=offset, limit=limit)
            else:
                return self._get_all()
            
        if not isinstance(criteria, dict):
            raise RuntimeError('Incorrect criteria format')
        
        if '_key' in criteria:
            if isinstance(criteria['_key'], (str, unicode)):
                return self._get_one(self.prepare_key(criteria['_key']))
            elif isinstance(criteria['_key'], (list, tuple)):
                criteria['_key'] = map(self.prepare_key, criteria['_key'])
                return self._get_many(*criteria['_key'])

    def commit(self):
        ''' commit
        '''
        self._conn.commit()

    def close(self):
        ''' close connection to database 
        '''
        try:
            self._conn.close()
        except:
            pass
    
# -----------------------------------------------------------------
# MysqlCollection class
# -----------------------------------------------------------------
class MysqlCollection(BaseCollection):
    ''' Mysql Connection 
    '''
    def get_uuid(self, amount=100):
        ''' 
        return one uuid. 
        
        By `amount` argument you can define how many UUIDs will be generated and 
        stored in cache if it's empty. By default 100 UUIDs will be generated.
        
        For mysql connection, the generation of UUIDs is more fast than kvlite.get_uuid()
        '''

        if not self._uuid_cache:
            self._cursor.execute('SELECT %s;' % ','.join(['uuid()' for _ in range(int(amount))]))
            for uuid in self._cursor.fetchone():
                u = uuid.split('-')
                u.reverse()
                u = ("%040s" % ''.join(u)).replace(' ','0')
                self._uuid_cache.append(u)
        return self._uuid_cache.pop()

    def _get_one(self, _key):
        ''' return document by _key 
        '''        
        _key = self.prepare_key(_key)
        SQL = 'SELECT k,v FROM %s WHERE k = ' % self._collection
        try:
            self._cursor.execute(SQL + "%s", binascii.a2b_hex(_key))
        except Exception, err:
            raise RuntimeError(err)
        result = self._cursor.fetchone()
        if result:
            try:
                v = self._serializer.loads(result[1])
            except Exception, err:
                raise RuntimeError('key %s, %s' % (_key, err))
            return (binascii.b2a_hex(result[0]), v)
        else:
            return (None, None)

    def _get_many(self, *_keys):
        ''' return docs by keys 
        '''        
        if _keys:
            if isinstance(_keys, (list, tuple)):
                bin_keys = [binascii.a2b_hex(k) for k in _keys if k <> self._ZEROS_KEY]
                SQL_SELECT_MANY = 'SELECT k,v FROM {} WHERE k IN ({})'
                SQL_SELECT_MANY = SQL_SELECT_MANY.format(self._collection,','.join(['%s']*len(bin_keys)));
                self._cursor.execute(SQL_SELECT_MANY, tuple(bin_keys))
                result = self._cursor.fetchall()
                if not result:
                    return
                for r in result:
                    k = binascii.b2a_hex(r[0])
                    try:
                        v = self._serializer.loads(r[1])
                    except Exception, err:
                        raise RuntimeError('key %s, %s' % (k, err))
                    yield (k, v)

    def _get_all(self):
        ''' return all docs 
        '''
        rowid = 0
        while True:
            SQL_SELECT_ALL = 'SELECT __rowid__, k,v FROM %s WHERE __rowid__ > %d LIMIT %s;'
            SQL_SELECT_ALL %=  (self._collection, rowid, ITEMS_PER_REQUEST)
            self._cursor.execute(SQL_SELECT_ALL)
            result = self._cursor.fetchall()
            if not result:
                break
            for r in result:
                rowid = r[0]
                k = binascii.b2a_hex(r[1])
                if k == self._ZEROS_KEY:
                    continue
                try:
                    v = self._serializer.loads(r[2])
                except Exception, err:
                    raise RuntimeError('key %s, %s' % (k, err))
                yield (k, v)
                
    __iter__ = _get_all

    def _get_paged(self, offset=None, limit=ITEMS_PER_REQUEST):
        ''' return docs by offset and limit
        
        offset and limit are used for pagination, for details 
        see BaseCollection.get()
        '''
        
        if not offset and not limit:
            return
        
        SQL_SELECT_MANY = 'SELECT k,v FROM %s WHERE k <> ? LIMIT %d, %d ;'
        SQL_SELECT_MANY %= (self._collection, int(offset), int(limit))
        self._cursor.execute(SQL_SELECT_MANY, (self._ZEROS_KEY, ))
        result = self._cursor.fetchall()
        if not result:
            return
        for r in result:
            k = binascii.b2a_hex(r[0])
            if k == self._ZEROS_KEY:
                continue
            try:
                v = self._serializer.loads(r[1])
            except Exception, err:
                raise RuntimeError('key %s, %s' % (k, err))
            yield (k, v)


    def put(self, k, v):
        ''' put document in collection 
        '''        
        kv_insert = list()
        if not isinstance(kv, (list,tuple)):
            raise RuntimeError('key/value should be packed in the list or tuple')
        
        # put([(k1,v1), (k2,v2)])
        if len(kv) == 1 \
            and isinstance(kv[0], (list, tuple)):
            
            kv_insert = [self.prepare_kv(*kvs, backend='mysql') for kvs in kv[0]]

        # put(k,v)
        elif len(kv) == 2 \
            and not isinstance(kv[0], (list, tuple)) \
            and not isinstance(kv[1], (list, tuple)):
            
            kv_insert.append(self.prepare_kv(*kv, backend='mysql'))

        else:
            raise RuntimeError('Incorrect format of key/values, %s' % kv)

        k = self.prepare_key(k)
        SQL_INSERT = 'INSERT INTO %s (k,v) ' % self._collection
        SQL_INSERT += 'VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=%s;;'

        self._cursor.execute(SQL_INSERT, kv_insert)

    def delete(self, k):
        ''' delete document by k 
        '''
        _key = self.prepare_key(k)
        if _key == self._ZEROS_KEY:
            raise RuntimeError('Metadata cannot be deleted')
        SQL_DELETE = '''DELETE FROM %s WHERE k = ''' % self._collection
        self._cursor.execute(SQL_DELETE + "%s;", binascii.a2b_hex(_key))

# -----------------------------------------------------------------
# SqliteCollection class
# -----------------------------------------------------------------
class SqliteCollection(BaseCollection):
    ''' Sqlite Collection
    '''    
    def get_uuid(self):
        ''' return id based on uuid 
        '''
        if not self._uuid_cache:
            for uuid in get_uuid():
                self._uuid_cache.append(uuid)
        return self._uuid_cache.pop()

    def put(self, *kv):
        ''' put document(s) in collection 
        
        kv is list of key/value
        
        put(k,v) or put([(k1,v1), (k2,v2)])
        '''
        kv_insert = list()
        if not isinstance(kv, (list,tuple)):
            raise RuntimeError('key/value should be packed in the list or tuple')
        
        # put([(k1,v1), (k2,v2)])
        if len(kv) == 1 \
            and isinstance(kv[0], (list, tuple)):
            
            kv_insert = [self.prepare_kv(*kvs, backend='sqlite') for kvs in kv[0]]

        # put(k,v)
        elif len(kv) == 2 \
            and not isinstance(kv[0], (list, tuple)) \
            and not isinstance(kv[1], (list, tuple)):
            
            kv_insert.append(self.prepare_kv(*kv, backend='sqlite'))

        else:
            raise RuntimeError('Incorrect format of key/values, %s' % kv)

        SQL_INSERT = 'INSERT OR REPLACE INTO %s (k,v) ' % self._collection
        SQL_INSERT += 'VALUES (?,?)'
        self._cursor.executemany(SQL_INSERT, kv_insert)

    def _get_one(self, _key):
        ''' return document by _key 
        '''        
        _key = self.prepare_key(_key)
        SQL = 'SELECT k,v FROM %s WHERE k = ?;' % self._collection
        try:
            self._cursor.execute(SQL, (_key,))
        except Exception, err:
            raise RuntimeError(err)
        result = self._cursor.fetchone()
        if result:
            try:
                if _key == self._ZEROS_KEY:
                    v = cPickleSerializer.loads(result[1])
                else:
                    v = self._serializer.loads(result[1])
            except Exception, err:
                raise RuntimeError('key %s, %s' % (_key, err))
            return (result[0], v)
        else:
            return (None, None)

    def _get_many(self, *_keys):
        ''' return docs by keys or all docs if keys are not defined 
        '''        
        if _keys:
            if isinstance(_keys, (list, tuple)):
                # check if keys are even
                for key in _keys:
                    if key == self._ZEROS_KEY:
                        continue
                    key = self.prepare_key(key)
                SQL_SELECT_MANY = 'SELECT k,v FROM %s WHERE k IN ({seq})';
                SQL_SELECT_MANY %= (self._collection)
                SQL_SELECT_MANY = SQL_SELECT_MANY.format(seq=','.join(['?']*len(_keys)))
                self._cursor.execute(SQL_SELECT_MANY, _keys)
                result = self._cursor.fetchall()
                if not result:
                    return
                for r in result:
                    k = r[0]
                    if k == self._ZEROS_KEY:
                        continue
                    try:
                        v = self._serializer.loads(r[1])
                    except Exception, err:
                        raise RuntimeError('key %s, %s' % (k, err))
                    yield (k, v)

    def _get_all(self):
        ''' return all docs 
        '''        
        rowid = 0
        while True:
            SQL_SELECT_MANY = 'SELECT rowid, k,v FROM %s WHERE rowid > %d LIMIT %d ;'
            SQL_SELECT_MANY %= (self._collection, rowid, ITEMS_PER_REQUEST)
            self._cursor.execute(SQL_SELECT_MANY)
            result = self._cursor.fetchall()
            if not result:
                break
            for r in result:
                rowid = r[0]
                k = r[1]
                if k == self._ZEROS_KEY:
                    continue
                try:
                    v = self._serializer.loads(r[2])
                except Exception, err:
                    raise RuntimeError('key %s, %s' % (k, err))
                yield (k, v)

    __iter__ = _get_all

    def _get_paged(self, offset=None, limit=ITEMS_PER_REQUEST):
        ''' return docs by offset and limit
        
        offset and limit are used for pagination, for details 
        see BaseCollection.get()
        '''        
        if not offset and not limit:
            return
        
        SQL_SELECT_MANY = 'SELECT k,v FROM %s WHERE k <> ? LIMIT %d, %d ;'
        SQL_SELECT_MANY %= (self._collection, int(offset), int(limit))
        self._cursor.execute(SQL_SELECT_MANY, (self._ZEROS_KEY, ))
        result = self._cursor.fetchall()
        if not result:
            return
        for r in result:
            k = r[0]
            if k == self._ZEROS_KEY:
                continue
            try:
                v = self._serializer.loads(r[1])
            except Exception, err:
                raise RuntimeError('key %s, %s' % (k, err))
            yield (k, v)

    def delete(self, k):
        ''' delete document by k 
        '''
        _key = self.prepare_key(k)
        if _key == self._ZEROS_KEY:
            raise RuntimeError('Metadata cannot be deleted')
        SQL_DELETE = '''DELETE FROM %s WHERE k = ?;''' % self._collection
        self._cursor.execute(SQL_DELETE, (_key,))
                    
        