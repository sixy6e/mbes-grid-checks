'''
Manages process of executing checks
'''

from typing import Optional, Dict, List, Any
from osgeo import gdal
import numpy as np
import numpy.ma as ma
import os

from .check_utils import get_check
from .data import InputFileDetails, BandType
from .tiling import get_tiles, Tile
from .gridcheck import GridCheck


class Executor:

    def __init__(
            self,
            input_file_details: List[InputFileDetails],
            check_classes):
        self.input_file_details = input_file_details
        self.tile_size_x = 2000
        self.tile_size_y = 2000
        self.checks = check_classes

        # used to store the results of each check as the checks are run
        # across multiple tiles
        self.check_result_cache = {}

        self.spatial_export = False
        self.spatial_export_location = None
        self.spatial_qajson = True

    def _load_band_tile(self, filename: str, band_index: int, tile: Tile):
        src_ds = gdal.Open(filename)
        if src_ds is None:
            raise RuntimeError(f"Could not open {filename}")

        src_band = src_ds.GetRasterBand(band_index)
        band_data = np.array(src_band.ReadAsArray(
            tile.min_x,
            tile.min_y,
            tile.max_x - tile.min_x,
            tile.max_y - tile.min_y
        ))

        # we need to mask the nodata values otherwise whatever value is used
        # for nodata will appear in the results
        nodata = src_band.GetNoDataValue()
        if nodata is None:
            return band_data
        else:
            masked_band_data = ma.masked_where(band_data == nodata, band_data)
            return masked_band_data

    def _load_data(self, ifd: InputFileDetails, tile: Tile):
        '''
        Loads the 3 input bands for the given tile
        '''
        depth_file, depth_band_idx = ifd.get_band(BandType.depth)
        density_file, density_band_idx = ifd.get_band(BandType.density)
        uncertainty_file, uncertainty_band_idx = ifd.get_band(
            BandType.uncertainty)

        depth_data = self._load_band_tile(
            depth_file, depth_band_idx, tile)
        density_data = self._load_band_tile(
            density_file, density_band_idx, tile)
        uncertainty_data = self._load_band_tile(
            uncertainty_file, uncertainty_band_idx, tile)

        density_data = density_data.astype(int)

        return (depth_data, density_data, uncertainty_data)

    def _get_output_file_location(
            self,
            ifd: InputFileDetails,
            check: GridCheck) -> str:
        if self.spatial_export_location is None:
            return None
        check_path = os.path.join(ifd.get_filename(), check.name)
        return os.path.join(self.spatial_export_location, check_path)

    def _run_checks(
        self,
        ifd: InputFileDetails,
        tile: Tile,
        depth_data,
        density_data,
        uncertainty_data,
        is_stopped=None,
    ):
        '''
        Runs each of the checks assigned to each file (via the
        InputFileDetails) on the loaded data arrays
        '''
        for check_id, check_params in ifd.check_ids_and_params:
            if is_stopped is not None and is_stopped():
                return

            check_class = get_check(check_id, self.checks)
            if check_class is None:
                # then the check is not supported by this tool
                # so skip and move on
                continue
            check = check_class(check_params)

            check.spatial_export = self.spatial_export
            check.spatial_export_location = self._get_output_file_location(
                ifd, check)
            check.spatial_qajson = self.spatial_qajson

            check.check_started()
            check.run(
                ifd,
                tile,
                depth_data,
                density_data,
                uncertainty_data
            )
            check.check_ended()

            # if this check has already been run on a different tile we need
            # to merge the results together. Then when all tiles have been run
            # we'll have a single entry for each check in `check_result_cache`
            # that is the result of all tiles merged
            if (ifd, check_id) in self.check_result_cache:
                last_check = self.check_result_cache[(ifd, check_id)]
                check.merge_results(last_check)
            self.check_result_cache[(ifd, check_id)] = check

    def __update_progress(self, progress_callback, progress):
        if progress_callback is None:
            return
        else:
            progress_callback(progress)

    def run(
        self,
        progress_callback=None,
        qajson_update_callback=None,
        is_stopped=None
    ):
        # clear out any previously run checks
        self.check_result_cache = {}

        # collect list of input files, and the list of tiles to be used for
        # each of these input files
        files_and_tiles = []

        # build up a list of all files, and the tiles that need to be loaded
        # and processed for each file
        total_tile_count = 0
        for input_file_detail in self.input_file_details:
            tiles = get_tiles(
                min_x=0,
                min_y=0,
                max_x=input_file_detail.size_x,
                max_y=input_file_detail.size_y,
                size_x=self.tile_size_x,
                size_y=self.tile_size_y,
            )
            total_tile_count += len(tiles)
            file_and_tile = (input_file_detail, tiles)
            files_and_tiles.append(file_and_tile)

        processed_tile_count = 0
        self.__update_progress(progress_callback, 0)
        # loop over each input file
        for (ifd, tiles) in files_and_tiles:
            # and for each input file loop over the necessary tiles
            # It's much more performant do only load the data for each tile
            # once, and then run all the checks over the loaded tile
            # before moving onto the next
            for _, tile in enumerate(tiles):
                if is_stopped is not None and is_stopped():
                    return

                depth_data, density_data, uncertainty_data = self._load_data(
                    ifd,
                    tile
                )

                self._run_checks(
                    ifd,
                    tile,
                    depth_data,
                    density_data,
                    uncertainty_data,
                    is_stopped
                )
                processed_tile_count += 1
                self.__update_progress(
                    progress_callback,
                    processed_tile_count / total_tile_count
                )
