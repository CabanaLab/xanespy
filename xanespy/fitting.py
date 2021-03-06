# -*- coding: utf-8 -*-
#
# Copyright © 2017 Mark Wolfman
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
# along with Xanespy. If not, see <http://www.gnu.org/licenses/>.

"""A collection of callables that can be used for fitting spectra."""


from collections import namedtuple
from multiprocessing import Pool
import warnings
import functools
from typing import Tuple, Callable

import numpy as np
from scipy.optimize import leastsq, curve_fit
import tqdm

from . import exceptions
from .xanes_math import k_edge_jump, iter_indices, foreach
from .utilities import nproc, mp_map


__all__ = ('prepare_p0', 'fit_spectra', 'Curve', 'Line',
           'LinearCombination', 'Gaussian', 'L3Curve', 'KCurve')


def guess_p0(func, spectra, edge=None, quiet=False, ncore=None):
    """Accept a number of spectra and try to get a good guess for initial
    fitting params.
    
    Parameters
    ----------
    func : callable
      The function that will be fit. It must have a ``guess_params``
      method.
    spectra : np.ndarray
      A 2D array with the second dimension representing Energy (or
      whatever the x axis is).
    edge : optional
      An XAS edge.
    ncore : int, optional
      How many processes to use in the pool. See
      :func:`~xanespy.utilities.nproc` for more details.
    
    Returns
    -------
    p0 : np.ndarray
      A 2D array, the first dimension matches ``spectra`` and the
      second dimension corresponds to the number of fitting parameters
      for *func*.
    
    """
    # Prepare a progress bar
    if not quiet:
        spectra = tqdm.tqdm(spectra, desc="Guessing initial params", unit='px')
    # Execute the parameters guessing with multiprocessing
    guess_params = functools.partial(func.guess_params, edge=edge,
                                     named_tuple=False)
    # with Pool(nproc(ncore)) as pool:
    #     p0 = np.array(pool.map(guess_params, spectra, chunksize=2000))
    p0 = mp_map(guess_params, spectra, chunksize=2000)
    return p0


def prepare_p0(p0, frame_shape, num_timesteps=1):
    """Create an initial parameter guess for fitting.
    
    Takes a starting guess (p0) and returns a numpy array with this
    inital guess that matches the frameset.
    
    For example, if a frameset has 12 timesteps and (1024, 2048) frames,
    then a 5-tuple input for ``p0`` will result in a return value with
    shape (12, 5, 1024, 2048)
    
    """
    # Prepare an empty array for the results
    out_shape = (num_timesteps, *frame_shape, len(p0))
    out = np.empty(shape=out_shape)
    # Now populate the fields and put the param axis in the energy spot
    out[:] = p0
    out = np.moveaxis(out, -1, 1)
    return out


def is_out_of_bounds(params, bounds) -> bool:
    """Test if the parameters are within valid bounds."""
    if bounds is not None:
        out_of_bounds = np.any(
            np.logical_or(
                np.less(params, bounds[0]),
                np.greater(params, bounds[1])
            )
        )
    else:
        out_of_bounds = False
    return out_of_bounds


def distance_to_bounds(params, bounds) -> float:
    """Determine the L2 distance from params to the bounds box."""
    zeros = np.zeros_like(params)
    bottom_distance = np.maximum(np.subtract(bounds[0], params), zeros)
    top_distance = np.maximum(np.subtract(params, bounds[1]), zeros)
    all_distance = bottom_distance + top_distance
    total_distance = np.linalg.norm(all_distance)
    return total_distance


def error(guess: np.ndarray, obs: np.ndarray, func: Callable,
          bounds=None) -> np.ndarray:
    """Compare observed and predicted signal and return the difference.
    
    Parameters
    ----------
    guess
      Parameters given to *func* to calculate predicted data.
    obs
      Observed data
    func
      A function that accepts *guess* parameters and returns the predicted signal. It will be used as
      ``predicted = func(*guess)``.
    nonnegative
      If truthy, negative parameters in *guess* will be heavily
      punished. This can also be an array of booleans for each entry
      in *guess* (eg ``(True, False, False, ...)``).
    bounds : 2-tuple of array_like, optional
      Defines upper and lower bounds for fitting. See
      :py:function:``scipy.optimize.curve_fit`` for more details.      
    
    Returns
    -------
    diff
      An array of difference values between the predicted values and
      the observed values.
    
    """
    # if is_out_of_bounds(guess, bounds):
    #     # Punish negative values
    #     diff = np.empty_like(obs)
    #     diff[:] = 1e6
    # else:
    #     # Compare predicted with observed values
    #     predicted = func(*guess)
    #     diff = np.abs(obs - predicted)
    # assert not np.any(np.isnan(diff))
    # Compare predicted with observed values
    predicted = func(*guess)
    diff = np.abs(obs - predicted)
    assert not np.any(np.isnan(diff))
    # Punish out of bounds values
    if is_out_of_bounds(guess, bounds):
        diff += distance_to_bounds(guess, bounds) * 10
    return diff


