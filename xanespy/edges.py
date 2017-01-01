# -*- coding: utf-8 -*-
#
# Copyright © 2016 Mark Wolf
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

"""Descriptions of X-ray energy absorption edge."""

import numpy as np

from xanes_math import k_edge_mask, l_edge_mask


class Edge():
    """An X-ray absorption edge. It is defined by a series of energy
    ranges. All energies are assumed to be in units of
    electron-volts. This class is intended to be extended into K-edge,
    L-edge, etc.

    Attributes
    ---------
    E_0: number - The energy of the absorption edge itself.

    *regions: 3-tuples - All the energy regions. Each tuple is of the
      form (start, end, step) and is inclusive at both ends.

    name: string - A human-readable name for this edge (eg "Ni K-edge")

    pre_edge: 2-tuple (start, stop) - Energy range that defines points
      below the edge region, inclusive.

    post_edge: 2-tuple (start, stop) - Energy range that defines points
      above the edge region, inclusive.

    post_edge_order - What degree polynomial to use for fitting
      the post_edge region.

    map_range: 2-tuple (start, stop) - Energy range used for
      normalizing maps. If not supplied, will be determine from pre-
      and post-edge arguments.

    edge_range: 2-tuple (start, stop) - Energy range used to determine
      the official beginning and edge of the edge itself.
    """
    regions = []
    E_0 = None
    pre_edge = None
    post_edge = None
    map_range = None
    edge_range = None
    post_edge_order = 2
    pre_edge_fit = None

    def all_energies(self):
        energies = []
        for region in self.regions:
            start = region[0]
            stop = region[1]
            step = region[2]
            num = int(stop - start) / step + 1
            energies.append(np.linspace(region[0], region[1], num))
        energies = np.concatenate(energies)
        return sorted(list(set(energies)))

    def energies_in_range(self, norm_range=None):
        if norm_range is None:
            norm_range = (self.map_range[0],
                          self.map_range[1])
        energies = [e for e in self.all_energies()
                    if norm_range[0] <= e <= norm_range[1]]
        return energies

    def _post_edge_xs(self, x):
        """Convert a set of x values to a power series up to an order
        determined by self.post_edge_order."""
        X = []
        for power in range(1, self.post_edge_order+1):
            X.append(x**power)
        # Reshape data for make sklearn regression happy
        X = np.array(X)
        if X.shape == (1,):
            # Single value for x
            X = X.reshape(-1, 1)
        elif X.ndim == 1:
            # Single feature (eg [x, x^2])
            X = X.reshape(1, -1)
        elif X.ndim > 1:
            # Multiple values for x
            X = X.swapaxes(0, 1)
        return X


class LEdge(Edge):
    """An X-ray absorption K-edge corresponding to a 2s or 2p
    transition."""

    def annotate_spectrum(self, ax):
        ax.axvline(x=np.max(self.pre_edge), linestyle='-', color="0.55",
                   alpha=0.4)
        ax.axvline(x=np.min(self.post_edge), linestyle='-', color="0.55",
                   alpha=0.4)
        return ax

    def mask(self, *args, **kwargs):
        """Return a numpy array mask for material that's active at this
        edge. Calculations are done in `xanes_math.l_edge_mask()."""
        return l_edge_mask(*args, edge=self, **kwargs)


class KEdge(Edge):
    """An X-ray absorption K-edge corresponding to a 1s transition."""

    def annotate_spectrum(self, ax):
        ax.axvline(x=self.edge_range[0], linestyle='-', color="0.55",
                   alpha=0.4)
        ax.axvline(x=self.edge_range[1], linestyle='-', color="0.55",
                   alpha=0.4)
        return ax

    def mask(self, *args, **kwargs):
        """Return a numpy array mask for material that's active at this
        edge. Calculations are done in `xanes_math.l_edge_mask()."""
        return k_edge_mask(*args, edge=self, **kwargs)


class NCACobaltLEdge(LEdge):
    E_0 = 793.2
    regions = [
        (770, 775, 1),
        (775, 785, 0.5),
        (785, 790, 1),
    ]
    pre_edge = (770, 775)
    post_edge = (785, 790)
    map_range = (0, 1)
    _peak1 = 780.5


class NCANickelLEdge(LEdge):
    E_0 = 853
    regions = [
        (844, 848, 1),
        (849, 856, 0.25),
        (857, 862, 1),
    ]
    pre_edge = (844, 848)
    post_edge = (857, 862)
    map_range = (0, 1)
    _peak1 = 850.91
    _peak2 = 853.16


class LMOMnKEdge(KEdge):
    regions = [
        (6450, 6510, 20),
        (6524, 6542, 2),
        (6544, 6564, 1),
        (6566, 6568, 2),
        (6572, 6600, 4),
        (6610, 6650, 10),
        (6700, 6850, 50),
    ]


class NCANickelKEdge(KEdge):
    E_0 = 8333
    shell = 'K'
    regions = [
        (8250, 8310, 20),
        (8324, 8344, 2),
        (8344, 8356, 1),
        (8356, 8360, 2),
        (8360, 8400, 4),
        (8400, 8440, 8),
        (8440, 8640, 50),
    ]
    pre_edge = (8249, 8281)
    post_edge = (8440, 8640)
    map_range = (8341, 8358)
    edge_range = (8341, 8358)


class NCANickelKEdge61(NCANickelKEdge):
    regions = [
        (8250, 8310, 15),
        (8324, 8360, 1),
        (8360, 8400, 4),
        (8400, 8440, 8),
        (8440, 8640, 50),
    ]


class NCANickelKEdge62(NCANickelKEdge):
    regions = [
        (8250, 8310, 15),
        (8324, 8360, 1),
        (8360, 8400, 4),
        (8400, 8440, 8),
        (8440, 8690, 50),
    ]


# Dictionaries make it more intuitive to access these edges by element
k_edges = {
    'Ni_NCA': NCANickelKEdge,
    'Ni_NMC': NCANickelKEdge, # They're pretty much the same
    'Mn_LMO': LMOMnKEdge,
}


l_edges = {
    'Ni_NCA': NCANickelLEdge,
}
