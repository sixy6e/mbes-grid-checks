'''
Manages process of executing checks
'''

from typing import Optional, Dict, List, Any
from osgeo import gdal
import numpy as np

from .check_utils import all_checks, get_check
from .data import InputFileDetails, BandType
from .tiling import get_tiles, Tile


class Executor:

    def __init__(self, input_file_details: List[InputFileDetails]):
        self.input_file_details = input_file_details
        self.tile_size_x = 2000
        self.tile_size_y = 2000
        self.checks = all_checks

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
        return band_data

    def _load_data(self, ifd: InputFileDetails, tile: Tile):
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

        return (depth_data, density_data, uncertainty_data)

    def _run_checks(
            self,
            ifd: InputFileDetails,
            depth_data,
            density_data,
            uncertainty_data):
        '''
        Runs each of the checks assigned to each file (via the
        InputFileDetails) on the loaded data arrays
        '''
        for check_id in ifd.check_ids:
            check_class = get_check(check_id)
            check = check_class([])

            check.run(depth_data, density_data, uncertainty_data)

    def __update_progress(self, progress_callback, progress):
        if progress_callback is None:
            return
        else:
            progress_callback(progress)

    def run(self, progress_callback=None):

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
        for (ifd, tiles) in files_and_tiles:
            for tile in tiles:
                depth_data, density_data, uncertainty_data = self._load_data(
                    ifd,
                    tile
                )

                self._run_checks(
                    ifd,
                    depth_data,
                    density_data,
                    uncertainty_data
                )
                processed_tile_count += 1
                self.__update_progress(
                    progress_callback,
                    processed_tile_count/total_tile_count
                )