def _fit_sources(inputs, func, nonnegative=False, bounds=None):
    spectrum, p0 = inputs
    # Don't bother fitting if there's NaN values
    if np.any(np.isnan(spectrum)):
        p_fit = np.empty(p0.shape)
        p_fit[()] = np.nan
        res_ = np.nan
        return p_fit, res_
    # Calculate bounds for fitting if needed
    if bounds is None and nonnegative:
        # Set bounds to 0 and np.inf
        bounds = (
            [0] * len(p0),
            [np.inf] * len(p0)
        )
    elif bounds is None:
        # Set bounds to -np.inf and np.inf
        bounds = (
            [-np.inf] * len(p0),
            [np.inf] * len(p0)
        )
    if is_out_of_bounds(p0, bounds):
        msg = 'Guess {} is outside of bounds {}'.format(p0, bounds)
        warnings.warn(msg, RuntimeWarning)
    # Valid data, so fit the spectrum
    results = leastsq(func=error, x0=p0, args=(spectrum, func, bounds), full_output=True)
    p_fit, cov_x, infodict, mesg, status = results
    # Status 4 is often a sign of mismatched datatypes.
    if status == 4:
        msg = "Precision errors encountered during fitting. Check dtypes."
        warnings.warn(msg, RuntimeWarning)
    # Calculate residual errors
    res_ = (spectrum - func(*p_fit))
    res_ = np.sqrt(np.mean(np.power(res_, 2)))
    return (p_fit, res_)


def find_whiteline(params, curve):
    fit = curve(*params)
    whiteline = curve.x[np.argmax(fit)]
    return whiteline


def fit_spectra(observations, func, p0, nonnegative=False, bounds=None, quiet=False, ncore=None):
    """Fit a function to a series observations.
    
    The shapes of ``observations`` and ``p0`` parameters must match in
    the first dimension, and the callable ``func`` should take a
    series of parameters (the exact number is determined by the last
    dimension of ``p0``) and return a set of observations (the length
    of which is determined by the last dimension of ``observations``).
    
    Parameters
    ----------
    observations : np.ndarray
      A 1- or 2-dimensional array of observations against which to fit
      the function ``func``.
    func : callable, str
      The function that will be used for fitting. It should match
      ``func(p0, p1, ...)`` where p0, p1, etc are the fitting
      parameters. Some useful functions can be found in the
      ``xanespy.fitting`` module.
    p0 : np.ndarray
      Initial guess for parameters, with similar dimensions to a
      frameset. Example, fitting 3 sources (plus offset) for a (1,
      40, 256, 256) 40-energy frameset requires p0 to be (1, 4,
      256, 256).
    nonnegative : bool, optional
      If true (default), negative parameters will be avoided. This
      can also be a tuple to allow for fine-grained control. Eg:
      (True, False) will only punish negative values in the first
      of the two parameters.
    bounds : 2-tuple of array_like, optional
      Defines upper and lower bounds for fitting. See
      :py:function:``scipy.optimize.curve_fit`` for more details.
    quiet : bool, optional
      Whether to suppress the progress bar, etc.
    ncore : int, optional
      How many processes to use in the pool. See
      :func:`~xanespy.utilities.nproc` for more details.
    
    Returns
    -------
    params : numpy.ndarray
      The fit parameters (as frames) for each source.
    residuals : numpy.ndarray
      Residual error after fitting, as maps.
    
    """
    # Massage the datas
    observations = np.array(observations)
    if observations.ndim == 1:
        observations = observations.reshape((1, len(observations)))
        one_dimensional = True
    else:
        one_dimensional = False
    p0 = np.array(p0)
    if p0.ndim == 1:
        p0_shape = (observations.shape[1], p0.shape[0])
        p0 = np.broadcast_to(p0, p0_shape)
    params = np.empty_like(p0)
    # Execute fitting for each spectrum
    indices = iter_indices(observations, desc="Fitting spectra",
                           leftover_dims=1, quiet=quiet)
    # Execute fitting (with multiprocessing)
    payload = zip(observations, p0)
    if not quiet:
        payload = tqdm.tqdm(payload, total=len(observations),
                            desc="Fitting spectra", unit='spctrm')
    with Pool(nproc(ncore)) as pool:
        fitter = functools.partial(_fit_sources, func=func, nonnegative=nonnegative, bounds=bounds)
        params = pool.map(fitter, payload)
    # Prepare the results for returning
    params, residuals = zip(*params)
    params = np.array(params)
    residuals = np.array(residuals)
    if one_dimensional:
        params = params[0]
        residuals = residuals[0]
    return (params, residuals)


