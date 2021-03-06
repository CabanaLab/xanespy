===============
 Introduction 
===============

Xanespy is a toolkit for interacting with X-ray microscopy data, most
likely collected at a synchrotron beamline. By collecting a set of
frames at multiple X-ray energies, spectral maps are reconstructed to
provide chemical insight. Multiple framesets can be collected
sequentially as part of an *operando* experiment and analyzed
simultaneously in python. Slow operations take advantage of multiple
cores when available.

This project has the following design goals:

- Provide a python toolkit for analysis of X-ray absorbance frames.
- Store data in an open format for easy distribution.

GUI tools (eg. TXM-Wizard) exist for performing this type of
analysis. While convenient, the downside to this approach is the
potential inability to exactly reproduce a given set of steps. Xanespy
does provide an interactive GUI for visualizing the data, but this GUI
does not alter the data or export results. This way, the analysis
steps are caputed either in an IPython notebook or conventional python
script. These steps, together with the original data, should then be
sufficient to reproduce the results exactly.


Installation
============

Xanespy can be installed from the **python package index (PyPI) using pip**

.. code:: bash

   $ pip install xanespy

Development
===========

If you plan to contribute changes to xanespy, installing in developer
mode may be more your style. This will also allow you to run tests and
build documentation.

Installation
------------

Download the source code either using the `SSH`_ or `HTTPS`_ links
(SSH shown below). Assuming you are using conda, here are the
steps. Any version of python >=3.5 should be ok.

.. code:: bash

   $ conda create -n xanespy python=3.6 numpy scipy pyqt
   $ source activate xanespy
   $ git clone git@github.com:canismarko/xanespy.git
   $ pip install -r xanespy/requirements.txt
   $ pip install -e xanespy/

.. _SSH: git@github.com:canismarko/xanespy.git
.. _HTTPS: https://github.com/canismarko/xanespy.git
   
Tests
-----

The easiest way to run unit-tests is with pytest:

.. code:: bash

   $ cd xanespy/
   $ pip install pytest
   $ pytest

Documentation
-------------

The documentation is built using sphinx. To make HTML documents, use the following:

.. code:: bash

   $ pip install -r xanespy/requirements-docs.txt
   $ cd xanespy/docs
   $ make html

X-Ray Absorbance Basics
=======================

Coming soon...


Example Workflow
================

A typical prcocedure for interacting with microscope frame-sets involves the following parts:

- Import the raw data
- Apply corrections and align the images
- Calculate some metric and create maps of it
- Visualize the maps, staticly or interactively.

Example for a single frameset across an X-ray absorbance edge::

    import xanespy

    # Example for importing from SSRL beamline 6-2c
    xanespy.import_ssrl_frameset('<data_dir>', hdf_filename='imported_data.h5')

    # Load a pre-defined XAS edge or create your own subclass xanespy.Edge
    edge = xanespy.k_edges['Ni_NCA']
    # Now load the newly created HDF5 file and the X-ray absorbance edge
    fs = xanespy.XanesFrameset(filename='imported_data.h5', edge=edge)

    # Perform automatic frame alignment
    fs.align_frames(passes=5)
    # Fit the absorbance spectra and extract the edge position (SLOW!)
    fs.fit_spectra()

    # Inspect the result with the built-in Qt5 GUI
    fs.qt_viewer()
