#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2017 Mark Wolf
#
# This file is part of Xanespy.
#
# Xanespy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Xanespy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Xanespy.  If not, see <http://www.gnu.org/licenses/>.

# flake8: noqa

import unittest
from unittest import TestCase, mock
from collections import namedtuple
import os
import math
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from xanespy.fitting import (LinearCombination, KCurve, Gaussian,
                             L3Curve, prepare_p0, _fit_sources,
                             fit_spectra, Curve, Line, error,
                             guess_p0, find_whiteline,
                             is_out_of_bounds, distance_to_bounds)
from xanespy import edges


TEST_DIR = os.path.dirname(__file__)
SSRL_DIR = os.path.join(TEST_DIR, 'txm-data-ssrl')


class FittingTestCase(TestCase):
    def test_base_curve(self):
        curve = Curve(x=None)
        # Check that basic methods are stubbed
        with self.assertRaises(NotImplementedError):
            curve.guess_params(None, None)
        # Check the NamedTuple produced from param_names
        n_tuple = curve.NamedTuple()
        self.assertEqual(str(n_tuple), 'curve_params()')
    
    def test_line(self):
        # Prepare a basic line
        x = np.linspace(1, 2, num=10)
        m, b = (2, -1)
        noise = [0.094, 0.0485, 0.087, 0.004, 0.053, 0.097, 0.015,
                 0.0725, 0.025, 0.051]
        y = m * x + b + noise
        # Check the calculated line
        line = Line(x=x)
        predicted = line(m, b)
        np.testing.assert_almost_equal(predicted, y, decimal=1)
        # Create and check the guessed parameters
        guessed_params = line.guess_params(y, edge=None)
        np.testing.assert_almost_equal(guessed_params, (m, b), decimal=1)
        
    def test_linear_combination(self):
        # Prepare test sources
        x = np.linspace(0, 2*np.pi, num=361)
        sources = [np.sin(x), np.sin(2*x)]
        # Produce a combo with 0.5*sin(x) + 0.25*sin(2x) + 2
        lc = LinearCombination(sources=sources)
        out = lc(0.5, 0.25, 2)
        expected = 0.5*sources[0] + 0.25*sources[1] + 2
        np.testing.assert_equal(out, expected)
        # Test param_names property
        pnames = ('weight_0', 'weight_1', 'offset')
        self.assertEqual(lc.param_names, pnames)
    
    def test_gaussian(self):
        # Prepare intpu data
        Es = np.linspace(0, 10, num=101)
        gaussian = Gaussian(x=Es)
        out = gaussian(1, 5.1, 0.2)
        # Check the resulting output
        self.assertEqual(np.argmax(out), 51)
    
    def test_L3_curve(self):
        # Prepare input data
        Es = np.arange(855, 871, 0.25)
        l3 = L3Curve(x=Es, num_peaks=1)
        # confirm right number of param names
        names = ('height_0', 'center_0', 'sigma_0',
                 'sig_height', 'sig_center', 'sig_sigma',
                 'offset')
        self.assertEqual(l3.param_names, names)
        # Fit a 1-peak curve
        params = (1, 860, 0.1, 0, 862.5, 1, -2)
        out = l3(*params)
        self.assertEqual(np.argmax(out), 20)
    
    def test_K_curve(self):
        # Prepare input data
        Es = np.linspace(8250, 8650, num=100)
        k_curve = KCurve(x=Es)
        # Confirm correct number of parameter names
        names = ('scale', 'voffset', 'E0',  # Global parameters
                 'sigw',  # Sharpness of the edge sigmoid
                 'bg_slope', # Linear reduction in background optical_depth
                 'ga', 'gb', 'gc',  # Gaussian height, center and width
        )
        self.assertEqual(k_curve.param_names, names)
        # Check a predicted curve
        KParams = namedtuple('KParams', k_curve.param_names)
        params = KParams(scale=1, voffset=1, E0=8353,
                         sigw=0.5, bg_slope=-0.001,
                         ga=0.5, gb=3, gc=5)
        out = k_curve(*params)
        # Check some properties of the predicted curve determined manually
        self.assertEqual(np.argmax(out), 27)
        self.assertAlmostEqual(np.min(out), 1.050, places=3)
        self.assertAlmostEqual(np.max(out), 2.306, places=3)
    
    def test_guess_kedge_params(self):
        """Given an arbitrary K-edge spectrum, can we guess reasonable
        starting parameters for fitting?"""
        # Load spectrum
        spectrum = pd.read_csv(os.path.join(SSRL_DIR, 'NCA_xanes.csv'),
                               index_col=0, sep=' ', names=['Absorbance'])
        edge = edges.NCANickelKEdge()
        Es = np.array(spectrum.index)
        ODs = np.array(spectrum.values)[:,0]
        OD_df = pd.Series(ODs, index=Es)
        # Do the guessing
        kcurve = KCurve(Es)
        result = kcurve.guess_params(OD_df, edge=edge)
        # Check resultant guessed parameters
        self.assertAlmostEqual(result.scale, 0.244, places=2)
        self.assertAlmostEqual(result.voffset, 0.45, places=2)
        self.assertEqual(result.E0, edge.E_0)
        self.assertAlmostEqual(result.ga, 0.75, places=2)
        self.assertAlmostEqual(result.gb, 5, places=1)
        self.assertAlmostEqual(result.bg_slope, 0, places=5)
        # Check non-named tuple
        result = kcurve.guess_params(OD_df, edge=edge, named_tuple=False)
        self.assertIsInstance(result, tuple)
        self.assertNotIn('KParams', str(result))
        # Check mismatched array shapes
        kcurve = KCurve(Es)
        with self.assertRaises(ValueError) as cm:
            bad_ODs = np.linspace(0, 1, num=len(Es)-1)
            kcurve.guess_params(bad_ODs, edge=edge)
        self.assertEqual(str(cm.exception),
                         'Intensities and energies do not have the same shape: (60,) vs (61,)')
    
    def test_prepare_p0(self):
        # Run the function with known inputs
        p0 = (5, 3, 1)
        out = prepare_p0(p0, num_timesteps=4, frame_shape=(256, 128))
        # Prepare expected value
        expected = np.empty(shape=(4, 3, 256, 128))
        expected[:,0,:,:] = 5
        expected[:,1,:,:] = 3
        expected[:,2,:,:] = 1
        # Check that the arrays match
        np.testing.assert_equal(out, expected)
    
    def test_guess_p0(self):
        x = np.linspace(0, 1)
        line = Line(x)
        spectra = [line(1, 1)]
        guessed_params = guess_p0(func=line, spectra=spectra, quiet=True)
        np.testing.assert_equal(guessed_params, [[1, 1]])
    
    def test_find_whiteline(self):
        x = np.linspace(-1, 1, num=51)
        gauss = Gaussian(x)
        center = 0.2
        params = (1, center, 0.5)
        whiteline = find_whiteline(params=params, curve=gauss)
        self.assertAlmostEqual(whiteline, center)
    
    def test_fit_spectra(self):
        # Define a function to fit
        x = np.linspace(0, 10, num=11)
        line = Line(x)
        real_params = np.array([(2., -3.)])
        real_data = line(*real_params[0])
        spectra = np.array([real_data])
        # Execute the fit
        p0 = np.array([(1, 0)])
        params, residuals = fit_spectra(observations=spectra,
                                        func=line, p0=p0)
        np.testing.assert_almost_equal(params, real_params)
        self.assertTrue(0 < residuals < 1e-9, residuals)
        # Check what happens in only 1-D data are used
        params, residuals = fit_spectra(observations=real_data,
                                        func=line, p0=(1, 0))
        np.testing.assert_almost_equal(params, real_params[0])
        self.assertTrue(0 < residuals < 1e-9, residuals)
    
    def test_fit_spectra_with_bounds(self):
        # Define a function to fit
        x = np.linspace(0, 10, num=11)
        line = Line(x)
        real_params = np.array([(2., -3.)])
        real_data = line(*real_params[0])
        spectra = np.array([real_data])
        bounds = ([3, -2], [np.inf, np.inf])
        # Execute the fit
        p0 = np.array([(4, 0)])
        params, residuals = fit_spectra(observations=spectra,
                                        func=line, p0=p0, bounds=bounds)
        # plt.plot(x, line(*params[0]))
        # plt.plot(x, line(*bounds[0]))
        # plt.plot(x, real_data, linestyle='None', marker='o')
        # plt.show()
        np.testing.assert_almost_equal(params, [(3, -1.8894082)])
        self.assertTrue(0 < residuals < 10, residuals)
        # Check that a warning is raised if the guess is outside of the bounds
        # p0 = np.array([(1, 0)])
        # with warnings.catch_warnings(record=True) as w:
        #     warnings.resetwarnings()
        #     params, residuals = fit_spectra(observations=spectra,
        #                                     func=line, p0=p0, bounds=bounds)
        # self.assertEqual(len(w), 1)
    
    def test_distance_to_bounds(self):
        # In bounds parameters
        result = distance_to_bounds(
            [1, 3],
            ([0, 0], [2, 4]),
        )
        self.assertEqual(result, 0)
        # Out of bounds parameters (below)
        result = distance_to_bounds(
            [-1, 0],
            ([0, 0], [2, 4]),
        )
        self.assertEqual(result, 1)
        # Out of bounds parameters (above)
        result = distance_to_bounds(
            [3, 5],
            ([0, 0], [2, 4]),
        )
        self.assertEqual(result, np.sqrt(2))
    
    def test_is_out_of_bounds(self):
        # In bounds parameters
        result = is_out_of_bounds(
            [1, 3],
            ([0, 0], [2, 4]),
        )
        self.assertFalse(result)
        # Out of bounds parameters (below)
        result = is_out_of_bounds(
            [-1, 0],
            ([0, 0], [2, 4]),
        )
        self.assertTrue(result)
        # Out of bounds parameters (above)
        result = is_out_of_bounds(
            [1, 5],
            ([0, 0], [2, 4]),
        )
        self.assertTrue(result)
    
    def test_fit_sources(self):
        # Prepare some test data
        x = np.linspace(0, 1, num=10)
        line = Line(x)
        p0 = np.array([2, 1]) # m, b
        noise = [0.094, 0.0485, 0.087, 0.004, 0.053, 0.097, 0.015,
                 0.0725, 0.025, 0.051]
        # Do a straight-forward fitting
        y = line(*p0) + noise
        p_fit, res_ = _fit_sources(inputs=[y, p0], func=line)
        np.testing.assert_almost_equal(p_fit, p0, decimal=1)
        self.assertLess(res_, 0.03)
        # Check for precision errors
        with mock.patch('xanespy.fitting.leastsq') as leastsq:
            leastsq.return_value = (p0, None, {}, '', 4)
            with warnings.catch_warnings(record=True) as w:
                warnings.resetwarnings()
                p_fit, res_ = _fit_sources(inputs=[y, p0], func=line)
            self.assertEqual(len(w), 1)
            self.assertIn('Precision errors', str(w[0].message))
        # Check NaN values
        y[3] = np.nan
        p_fit, res_ = _fit_sources(inputs=[y, p0], func=line)
        np.testing.assert_equal(p_fit, [np.nan, np.nan])
        self.assertTrue(math.isnan(res_))
    
    def test_error_function(self):
        x = np.linspace(0, 2*np.pi)
        def func(scale, offset):
            return scale * np.sin(x) + offset
        output = error(func=func, guess=np.array((1, 0)), obs=func(1, 1))
        np.testing.assert_almost_equal(output, np.ones_like(output))
        # Test non-negative constraint, but with only non-negative parameters
        nonnegative = ([0, 0], [np.inf, np.inf])
        output = error(func=func, guess=np.array((1, 1)), obs=func(1, 2), bounds=nonnegative)
        np.testing.assert_almost_equal(output, np.full_like(output, 1.))
        # Test non-negative constraint, including some negative parameters
        output = error(func=func, guess=np.array((-1, 2)), obs=func(1, 2), bounds=nonnegative)
        self.assertEqual(np.min(output), 10)
        # Test non-negative constraint, with a array instead of individual values
        partial_nonnegative = ([-np.inf, 0], [np.inf, np.inf])
        output = error(func=func, guess=np.array((-1, 1)),
                       obs=func(-1, 2), bounds=partial_nonnegative)
        np.testing.assert_almost_equal(output, np.full_like(output, 1))