class Curve():
    """Base class for a callabled Curve."""
    name = "curve"
    param_names = () # type: Tuple[str, ...]

    def __init__(self, x):
        self.x = x

    def guess_params(self, intensities, edge, named_tuple=True):
        raise NotImplementedError()
    
    def NamedTuple(self, *params):
        """Return a named tuple with the given parameters."""
        Params = namedtuple('{}_params'.format(self.name), self.param_names)
        return Params(*params)


class Line(Curve):
    def guess_params(self, intensities, edge, named_tuple=True):
        # Get slope from first and last points
        m = (intensities[-1] - intensities[0]) / (self.x[-1] - self.x[0])
        # Extrapolate to y-intercept
        b = intensities[0] - m * self.x[0]
        return (m, b)
    
    def __call__(self, m, b):
        return m*self.x + b


class LinearCombination(Curve):
    """Combines other curves into one callable.
    
    The constructor accepts the keyword argument ``sources``, which
    should be a list of numpy arrays. The resulting object can then be
    called with parameters for the weight of each function plus an
    offset. For example, with two sources, the object is called as
    
    .. code:: python
    
        # Prepare the separate sources
        x = np.linspace(0, 2*np.pi, num=361)
        sources = [np.sin(x), np.sin(2*x)]
        
        # Produce a combo with 0.5*sin(x) + 0.25*sin(2x) + 2
        lc = LinearCombination(sources=sources)
        out = lc(0.5, 0.25, 2)
    
    The final output will have the same shape as the sources, which
    should all be the same shape as each other.
    
    """
    name = "linear_combination"
    
    def __init__(self, sources):
        self.sources = sources
    
    def __call__(self, *params):
        # Prepare data and parameters
        out = 0
        p_sources = params[0:-1]
        # Add each source weighted by input parameters
        for coeff, source in zip(p_sources, self.sources):
            out += coeff * source
        # Add global offset
        out += params[-1]
        return out
    
    @property
    def param_names(self):
        names = ['weight_%d' % idx for idx in range(len(self.sources))]
        names.append('offset')
        names = tuple(names)
        return names


class Gaussian(Curve):
    """A Gaussian curve.
    
    Mathematically:
    
    .. math::
        y = a e^{\\frac{-(x-b)**2}{2c^2}}

    Parameters
    ----------
    x : np.ndarray
      Array of x-values to input into the Gaussian function.
    
    """
    name = "gaussian"
    param_names = ('height', 'center', 'width')
    
    def __call__(self, height, center, width):
        x = self.x
        a, b, c = (height, center, width)
        return a * np.exp(-(x-b)**2 / 2 / c**2)


