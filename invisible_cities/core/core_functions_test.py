from __future__ import print_function
from __future__ import absolute_import

import sys, os
from functools import partial

import pandas as pd
import numpy  as np
import numpy.testing as npt

from pytest import mark
from hypothesis import given
from hypothesis.strategies import integers, floats, sampled_from, composite
sane_floats = partial(floats, allow_nan=False, allow_infinity=False)

from . import core_functions as core

def test_lrange():
    assert core.lrange(10) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

def test_trange():
    assert core.trange(10) == (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)

def test_loc_elem_1d():
    assert core.loc_elem_1d(np.array(core.lrange(10)), 5) == 5

@composite
def nonzero_floats(draw, min_value=None, max_value=None):
    sign      = draw(sampled_from((-1, +1)))
    magnitude = draw(floats(min_value=min_value, max_value=max_value))
    return sign * magnitude

# Need to make sure that the step size is not to small compared to the
# range, otherwise the array that needs to be generated may contain so
# many values that we run out of memory. Do this by bounding the
# range's absolute size from above and the step's absolute size from
# below.
np_range_strategies = dict(
    start =         floats(min_value=-100,   max_value=+100),
    stop  =         floats(min_value=-100,   max_value=+100),
    step  = nonzero_floats(min_value=   0.1, max_value=  10))

# Check that the difference between adjacent elements is constant, and
# compare to the behaviour of the real np.arange.
@given(**np_range_strategies)
def test_np_range(start, stop, step):
    x = core.np_range(start, stop, step)
    y = x[1:  ]
    z = x[ :-1]
    steps = y - z
    npt.assert_almost_equal(steps, step)
    npt.assert_array_equal(x, np.arange(start, stop, step))

# Check that the sum of the forward and reverse ranges is the same
# everywhere.
@given(**np_range_strategies)
def test_np_reverse_range(start, stop, step):
    forward = core.        np_range(start, stop, step)
    reverse = core.np_reverse_range(start, stop, step)
    summed = forward + reverse
    if len(summed):
        npt.assert_almost_equal(summed, summed[0])

@given(integers(min_value=0, max_value=99), sane_floats())
def test_np_constant(N, k):
    array = core.np_constant(N,k)
    assert len(array) == N
    assert all(array == k)


def test_dict_map():
    assert (core.dict_map(lambda x: x**2, {'a': 1, 'b': 2, 'c': 3, 'd':  4})
            ==                       {'a': 1, 'b': 4, 'c': 9, 'd': 16})

def test_df_map():
    d = {'q' : [-1, +1, -1],
         'mass' : [0.511, 105., 1776.],
         'spin' :[0.5, 0.5, 0.5]}

    leptons = pd.DataFrame(d,index=['e-', 'mu+', 'tau-'])
    l2 = core.df_map(lambda x: x*1000, leptons, 'mass')
    assert l2.mass.values[0] == 511

def test_dict_filter():
    core.dict_filter(lambda x: x>5,
      {'a':1,'b':20,'c':3,'d':40}) == {'b': 20, 'd': 40}

def test_farray_from_string():
    core.farray_from_string('1 10 100')[2] == 100

def test_rebin_array():
    core.rebin_array(core.lrange(100), 5)[0] == 10

def test_define_window():
    mu, sigma = 100, 0.2 # mean and standard deviation
    sgn = np.random.normal(mu, sigma, 10000)
    n, _ = np.histogram(sgn, 50)
    n0, n1 = core.define_window(n, window_size=10)
    peak = core.loc_elem_1d(n, np.max(n))
    assert n0 == peak - 10
    assert n1 == peak + 10