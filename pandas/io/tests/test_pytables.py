import nose
import unittest
import os
import sys
import warnings

from datetime import datetime
import numpy as np

from pandas import (Series, DataFrame, Panel, MultiIndex, bdate_range,
                    date_range, Index)
from pandas.io.pytables import HDFStore, get_store, Term, IncompatibilityWarning
import pandas.util.testing as tm
from pandas.tests.test_series import assert_series_equal
from pandas.tests.test_frame import assert_frame_equal
from pandas import concat, Timestamp

try:
    import tables
except ImportError:
    raise nose.SkipTest('no pytables')

from distutils.version import LooseVersion

_default_compressor = LooseVersion(tables.__version__) >= '2.2' \
                      and 'blosc' or 'zlib'

_multiprocess_can_split_ = False

class TestHDFStore(unittest.TestCase):
    path = '__test__.h5'
    scratchpath = '__scratch__.h5'

    def setUp(self):
        self.store = HDFStore(self.path)

    def tearDown(self):
        self.store.close()
        os.remove(self.path)

    def test_factory_fun(self):
        try:
            with get_store(self.scratchpath) as tbl:
                raise ValueError('blah')
        except ValueError:
            pass

        with get_store(self.scratchpath) as tbl:
            tbl['a'] = tm.makeDataFrame()

        with get_store(self.scratchpath) as tbl:
            self.assertEquals(len(tbl), 1)
            self.assertEquals(type(tbl['a']), DataFrame)

        os.remove(self.scratchpath)

    def test_keys(self):
        self.store['a'] = tm.makeTimeSeries()
        self.store['b'] = tm.makeStringSeries()
        self.store['c'] = tm.makeDataFrame()
        self.store['d'] = tm.makePanel()
        self.store['foo/bar'] = tm.makePanel()
        self.assertEquals(len(self.store), 5)
        self.assert_(set(self.store.keys()) == set(['/a', '/b', '/c', '/d', '/foo/bar']))

    def test_repr(self):
        repr(self.store)
        self.store['a'] = tm.makeTimeSeries()
        self.store['b'] = tm.makeStringSeries()
        self.store['c'] = tm.makeDataFrame()
        self.store['d'] = tm.makePanel()
        self.store['foo/bar'] = tm.makePanel()
        self.store.append('e', tm.makePanel())
        repr(self.store)
        str(self.store)

    def test_contains(self):
        self.store['a'] = tm.makeTimeSeries()
        self.store['b'] = tm.makeDataFrame()
        self.store['foo/bar'] = tm.makeDataFrame()
        self.assert_('a' in self.store)
        self.assert_('b' in self.store)
        self.assert_('c' not in self.store)
        self.assert_('foo/bar' in self.store)
        self.assert_('/foo/bar' in self.store)
        self.assert_('/foo/b' not in self.store)
        self.assert_('bar' not in self.store)

    def test_versioning(self):
        self.store['a'] = tm.makeTimeSeries()
        self.store['b'] = tm.makeDataFrame()
        df = tm.makeTimeDataFrame()
        self.store.remove('df1')
        self.store.append('df1', df[:10])
        self.store.append('df1', df[10:])
        self.assert_(self.store.root.a._v_attrs.pandas_version == '0.10')
        self.assert_(self.store.root.b._v_attrs.pandas_version == '0.10')
        self.assert_(self.store.root.df1._v_attrs.pandas_version == '0.10')

        # write a file and wipe its versioning
        self.store.remove('df2')
        self.store.append('df2', df)
        self.store.get_node('df2')._v_attrs.pandas_version = None
        self.store.select('df2')
        self.store.select('df2', [ Term('index','>',df.index[2]) ])

    def test_meta(self):
        raise nose.SkipTest('no meta')

        meta = { 'foo' : [ 'I love pandas ' ] }
        s = tm.makeTimeSeries()
        s.meta = meta
        self.store['a'] = s
        self.assert_(self.store['a'].meta == meta)

        df = tm.makeDataFrame()
        df.meta = meta
        self.store['b'] = df
        self.assert_(self.store['b'].meta == meta)

        # this should work, but because slicing doesn't propgate meta it doesn
        self.store.remove('df1')
        self.store.append('df1', df[:10])
        self.store.append('df1', df[10:])
        results = self.store['df1']
        #self.assert_(getattr(results,'meta',None) == meta)

        # no meta
        df = tm.makeDataFrame()
        self.store['b'] = df
        self.assert_(hasattr(self.store['b'],'meta') == False)

    def test_reopen_handle(self):
        self.store['a'] = tm.makeTimeSeries()
        self.store.open('w', warn=False)
        self.assert_(self.store.handle.isopen)
        self.assertEquals(len(self.store), 0)

    def test_flush(self):
        self.store['a'] = tm.makeTimeSeries()
        self.store.flush()

    def test_get(self):
        self.store['a'] = tm.makeTimeSeries()
        left = self.store.get('a')
        right = self.store['a']
        tm.assert_series_equal(left, right)

        left = self.store.get('/a')
        right = self.store['/a']
        tm.assert_series_equal(left, right)

        self.assertRaises(KeyError, self.store.get, 'b')

    def test_put(self):
        ts = tm.makeTimeSeries()
        df = tm.makeTimeDataFrame()
        self.store['a'] = ts
        self.store['b'] = df[:10]
        self.store['foo/bar/bah'] = df[:10]
        self.store['foo'] = df[:10]
        self.store['/foo'] = df[:10]
        self.store.put('c', df[:10], table=True)

        # not OK, not a table
        self.assertRaises(ValueError, self.store.put, 'b', df[10:], append=True)

        # node does not currently exist, test _is_table_type returns False in
        # this case
        self.assertRaises(ValueError, self.store.put, 'f', df[10:], append=True)

        # OK
        self.store.put('c', df[10:], append=True)

        # overwrite table
        self.store.put('c', df[:10], table=True, append=False)
        tm.assert_frame_equal(df[:10], self.store['c'])

    def test_put_string_index(self):

        index = Index([ "I am a very long string index: %s" % i for i in range(20) ])
        s  = Series(np.arange(20), index = index)
        df = DataFrame({ 'A' : s, 'B' : s })

        self.store['a'] = s
        tm.assert_series_equal(self.store['a'], s)

        self.store['b'] = df
        tm.assert_frame_equal(self.store['b'], df)

        # mixed length
        index = Index(['abcdefghijklmnopqrstuvwxyz1234567890'] + [ "I am a very long string index: %s" % i for i in range(20) ])
        s  = Series(np.arange(21), index = index)
        df = DataFrame({ 'A' : s, 'B' : s })
        self.store['a'] = s
        tm.assert_series_equal(self.store['a'], s)

        self.store['b'] = df
        tm.assert_frame_equal(self.store['b'], df)


    def test_put_compression(self):
        df = tm.makeTimeDataFrame()

        self.store.put('c', df, table=True, compression='zlib')
        tm.assert_frame_equal(self.store['c'], df)

        # can't compress if table=False
        self.assertRaises(ValueError, self.store.put, 'b', df,
                          table=False, compression='zlib')

    def test_put_compression_blosc(self):
        tm.skip_if_no_package('tables', '2.2', app='blosc support')
        df = tm.makeTimeDataFrame()

        # can't compress if table=False
        self.assertRaises(ValueError, self.store.put, 'b', df,
                          table=False, compression='blosc')

        self.store.put('c', df, table=True, compression='blosc')
        tm.assert_frame_equal(self.store['c'], df)

    def test_put_integer(self):
        # non-date, non-string index
        df = DataFrame(np.random.randn(50, 100))
        self._check_roundtrip(df, tm.assert_frame_equal)

    def test_append(self):

        df = tm.makeTimeDataFrame()
        self.store.remove('df1')
        self.store.append('df1', df[:10])
        self.store.append('df1', df[10:])
        tm.assert_frame_equal(self.store['df1'], df)

        self.store.remove('df2')
        self.store.put('df2', df[:10], table=True)
        self.store.append('df2', df[10:])
        tm.assert_frame_equal(self.store['df2'], df)

        self.store.remove('df3')
        self.store.append('/df3', df[:10])
        self.store.append('/df3', df[10:])
        tm.assert_frame_equal(self.store['df3'], df)

        # this is allowed by almost always don't want to do it
        warnings.filterwarnings('ignore', category=tables.NaturalNameWarning)
        self.store.remove('/df3 foo')
        self.store.append('/df3 foo', df[:10])
        self.store.append('/df3 foo', df[10:])
        tm.assert_frame_equal(self.store['df3 foo'], df)
        warnings.filterwarnings('always', category=tables.NaturalNameWarning)
        
        # panel
        wp = tm.makePanel()
        self.store.remove('wp1')
        self.store.append('wp1', wp.ix[:,:10,:])
        self.store.append('wp1', wp.ix[:,10:,:])
        tm.assert_panel_equal(self.store['wp1'], wp)

        # ndim
        p4d = tm.makePanel4D()
        self.store.remove('p4d')
        self.store.append('p4d', p4d.ix[:,:,:10,:])
        self.store.append('p4d', p4d.ix[:,:,10:,:])
        tm.assert_panel4d_equal(self.store['p4d'], p4d)

        # test using axis labels
        self.store.remove('p4d')
        self.store.append('p4d', p4d.ix[:,:,:10,:], axes=['items','major_axis','minor_axis'])
        self.store.append('p4d', p4d.ix[:,:,10:,:], axes=['items','major_axis','minor_axis'])
        tm.assert_panel4d_equal(self.store['p4d'], p4d)

    def test_append_frame_column_oriented(self):

        # column oriented
        df = tm.makeTimeDataFrame()
        self.store.remove('df1')
        self.store.append('df1', df.ix[:,:2], axes = ['columns'])
        self.store.append('df1', df.ix[:,2:])
        tm.assert_frame_equal(self.store['df1'], df)

        result = self.store.select('df1', 'columns=A')
        expected = df.reindex(columns=['A'])
        tm.assert_frame_equal(expected, result)

        # this isn't supported
        self.assertRaises(Exception, self.store.select, 'df1', ('columns=A', Term('index','>',df.index[4])))

        # selection on the non-indexable
        result = self.store.select('df1', ('columns=A', Term('index','=',df.index[0:4])))
        expected = df.reindex(columns=['A'],index=df.index[0:4])
        tm.assert_frame_equal(expected, result)

    def test_ndim_indexables(self):
        """ test using ndim tables in new ways"""

        p4d = tm.makePanel4D()

        # append then change (will take existing schema)
        self.store.remove('p4d')
        self.store.append('p4d', p4d.ix[:,:,:10,:], axes=['items','major_axis','minor_axis'])
        self.store.append('p4d', p4d.ix[:,:,10:,:], axes=['labels','items','major_axis'])

        # pass incorrect number of axes
        self.store.remove('p4d')
        self.assertRaises(Exception, self.store.append, 'p4d', p4d.ix[:,:,:10,:], axes=['major_axis','minor_axis'])

        # different than default indexables
        self.store.remove('p4d')
        self.store.append('p4d', p4d.ix[:,:,:10,:], axes=[0,2,3])
        self.store.append('p4d', p4d.ix[:,:,10:,:], axes=[0,2,3])
        tm.assert_panel4d_equal(self.store['p4d'], p4d)

        # partial selection
        result = self.store.select('p4d',['labels=l1'])
        expected = p4d.reindex(labels = ['l1'])
        tm.assert_panel4d_equal(result, expected)

        # partial selection2
        result = self.store.select('p4d',[Term('labels=l1'), Term('items=ItemA'), Term('minor_axis=B')])
        expected = p4d.reindex(labels = ['l1'], items = ['ItemA'], minor_axis = ['B'])
        tm.assert_panel4d_equal(result, expected)

        # non-existant partial selection
        result = self.store.select('p4d',[Term('labels=l1'), Term('items=Item1'), Term('minor_axis=B')])
        expected = p4d.reindex(labels = ['l1'], items = [], minor_axis = ['B'])
        tm.assert_panel4d_equal(result, expected)

    def test_append_with_strings(self):
        wp = tm.makePanel()
        wp2 = wp.rename_axis(dict([ (x,"%s_extra" % x) for x in wp.minor_axis ]), axis = 2)

        self.store.append('s1', wp, min_itemsize = 20)
        self.store.append('s1', wp2)
        expected = concat([ wp, wp2], axis = 2)
        expected = expected.reindex(minor_axis = sorted(expected.minor_axis))
        tm.assert_panel_equal(self.store['s1'], expected)

        # test dict format
        self.store.append('s2', wp, min_itemsize = { 'minor_axis' : 20 })
        self.store.append('s2', wp2)
        expected = concat([ wp, wp2], axis = 2)
        expected = expected.reindex(minor_axis = sorted(expected.minor_axis))
        tm.assert_panel_equal(self.store['s2'], expected)

        # apply the wrong field (similar to #1)
        self.store.append('s3', wp, min_itemsize = { 'major_axis' : 20 })
        self.assertRaises(Exception, self.store.append, 's3')

        # test truncation of bigger strings
        self.store.append('s4', wp)
        self.assertRaises(Exception, self.store.append, 's4', wp2)

        # avoid truncation on elements
        df = DataFrame([[123,'asdqwerty'], [345,'dggnhebbsdfbdfb']])
        self.store.append('df_big',df, min_itemsize = { 'values' : 1024 })
        tm.assert_frame_equal(self.store.select('df_big'), df)

        # appending smaller string ok
        df2 = DataFrame([[124,'asdqy'], [346,'dggnhefbdfb']])
        self.store.append('df_big',df2)
        expected = concat([ df, df2 ])
        tm.assert_frame_equal(self.store.select('df_big'), expected)

        # avoid truncation on elements
        df = DataFrame([[123,'asdqwerty'], [345,'dggnhebbsdfbdfb']])
        self.store.append('df_big2',df, min_itemsize = { 'values' : 10 })
        tm.assert_frame_equal(self.store.select('df_big2'), df)

        # bigger string on next append
        self.store.append('df_new',df, min_itemsize = { 'values' : 16 })
        df_new  = DataFrame([[124,'abcdefqhij'], [346, 'abcdefghijklmnopqrtsuvwxyz']])
        self.assertRaises(Exception, self.store.append, 'df_new',df_new)

    def test_create_table_index(self):
        wp = tm.makePanel()
        self.store.append('p5', wp)
        self.store.create_table_index('p5')

        assert(self.store.handle.root.p5.table.cols.major_axis.is_indexed == True)
        assert(self.store.handle.root.p5.table.cols.minor_axis.is_indexed == False)

        # default optlevels
        assert(self.store.handle.root.p5.table.cols.major_axis.index.optlevel == 6)
        assert(self.store.handle.root.p5.table.cols.major_axis.index.kind == 'medium')

        # let's change the indexing scheme
        self.store.create_table_index('p5')
        assert(self.store.handle.root.p5.table.cols.major_axis.index.optlevel == 6)
        assert(self.store.handle.root.p5.table.cols.major_axis.index.kind == 'medium')
        self.store.create_table_index('p5', optlevel=9)
        assert(self.store.handle.root.p5.table.cols.major_axis.index.optlevel == 9)
        assert(self.store.handle.root.p5.table.cols.major_axis.index.kind == 'medium')
        self.store.create_table_index('p5', kind='full')
        assert(self.store.handle.root.p5.table.cols.major_axis.index.optlevel == 9)
        assert(self.store.handle.root.p5.table.cols.major_axis.index.kind == 'full')
        self.store.create_table_index('p5', optlevel=1, kind='light')
        assert(self.store.handle.root.p5.table.cols.major_axis.index.optlevel == 1)
        assert(self.store.handle.root.p5.table.cols.major_axis.index.kind == 'light')

        df = tm.makeTimeDataFrame()
        self.store.append('f', df[:10])
        self.store.append('f', df[10:])
        self.store.create_table_index('f')

        # try to index a non-table
        self.store.put('f2', df)
        self.assertRaises(Exception, self.store.create_table_index, 'f2')

        # try to change the version supports flag
        from pandas.io import pytables
        pytables._table_supports_index = False
        self.assertRaises(Exception, self.store.create_table_index, 'f')

        # test out some versions
        original = tables.__version__

        for v in ['2.2','2.2b']:
            pytables._table_mod = None
            pytables._table_supports_index = False
            tables.__version__ = v
            self.assertRaises(Exception, self.store.create_table_index, 'f')

        for v in ['2.3.1','2.3.1b','2.4dev','2.4',original]:
            pytables._table_mod = None
            pytables._table_supports_index = False
            tables.__version__ = v
            self.store.create_table_index('f')
        pytables._table_mod = None
        pytables._table_supports_index = False
        tables.__version__ = original
        

    def test_big_table(self):
        raise nose.SkipTest('no big table')

        # create and write a big table
        wp = Panel(np.random.randn(20, 1000, 1000), items= [ 'Item%s' % i for i in xrange(20) ],
                   major_axis=date_range('1/1/2000', periods=1000), minor_axis = [ 'E%s' % i for i in xrange(1000) ])

        wp.ix[:,100:200,300:400] = np.nan

        try:
            store = HDFStore(self.scratchpath)
            store._debug_memory = True
            store.append('wp',wp)
            recons = store.select('wp')
        finally:
            store.close()
            os.remove(self.scratchpath)

    def test_append_diff_item_order(self):
        wp = tm.makePanel()
        wp1 = wp.ix[:, :10, :]
        wp2 = wp.ix[['ItemC', 'ItemB', 'ItemA'], 10:, :]

        self.store.put('panel', wp1, table=True)
        self.assertRaises(Exception, self.store.put, 'panel', wp2,
                          append=True)

    def test_table_index_incompatible_dtypes(self):
        df1 = DataFrame({'a': [1, 2, 3]})
        df2 = DataFrame({'a': [4, 5, 6]},
                        index=date_range('1/1/2000', periods=3))

        self.store.put('frame', df1, table=True)
        self.assertRaises(Exception, self.store.put, 'frame', df2,
                          table=True, append=True)

    def test_table_values_dtypes_roundtrip(self):
        df1 = DataFrame({'a': [1, 2, 3]}, dtype = 'f8')
        self.store.append('df1', df1)
        assert df1.dtypes == self.store['df1'].dtypes

        df2 = DataFrame({'a': [1, 2, 3]}, dtype = 'i8')
        self.store.append('df2', df2)
        assert df2.dtypes == self.store['df2'].dtypes

        # incompatible dtype
        self.assertRaises(Exception, self.store.append, 'df2', df1)

    def test_table_mixed_dtypes(self):

        # frame
        def _make_one_df():
            df = tm.makeDataFrame()
            df['obj1'] = 'foo'
            df['obj2'] = 'bar'
            df['bool1'] = df['A'] > 0
            df['bool2'] = df['B'] > 0
            df['bool3'] = True
            df['int1'] = 1
            df['int2'] = 2
            return df.consolidate()

        df1 = _make_one_df()

        self.store.append('df1_mixed', df1)
        tm.assert_frame_equal(self.store.select('df1_mixed'), df1)

        # panel
        def _make_one_panel():
            wp = tm.makePanel()
            wp['obj1'] = 'foo'
            wp['obj2'] = 'bar'
            wp['bool1'] = wp['ItemA'] > 0
            wp['bool2'] = wp['ItemB'] > 0
            wp['int1'] = 1
            wp['int2'] = 2
            return wp.consolidate()
        p1 = _make_one_panel()

        self.store.append('p1_mixed', p1)
        tm.assert_panel_equal(self.store.select('p1_mixed'), p1)

        # ndim
        def _make_one_p4d():
            wp = tm.makePanel4D()
            wp['obj1'] = 'foo'
            wp['obj2'] = 'bar'
            wp['bool1'] = wp['l1'] > 0
            wp['bool2'] = wp['l2'] > 0
            wp['int1'] = 1
            wp['int2'] = 2
            return wp.consolidate()

        p4d = _make_one_p4d()
        self.store.append('p4d_mixed', p4d)
        tm.assert_panel4d_equal(self.store.select('p4d_mixed'), p4d)

    def test_remove(self):
        ts = tm.makeTimeSeries()
        df = tm.makeDataFrame()
        self.store['a'] = ts
        self.store['b'] = df
        self.store.remove('a')
        self.assertEquals(len(self.store), 1)
        tm.assert_frame_equal(df, self.store['b'])

        self.store.remove('b')
        self.assertEquals(len(self.store), 0)

        # pathing
        self.store['a'] = ts
        self.store['b/foo'] = df
        self.store.remove('foo')
        self.store.remove('b/foo')
        self.assertEquals(len(self.store), 1)

        self.store['a'] = ts
        self.store['b/foo'] = df
        self.store.remove('b')
        self.assertEquals(len(self.store), 1)

        # __delitem__
        self.store['a'] = ts
        self.store['b'] = df
        del self.store['a']
        del self.store['b']
        self.assertEquals(len(self.store), 0)

    def test_remove_where(self):

        # non-existance
        crit1 = Term('index','>','foo')
        self.store.remove('a', where=[crit1])

        # try to remove non-table (with crit)
        # non-table ok (where = None)
        wp = tm.makePanel()
        self.store.put('wp', wp, table=True)
        self.store.remove('wp', [('minor_axis', ['A', 'D'])])
        rs = self.store.select('wp')
        expected = wp.reindex(minor_axis = ['B','C'])
        tm.assert_panel_equal(rs,expected)

        # empty where
        self.store.remove('wp')
        self.store.put('wp', wp, table=True)

        # deleted number (entire table)
        n = self.store.remove('wp', [])
        assert(n == 120)

        # non - empty where
        self.store.remove('wp')
        self.store.put('wp', wp, table=True)
        self.assertRaises(Exception, self.store.remove,
                          'wp', ['foo'])

        # selectin non-table with a where
        #self.store.put('wp2', wp, table=False)
        #self.assertRaises(Exception, self.store.remove,
        #                  'wp2', [('column', ['A', 'D'])])


    def test_remove_crit(self):
        wp = tm.makePanel()
        self.store.put('wp', wp, table=True)
        date = wp.major_axis[len(wp.major_axis) // 2]

        crit1 = Term('major_axis','>',date)
        crit2 = Term('minor_axis',['A', 'D'])
        n = self.store.remove('wp', where=[crit1])

        # deleted number
        assert(n == 56)

        n = self.store.remove('wp', where=[crit2])
        assert(n == 32)

        result = self.store['wp']
        expected = wp.truncate(after=date).reindex(minor=['B', 'C'])
        tm.assert_panel_equal(result, expected)

        # test non-consecutive row removal
        wp = tm.makePanel()
        self.store.put('wp2', wp, table=True)

        date1 = wp.major_axis[1:3]
        date2 = wp.major_axis[5]
        date3 = [wp.major_axis[7],wp.major_axis[9]]

        crit1 = Term('major_axis',date1)
        crit2 = Term('major_axis',date2)
        crit3 = Term('major_axis',date3)

        self.store.remove('wp2', where=[crit1])
        self.store.remove('wp2', where=[crit2])
        self.store.remove('wp2', where=[crit3])
        result = self.store['wp2']

        ma = list(wp.major_axis)
        for d in date1:
            ma.remove(d)
        ma.remove(date2)
        for d in date3:
            ma.remove(d)
        expected = wp.reindex(major = ma)
        tm.assert_panel_equal(result, expected)

    def test_terms(self):

        wp = tm.makePanel()
        p4d = tm.makePanel4D()
        self.store.put('wp', wp, table=True)
        self.store.put('p4d', p4d, table=True)

        # some invalid terms
        terms = [
            [ 'minor', ['A','B'] ],
            [ 'index', ['20121114'] ],
            [ 'index', ['20121114', '20121114'] ],
            ]
        for t in terms:
            self.assertRaises(Exception, self.store.select, 'wp', t)

        self.assertRaises(Exception, Term.__init__)
        self.assertRaises(Exception, Term.__init__, 'blah')
        self.assertRaises(Exception, Term.__init__, 'index')
        self.assertRaises(Exception, Term.__init__, 'index', '==')
        self.assertRaises(Exception, Term.__init__, 'index', '>', 5)

        # panel
        result = self.store.select('wp',[ Term('major_axis<20000108'), Term('minor_axis', '=', ['A','B']) ])
        expected = wp.truncate(after='20000108').reindex(minor=['A', 'B'])
        tm.assert_panel_equal(result, expected)

        # p4d
        result = self.store.select('p4d',[ Term('major_axis<20000108'), Term('minor_axis', '=', ['A','B']), Term('items', '=', ['ItemA','ItemB']) ])
        expected = p4d.truncate(after='20000108').reindex(minor=['A', 'B'],items=['ItemA','ItemB'])
        tm.assert_panel4d_equal(result, expected)

        # valid terms
        terms = [
            dict(field = 'major_axis', op = '>', value = '20121114'),
            ('major_axis', '20121114'),
            ('major_axis', '>', '20121114'),
            (('major_axis', ['20121114','20121114']),),
            ('major_axis', datetime(2012,11,14)),
            'major_axis>20121114',
            'major_axis>20121114',
            'major_axis>20121114',
            (('minor_axis', ['A','B']),),
            (('minor_axis', ['A','B']),),
            ((('minor_axis', ['A','B']),),),
            (('items', ['ItemA','ItemB']),),
            ('items=ItemA'),
            ]

        for t in terms:
           self.store.select('wp', t)
           self.store.select('p4d', t)

        # valid for p4d only
        terms = [
            (('labels', '=', ['l1','l2']),),
            Term('labels', '=', ['l1','l2']),
            ]

        for t in terms:
           self.store.select('p4d', t)

    def test_series(self):
        s = tm.makeStringSeries()
        self._check_roundtrip(s, tm.assert_series_equal)

        ts = tm.makeTimeSeries()
        self._check_roundtrip(ts, tm.assert_series_equal)

        ts2 = Series(ts.index, Index(ts.index, dtype=object))
        self._check_roundtrip(ts2, tm.assert_series_equal)

        ts3 = Series(ts.values, Index(np.asarray(ts.index, dtype=object),
                                      dtype=object))
        self._check_roundtrip(ts3, tm.assert_series_equal)

    def test_sparse_series(self):
        s = tm.makeStringSeries()
        s[3:5] = np.nan
        ss = s.to_sparse()
        self._check_roundtrip(ss, tm.assert_series_equal,
                              check_series_type=True)

        ss2 = s.to_sparse(kind='integer')
        self._check_roundtrip(ss2, tm.assert_series_equal,
                              check_series_type=True)

        ss3 = s.to_sparse(fill_value=0)
        self._check_roundtrip(ss3, tm.assert_series_equal,
                              check_series_type=True)

    def test_sparse_frame(self):
        s = tm.makeDataFrame()
        s.ix[3:5, 1:3] = np.nan
        s.ix[8:10, -2] = np.nan
        ss = s.to_sparse()
        self._check_double_roundtrip(ss, tm.assert_frame_equal,
                                     check_frame_type=True)

        ss2 = s.to_sparse(kind='integer')
        self._check_double_roundtrip(ss2, tm.assert_frame_equal,
                                     check_frame_type=True)

        ss3 = s.to_sparse(fill_value=0)
        self._check_double_roundtrip(ss3, tm.assert_frame_equal,
                                     check_frame_type=True)

    def test_sparse_panel(self):
        items = ['x', 'y', 'z']
        p = Panel(dict((i, tm.makeDataFrame().ix[:2, :2]) for i in items))
        sp = p.to_sparse()

        self._check_double_roundtrip(sp, tm.assert_panel_equal,
                                     check_panel_type=True)

        sp2 = p.to_sparse(kind='integer')
        self._check_double_roundtrip(sp2, tm.assert_panel_equal,
                                     check_panel_type=True)

        sp3 = p.to_sparse(fill_value=0)
        self._check_double_roundtrip(sp3, tm.assert_panel_equal,
                                     check_panel_type=True)

    def test_float_index(self):
        # GH #454
        index = np.random.randn(10)
        s = Series(np.random.randn(10), index=index)
        self._check_roundtrip(s, tm.assert_series_equal)

    def test_tuple_index(self):
        # GH #492
        col = np.arange(10)
        idx = [(0.,1.), (2., 3.), (4., 5.)]
        data = np.random.randn(30).reshape((3, 10))
        DF = DataFrame(data, index=idx, columns=col)
        self._check_roundtrip(DF, tm.assert_frame_equal)

    def test_index_types(self):
        values = np.random.randn(2)

        func = lambda l, r : tm.assert_series_equal(l, r, True, True, True)

        ser = Series(values, [0, 'y'])
        self._check_roundtrip(ser, func)

        ser = Series(values, [datetime.today(), 0])
        self._check_roundtrip(ser, func)

        ser = Series(values, ['y', 0])
        self._check_roundtrip(ser, func)

        from datetime import date
        ser = Series(values, [date.today(), 'a'])
        self._check_roundtrip(ser, func)

        ser = Series(values, [1.23, 'b'])
        self._check_roundtrip(ser, func)

        ser = Series(values, [1, 1.53])
        self._check_roundtrip(ser, func)

        ser = Series(values, [1, 5])
        self._check_roundtrip(ser, func)

        ser = Series(values, [datetime(2012, 1, 1), datetime(2012, 1, 2)])
        self._check_roundtrip(ser, func)

    def test_timeseries_preepoch(self):
        if sys.version_info[0] == 2 and sys.version_info[1] < 7:
            raise nose.SkipTest

        dr = bdate_range('1/1/1940', '1/1/1960')
        ts = Series(np.random.randn(len(dr)), index=dr)
        try:
            self._check_roundtrip(ts, tm.assert_series_equal)
        except OverflowError:
            raise nose.SkipTest('known failer on some windows platforms')

    def test_frame(self):
        df = tm.makeDataFrame()

        # put in some random NAs
        df.values[0, 0] = np.nan
        df.values[5, 3] = np.nan

        self._check_roundtrip_table(df, tm.assert_frame_equal)
        self._check_roundtrip(df, tm.assert_frame_equal)

        self._check_roundtrip_table(df, tm.assert_frame_equal,
                                    compression=True)
        self._check_roundtrip(df, tm.assert_frame_equal,
                                    compression=True)

        tdf = tm.makeTimeDataFrame()
        self._check_roundtrip(tdf, tm.assert_frame_equal)
        self._check_roundtrip(tdf, tm.assert_frame_equal,
                              compression=True)

        # not consolidated
        df['foo'] = np.random.randn(len(df))
        self.store['df'] = df
        recons = self.store['df']
        self.assert_(recons._data.is_consolidated())

        # empty
        self._check_roundtrip(df[:0], tm.assert_frame_equal)

    def test_empty_series_frame(self):
        s0 = Series()
        s1 = Series(name='myseries')
        df0 = DataFrame()
        df1 = DataFrame(index=['a', 'b', 'c'])
        df2 = DataFrame(columns=['d', 'e', 'f'])

        self._check_roundtrip(s0, tm.assert_series_equal)
        self._check_roundtrip(s1, tm.assert_series_equal)
        self._check_roundtrip(df0, tm.assert_frame_equal)
        self._check_roundtrip(df1, tm.assert_frame_equal)
        self._check_roundtrip(df2, tm.assert_frame_equal)

    def test_can_serialize_dates(self):
        rng = [x.date() for x in bdate_range('1/1/2000', '1/30/2000')]
        frame = DataFrame(np.random.randn(len(rng), 4), index=rng)
        self._check_roundtrip(frame, tm.assert_frame_equal)

    def test_timezones(self):
        rng = date_range('1/1/2000', '1/30/2000', tz='US/Eastern')
        frame = DataFrame(np.random.randn(len(rng), 4), index=rng)
        try:
            store = HDFStore(self.scratchpath)
            store['frame'] = frame
            recons = store['frame']
            self.assert_(recons.index.equals(rng))
            self.assertEquals(rng.tz, recons.index.tz)
        finally:
            store.close()
            os.remove(self.scratchpath)

    def test_fixed_offset_tz(self):
        rng = date_range('1/1/2000 00:00:00-07:00', '1/30/2000 00:00:00-07:00')
        frame = DataFrame(np.random.randn(len(rng), 4), index=rng)
        try:
            store = HDFStore(self.scratchpath)
            store['frame'] = frame
            recons = store['frame']
            self.assert_(recons.index.equals(rng))
            self.assertEquals(rng.tz, recons.index.tz)
        finally:
            store.close()
            os.remove(self.scratchpath)

    def test_store_hierarchical(self):
        index = MultiIndex(levels=[['foo', 'bar', 'baz', 'qux'],
                                   ['one', 'two', 'three']],
                           labels=[[0, 0, 0, 1, 1, 2, 2, 3, 3, 3],
                                   [0, 1, 2, 0, 1, 1, 2, 0, 1, 2]],
                           names=['foo', 'bar'])
        frame = DataFrame(np.random.randn(10, 3), index=index,
                          columns=['A', 'B', 'C'])

        self._check_roundtrip(frame, tm.assert_frame_equal)
        self._check_roundtrip(frame.T, tm.assert_frame_equal)
        self._check_roundtrip(frame['A'], tm.assert_series_equal)

        # check that the names are stored
        try:
            store = HDFStore(self.scratchpath)
            store['frame'] = frame
            recons = store['frame']
            assert(recons.index.names == ['foo', 'bar'])
        finally:
            store.close()
            os.remove(self.scratchpath)

    def test_store_index_name(self):
        df = tm.makeDataFrame()
        df.index.name = 'foo'
        try:
            store = HDFStore(self.scratchpath)
            store['frame'] = df
            recons = store['frame']
            assert(recons.index.name == 'foo')
        finally:
            store.close()
            os.remove(self.scratchpath)

    def test_store_series_name(self):
        df = tm.makeDataFrame()
        series = df['A']

        try:
            store = HDFStore(self.scratchpath)
            store['series'] = series
            recons = store['series']
            assert(recons.name == 'A')
        finally:
            store.close()
            os.remove(self.scratchpath)

    def test_store_mixed(self):
        def _make_one():
            df = tm.makeDataFrame()
            df['obj1'] = 'foo'
            df['obj2'] = 'bar'
            df['bool1'] = df['A'] > 0
            df['bool2'] = df['B'] > 0
            df['int1'] = 1
            df['int2'] = 2
            return df.consolidate()

        df1 = _make_one()
        df2 = _make_one()

        self._check_roundtrip(df1, tm.assert_frame_equal)
        self._check_roundtrip(df2, tm.assert_frame_equal)

        self.store['obj'] = df1
        tm.assert_frame_equal(self.store['obj'], df1)
        self.store['obj'] = df2
        tm.assert_frame_equal(self.store['obj'], df2)

        # check that can store Series of all of these types
        self._check_roundtrip(df1['obj1'], tm.assert_series_equal)
        self._check_roundtrip(df1['bool1'], tm.assert_series_equal)
        self._check_roundtrip(df1['int1'], tm.assert_series_equal)

        # try with compression
        self._check_roundtrip(df1['obj1'], tm.assert_series_equal,
                              compression=True)
        self._check_roundtrip(df1['bool1'], tm.assert_series_equal,
                              compression=True)
        self._check_roundtrip(df1['int1'], tm.assert_series_equal,
                              compression=True)
        self._check_roundtrip(df1, tm.assert_frame_equal,
                              compression=True)

    def test_wide(self):
        wp = tm.makePanel()
        self._check_roundtrip(wp, tm.assert_panel_equal)

    def test_wide_table(self):
        wp = tm.makePanel()
        self._check_roundtrip_table(wp, tm.assert_panel_equal)

    def test_wide_table_dups(self):
        wp = tm.makePanel()
        try:
            store = HDFStore(self.scratchpath)
            store._quiet = True
            store.put('panel', wp, table=True)
            store.put('panel', wp, table=True, append=True)
            recons = store['panel']
            tm.assert_panel_equal(recons, wp)
        finally:
            store.close()
            os.remove(self.scratchpath)

    def test_long(self):
        def _check(left, right):
            tm.assert_panel_equal(left.to_panel(), right.to_panel())

        wp = tm.makePanel()
        self._check_roundtrip(wp.to_frame(), _check)

        # empty
        # self._check_roundtrip(wp.to_frame()[:0], _check)

    def test_longpanel(self):
        pass

    def test_overwrite_node(self):
        self.store['a'] = tm.makeTimeDataFrame()
        ts = tm.makeTimeSeries()
        self.store['a'] = ts

        tm.assert_series_equal(self.store['a'], ts)

    def test_select(self):
        wp = tm.makePanel()

        # put/select ok
        self.store.put('wp', wp, table=True)
        self.store.select('wp')

        # non-table ok (where = None)
        self.store.put('wp2', wp, table=False)
        self.store.select('wp2')

        # selectin non-table with a where
        #self.assertRaises(Exception, self.store.select,
        #                  'wp2', ('column', ['A', 'D']))

    def test_panel_select(self):
        wp = tm.makePanel()
        self.store.put('wp', wp, table=True)
        date = wp.major_axis[len(wp.major_axis) // 2]

        crit1 = ('major_axis','>=',date)
        crit2 = ('minor_axis', '=', ['A', 'D'])

        result = self.store.select('wp', [crit1, crit2])
        expected = wp.truncate(before=date).reindex(minor=['A', 'D'])
        tm.assert_panel_equal(result, expected)

        result = self.store.select('wp', [ 'major_axis>=20000124', ('minor_axis', '=', ['A','B']) ])
        expected = wp.truncate(before='20000124').reindex(minor=['A', 'B'])
        tm.assert_panel_equal(result, expected)

    def test_frame_select(self):
        df = tm.makeTimeDataFrame()
        self.store.put('frame', df, table=True)
        date = df.index[len(df) // 2]

        crit1 = ('index','>=',date)
        crit2 = ('columns',['A', 'D'])
        crit3 = ('columns','A')

        result = self.store.select('frame', [crit1, crit2])
        expected = df.ix[date:, ['A', 'D']]
        tm.assert_frame_equal(result, expected)

        result = self.store.select('frame', [crit3])
        expected = df.ix[:, ['A']]
        tm.assert_frame_equal(result, expected)

        # other indicies for a frame

        # integer
        df = DataFrame(dict(A = np.random.rand(20), B = np.random.rand(20)))
        self.store.append('df_int', df)
        self.store.select('df_int', [ Term("index<10"), Term("columns", "=", ["A"]) ])

        df = DataFrame(dict(A = np.random.rand(20), B = np.random.rand(20), index = np.arange(20,dtype='f8')))
        self.store.append('df_float', df)
        self.store.select('df_float', [ Term("index<10.0"), Term("columns", "=", ["A"]) ])

        # can't select if not written as table
        #self.store['frame'] = df
        #self.assertRaises(Exception, self.store.select,
        #                  'frame', [crit1, crit2])

    def test_select_filter_corner(self):
        df = DataFrame(np.random.randn(50, 100))
        df.index = ['%.3d' % c for c in df.index]
        df.columns = ['%.3d' % c for c in df.columns]
        self.store.put('frame', df, table=True)

        crit = Term('columns', df.columns[:75])
        result = self.store.select('frame', [crit])
        tm.assert_frame_equal(result, df.ix[:, df.columns[:75]])

    def _check_roundtrip(self, obj, comparator, compression=False, **kwargs):
        options = {}
        if compression:
            options['complib'] = _default_compressor

        store = HDFStore(self.scratchpath, 'w', **options)
        try:
            store['obj'] = obj
            retrieved = store['obj']
            comparator(retrieved, obj, **kwargs)
        finally:
            store.close()
            os.remove(self.scratchpath)

    def _check_double_roundtrip(self, obj, comparator, compression=False,
                                **kwargs):
        options = {}
        if compression:
            options['complib'] = _default_compressor

        store = HDFStore(self.scratchpath, 'w', **options)
        try:
            store['obj'] = obj
            retrieved = store['obj']
            comparator(retrieved, obj, **kwargs)
            store['obj'] = retrieved
            again = store['obj']
            comparator(again, obj, **kwargs)
        finally:
            store.close()
            os.remove(self.scratchpath)

    def _check_roundtrip_table(self, obj, comparator, compression=False):
        options = {}
        if compression:
            options['complib'] = _default_compressor

        store = HDFStore(self.scratchpath, 'w', **options)
        try:
            store.put('obj', obj, table=True)
            retrieved = store['obj']
            # sorted_obj = _test_sort(obj)
            comparator(retrieved, obj)
        finally:
            store.close()
            os.remove(self.scratchpath)

    def test_legacy_read(self):
        pth = curpath()
        store = HDFStore(os.path.join(pth, 'legacy.h5'), 'r')
        store['a']
        store['b']
        store['c']
        store['d']
        store.close()

    def test_legacy_table_read(self):
        # legacy table types
        pth = curpath()
        store = HDFStore(os.path.join(pth, 'legacy_table.h5'), 'r')
        store.select('df1')
        store.select('df2')
        store.select('wp1')

        # force the frame
        store.select('df2', typ = 'legacy_frame')

        # old version (this still throws an exception though)
        import warnings
        warnings.filterwarnings('ignore', category=IncompatibilityWarning)
        self.assertRaises(Exception, store.select, 'wp1', Term('minor_axis','=','B'))
        warnings.filterwarnings('always', category=IncompatibilityWarning)

        store.close()

    def test_legacy_table_write(self):
        # legacy table types
        pth = curpath()
        df = tm.makeDataFrame()
        wp = tm.makePanel()

        store = HDFStore(os.path.join(pth, 'legacy_table.h5'), 'a')

        self.assertRaises(Exception, store.append, 'df1', df)
        self.assertRaises(Exception, store.append, 'wp1', wp)

        store.close()

    def test_store_datetime_fractional_secs(self):
        dt = datetime(2012, 1, 2, 3, 4, 5, 123456)
        series = Series([0], [dt])
        self.store['a'] = series
        self.assertEquals(self.store['a'].index[0], dt)

    def test_tseries_indices_series(self):
        idx = tm.makeDateIndex(10)
        ser = Series(np.random.randn(len(idx)), idx)
        self.store['a'] = ser
        result = self.store['a']

        assert_series_equal(result, ser)
        self.assertEquals(type(result.index), type(ser.index))
        self.assertEquals(result.index.freq, ser.index.freq)

        idx = tm.makePeriodIndex(10)
        ser = Series(np.random.randn(len(idx)), idx)
        self.store['a'] = ser
        result = self.store['a']

        assert_series_equal(result, ser)
        self.assertEquals(type(result.index), type(ser.index))
        self.assertEquals(result.index.freq, ser.index.freq)

    def test_tseries_indices_frame(self):
        idx = tm.makeDateIndex(10)
        df = DataFrame(np.random.randn(len(idx), 3), index=idx)
        self.store['a'] = df
        result = self.store['a']

        assert_frame_equal(result, df)
        self.assertEquals(type(result.index), type(df.index))
        self.assertEquals(result.index.freq, df.index.freq)

        idx = tm.makePeriodIndex(10)
        df = DataFrame(np.random.randn(len(idx), 3), idx)
        self.store['a'] = df
        result = self.store['a']

        assert_frame_equal(result, df)
        self.assertEquals(type(result.index), type(df.index))
        self.assertEquals(result.index.freq, df.index.freq)

    def test_unicode_index(self):
        unicode_values = [u'\u03c3', u'\u03c3\u03c3']

        s = Series(np.random.randn(len(unicode_values)), unicode_values)
        self._check_roundtrip(s, tm.assert_series_equal)

    def test_store_datetime_mixed(self):
        df = DataFrame({'a': [1,2,3], 'b': [1.,2.,3.], 'c': ['a', 'b', 'c']})
        ts = tm.makeTimeSeries()
        df['d'] = ts.index[:3]
        self._check_roundtrip(df, tm.assert_frame_equal)

    def test_cant_write_multiindex_table(self):
        # for now, #1848
        df = DataFrame(np.random.randn(10, 4),
                       index=[np.arange(5).repeat(2),
                              np.tile(np.arange(2), 5)])

        self.assertRaises(Exception, self.store.put, 'foo', df, table=True)

def curpath():
    pth, _ = os.path.split(os.path.abspath(__file__))
    return pth

def _test_sort(obj):
    if isinstance(obj, DataFrame):
        return obj.reindex(sorted(obj.index))
    elif isinstance(obj, Panel):
        return obj.reindex(major=sorted(obj.major_axis))
    else:
        raise ValueError('type not supported here')

if __name__ == '__main__':
    import nose
    nose.runmodule(argv=[__file__,'-vvs','-x','--pdb', '--pdb-failure'],
                   exit=False)