class L3Curve(Curve):
    """An L_3 absorption edge.
    
    This function is a combination of two Gaussian peaks and a step
    function. The first 3 parameters give the height, position and
    width of one peak, and parameters 3:6 give the same for a second
    peak. Parameters 6:9 are height, position and width of an arctan
    step function. Parameter 9 is a global offset.
    
    Parameters
    ----------
    peaks : int, optional
      How many peaks to fit across the edge.
    
    """
    name = "L3-gaussian"
    
    def __init__(self, x, num_peaks=2):
        self.x = x
        self.num_peaks = num_peaks
        self.dtype = x.dtype
    
    def __call__(self, *params):
        Params = namedtuple('L3Params', self.param_names)
        p = Params(*params)
        Es = self.x
        # Add two gaussian fields
        out = np.zeros_like(Es)
        gaussian = Gaussian(x=Es)
        for idx in range(self.num_peaks):
            i = 3*idx
            p_i = p[i:i+3]
            out += gaussian(*p_i)
        # Add arctan step function
        out += p.sig_height * (np.arctan((Es-p.sig_center)*p.sig_sigma) / np.pi + 0.5)
        # Add vertical offset
        out += p.offset
        return out
    
    @property
    def param_names(self):
        pnames = []
        # Add Gaussian parameters
        for idx in range(self.num_peaks):
            pnames.append('height_%d' % idx)
            pnames.append('center_%d' % idx)
            pnames.append('sigma_%d' % idx)
        # Add sigmoid parameters
        pnames.append('sig_height')
        pnames.append('sig_center')
        pnames.append('sig_sigma')
        # Add global y-offset parameter
        pnames.append('offset')
        return tuple(pnames)


class KCurve(Curve):
    """A K absorption edge.
    
    **Fit Parameters:**
    
    scale
      Overall scale factor for curve
    voffset
      Overall vertical offset for the curve
    E0
      Edge position as energy of maximum in second derivative at edge
    sigw
      Sharpenss of the edge sigmoid
    bg_slope
      Linear increase/-decrease in background optical depth
    ga
      Height parameter for Gaussian whiteline peak
    gb
      Center parameter in eV (relative to E0) for Gaussian whiteline
      peak
    gc
      Width parameter for Gaussian whiteline peak
    
    """
    name = "K_edge_curve"
    param_names = (
        'scale', 'voffset', 'E0',  # Global parameters
        'sigw',  # Sharpness of the edge sigmoid
        'bg_slope', # Linear reduction in background optical_depth
        'ga', 'gb', 'gc',  # Gaussian height, center and width
    )
    
    def guess_params(self, intensities, edge, named_tuple=True):
        """Guess initial starting parameters for a k-edge curve. This will
        give a rough estimate, appropriate for giving to the fit_kedge
        function as the starting parameters, p0.
        
        Arguments
        ---------
        intensities : np.ndarray
          An array containing optical_depth data that represents a
          K-edge spectrum. Only 1-dimensional data are currently
          accepted.
        edge : xanespy.edges.KEdge
          An X-ray Edge object, will be used for estimating the actual
          edge energy itself.
        named_tuple : bool, optional
          If truthy, the result will be a named tuple, otherwise a simple tuple.
        
        Returns
        -------
        p0 : tuple
          An iterable with the estimated parameters (see KEdgeParams
          for definition)
        
        """
        Is = np.array(intensities)
        if Is.shape != self.x.shape:
            raise ValueError('Intensities and energies do not have the same shape: {} vs {}'
                             ''.format(Is.shape, self.x.shape))
        # Guess the overall scale and offset parameters
        scale = k_edge_jump(frames=Is, energies=self.x, edge=edge)
        voffset = np.min(Is)
        # Estimate the edge position
        E0 = edge.E_0
        # Estimate the whiteline Gaussian parameters
        ga = 5 * (np.max(Is) - scale - voffset)
        gb = self.x[np.argmax(Is)] - E0
        gc = 2  # Arbitrary choice, should improve this in the future
        # Construct the parameters tuple
        KParams = namedtuple('KParams', self.param_names)
        p0 = KParams(scale=scale, voffset=voffset, E0=E0,
                     sigw=0.5, bg_slope=0,
                     ga=ga, gb=gb, gc=gc)
        if not named_tuple:
            p0 = tuple(p0)
        return p0
    
    def __call__(self, *params):
        # Named tuple to help keep track of parameters
        Params = namedtuple('Params', self.param_names)
        p = Params(*params)
        x = self.x
        # Adjust the x's to be relative to E_0
        x = x - p.E0
        # Sigmoid
        sig = np.arctan(x*p.sigw) / np.pi + 1/2
        # Gaussian
        gaus = p.ga*np.exp(-(x-p.gb)**2/2/p.gc**2)
        # Background
        bg = x * p.bg_slope
        curve = sig + gaus + bg
        curve = p.scale * curve + p.voffset
        return curve
