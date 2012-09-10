import kvlite
import unittest

from kvlite import MysqlCollection
from kvlite import MysqlCollectionManager

class KvliteMysqlTests(unittest.TestCase):

    def setUp(self):
        URI = 'mysql://kvlite_test:eixaaghiequ6ZeiBahn0@localhost/kvlite_test'

        self.collection_name = 'kvlite_test'
        self.manager = MysqlCollectionManager(URI)
        
        if self.collection_name not in self.manager.collections():
            self.manager.create(self.collection_name)
            
        collection_class = self.manager.collection_class
        self.collection = collection_class(self.manager.connection, self.collection_name)

    def tearDown(self):
        
        if self.collection_name in self.manager.collections():
            self.manager.remove(self.collection_name)
        self.collection.close()
    
    def test_mysql_get_uuid(self):
        
        uuids = [self.collection.get_uuid() for i in range(1000)]
        self.assertEqual(len(set(uuids)), 1000)

    def test_put_get_delete_count_one(self):
        
        k = self.collection.get_uuid()
        v = 'test_put_one'
        self.collection.put(k, v)
        self.assertEqual(self.collection.get(k), (k,v))
        self.assertEqual(self.collection.count, 1)
        self.collection.delete(k)
        self.assertEqual(self.collection.count, 0)

    def test_put_get_delete_count_many(self):
        
        ks = list()
        for i in xrange(100):
            k = self.collection.get_uuid()
            v = 'test_{}'.format(i)
            self.collection.put(k, v)
            ks.append(k)
        
        kvs = [kv[0] for kv in self.collection.get()]
        self.assertEqual(len(kvs), 100)

        kvs = [kv for kv in self.collection.keys()]
        self.assertEqual(len(kvs), 100)

        self.assertEqual(self.collection.count, 100)
        for k in ks:
            self.collection.delete(k)
        self.assertEqual(self.collection.count, 0)
        

        
if __name__ == '__main__':
    unittest.main()        

