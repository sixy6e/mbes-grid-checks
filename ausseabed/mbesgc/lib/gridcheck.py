'''
Definition of Grid Checks implemented in mbesgc
'''
from __future__ import annotations
from enum import Enum
from typing import Optional, Dict, List, Any
from ausseabed.qajson.model import QajsonParam, QajsonOutputs

import numpy as np


class GridCheckState(str, Enum):
    cs_pass = 'pass'
    cs_warning = 'warning'
    cs_fail = 'fail'


class GridCheckResult:
    '''
    Encapsulates the various outputs from a grid check
    '''
    def __init__(
            self,
            state: GridCheckState,
            messages: List = []):
        self.state = state
        self.messages = messages


class GridCheck:
    '''
    Base class for all grid checks
    '''

    def __init__(self, input_params: List[QajsonParam]):
        self.input_params = input_params

    def get_param(self, param_name: str) -> Any:
        ''' Gets the parameter value from the list of QajsonParams. Returns
        None if no parameter found. If multiple parameters share the same
        name, the first will be returned.
        '''
        if len(self.input_params) == 0:
            return None

        param = next(
            param
            for param in self.input_params
            if param.name == param_name
        )
        if param is None:
            return None
        else:
            return param.value

    def run(
            depth,
            density,
            uncertainty,
            progress_callback=None):
        '''
        Abstract function definition for how each check should implement its
        run method.

        Args:
            depth (numpy): Depth/elevation data
            depth (numpy): Density data
            uncertainty (numpy): Uncertainty data
            progress_callback (function): optional callback function to
                indicate progress to caller

        Returns:
            nothing?

        '''
        raise NotImplementedError

    def merge_results(self, last_check: GridCheck) -> None:
        '''
        Abstract function definition for how each check should merge results.

        Checks are run on a tile by tile (chunck of input data) basis. To get
        the complete results the results from each chunk need to be merged.
        This merging needs to be implemented within this function.

        Must be overwritten by child classes
        '''
        raise NotImplementedError

    def get_outputs(self) -> QajsonOutputs:
        '''
        Gets the results of this check in a QaJson format
        '''
        raise NotImplementedError


class DensityCheck(GridCheck):
    '''
    Performs check based on density data and input arrays. This looks to
    determine if each node (grid cell) statisfies a minimum count (the value
    stored in the density layer) and whether a percentage of nodes overall
    satisfy a different minumum count.
    '''

    id = '5e2afd8a-2ced-4de8-80f5-111c459a7175'
    name = 'Density Check'
    version = '1'

    def __init__(self, input_params: List[QajsonParam]):
        super().__init__(input_params)

        self._min_spn = self.get_param('min_soundings_per_node')

        # if any node has fewer soundings than this value, it will fail
        self._min_spn_ap = self.get_param(
            'min_soundings_per_node_at_percentage')

        # if a percentage `_min_spn_p` of all nodes is above a threshold
        # `_min_spn_ap` then this check will also fail
        self._min_spn_p = self.get_param(
            'min_soundings_per_node_percentage')
        self._min_spn_ap = self.get_param(
            'min_soundings_per_node_at_percentage')

    def run(
            depth,
            density,
            uncertainty,
            progress_callback=None):
        # generate histogram of counts
        # unique_vals will be the soundings per node
        # unique_counts is the total number of times the unique_val soundings
        # count was found.
        unique_vals, unique_counts = np.unique(density, return_counts=True)

        hist = {}
        for (val, count) in zip(unique_vals, unique_counts):
            hist[val] = count

        self.density_histogram = hist

    def merge_results(self, last_check: GridCheck):
        # merge the density histogram of the last_check into the current
        # check
        for soundings_count, last_count in last_check.density_histogram.items():
            if soundings_count in self.density_histogram:
                self.density_histogram[soundings_count] += last_count
            else:
                self.density_histogram[soundings_count] = last_count

    def get_outputs(self):
        # TODO
        # TODO
        # TODO
        messages = []
        data = {}
        check_state = None

        result = QajsonOutputs(
            execution=None,
            files=None,
            count=None,
            percentage=None,
            messages=messages,
            data=data,
            check_state=check_state
        )

        return outputs
