from osgeo import gdal, osr, gdal_array
from typing import Tuple, NoReturn, Callable
import numpy as np

from .tiling import get_tiles, Tile


def _default_progress_callback(progress):
    ''' Default progress callback function. Prints % complete to stdout.
    '''
    print(f"Progress = {progress * 100:.1f}")


class GridTransformer:
    ''' Converts raster data into the format expected by MBES Grid Checks and Finder Grid Checks.
    This process takes three separate files, each containing a single band, and outputs a three
    band raster including density, depth, and uncertainty (all 32-bit floats).
    '''

    def __init__(self):
        self.output_datatype = gdal.GDT_Float32
        # set output nodata to -3.4028235e+38
        self.output_nodata = np.finfo(np.float32).min.item()
        print(type(self.output_nodata))
        # data is chunked by tiles with this size
        self.error_messages = []
        self.warning_messages = []

    def _validate_sizes(
            self,
            density: gdal.Dataset,
            depth: gdal.Dataset,
            uncertainty: gdal.Dataset) -> bool:
        if (
            (density.RasterXSize == depth.RasterXSize == uncertainty.RasterXSize) and
            (density.RasterYSize == depth.RasterYSize == uncertainty.RasterYSize)
        ):
            return True
        else:
            sizes = (
                f"Density ({density.RasterXSize, density.RasterYSize})\n"
                f"Depth ({depth.RasterXSize, depth.RasterYSize})\n"
                f"Uncertainty ({uncertainty.RasterXSize, uncertainty.RasterYSize})"
            )
            self.error_messages.append(
                f"Input file raster sizes do not match \n{sizes}")
            return False

    def _validate_datatypes(
            self,
            density: gdal.Band,
            depth: gdal.Band,
            uncertainty: gdal.Band) -> bool:
        ''' Checks to ensure existing datatypes are valid. At this stage all datatypes
        are assumed to be valid as they can be forced into a float32.

        This function will include warning messages when a data type does not match
        the output datatype.
        '''
        output_datatype_name = gdal.GetDataTypeName(self.output_datatype)
        if density is not None and density.DataType != self.output_datatype:
            dtn = gdal.GetDataTypeName(density.DataType)
            self.warning_messages.append(
                f"Density input datatype ({dtn}) does not match output "
                f"({output_datatype_name}) and will be converted."
            )
        if depth is not None and depth.DataType != self.output_datatype:
            dtn = gdal.GetDataTypeName(depth.DataType)
            self.warning_messages.append(
                f"Depth input datatype ({dtn}) does not match output "
                f"({output_datatype_name}) and will be converted."
            )
        if uncertainty is not None and uncertainty.DataType != self.output_datatype:
            dtn = gdal.GetDataTypeName(uncertainty.DataType)
            self.warning_messages.append(
                f"Uncertainty input datatype ({dtn}) does not match output "
                f"({output_datatype_name}) and will be converted."
            )
        return True

    def _get_tile_data(self, tile: Tile, band: gdal.Band):
        ''' Loads the band data for the tile and converts it to the output
        data type. Returns a numpy array
        '''

        band_data = np.array(band.ReadAsArray(
            tile.min_x,
            tile.min_y,
            tile.max_x - tile.min_x,
            tile.max_y - tile.min_y
        ))

        np_out_dt = gdal_array.GDALTypeCodeToNumericTypeCode(
            self.output_datatype)

        nodata = band.GetNoDataValue()
        if nodata is None:
            # convert the input data to the datatype we are going to use for
            # output
            band_data_converted = band_data.astype(np_out_dt)
        else:
            # conversion for data that includes nodata is done via a masked array
            # to prevent issues of converting a nodata value, losing some precision,
            # and having it not match the nodata value exactly (causing nodata to
            # not be nodata!)
            masked_band_data = np.ma.masked_where(
                band_data == nodata, band_data)
            masked_band_data_converted = masked_band_data.astype(np_out_dt)
            masked_band_data_converted.fill_value = self.output_nodata
            band_data_converted = masked_band_data_converted.filled()

        return band_data_converted

    def _get_block_size(
            self,
            density: gdal.Band,
            depth: gdal.Band,
            uncertainty: gdal.Band) -> Tuple[int, int]:
        ''' Gets the block size from the existing datasets. This is used to
        get optimium performance when reading data.
        '''
        # For now it is assumed that all bands will share a common block
        # size. This is likely if they all share the same overall size,
        # and were all produced by the same piece of software.
        bs = depth.GetBlockSize()
        return (bs[0], bs[1])

    def process(
            self,
            density: Tuple[str, int],
            depth: Tuple[str, int],
            uncertainty: Tuple[str, int],
            output: str,
            progress_callback: Callable = None) -> bool:
        '''
        Runs the conversion process from 3 input files containing a single band each to
        one file containing 3 bands.

        Args:
            density: Tuple(str, int): tuple with full file path and the index of the
                band containing density data
            depth: Tuple(str, int): tuple with full file path and the index of the
                band containing depth data
            uncertainty: Tuple(str, int): tuple with full file path and the index of the
                band containing uncertainty data
            output: str: full path to the output file that will be created by this
                process
            progress_callback (function): optional callback function to
                indicate progress to caller

        Returns:
            True if the process was successful, False if not.

        '''
        self.error_messages = []
        self.warning_messages = []
        failed = False
        # use the passed in progress callback function if one defined, otherwise use the
        # default.
        pcb = _default_progress_callback if progress_callback is None else progress_callback
        pcb(0.0)

        ds_density: gdal.Dataset = gdal.Open(density[0])
        ds_depth: gdal.Dataset = gdal.Open(depth[0])
        ds_uncertainty: gdal.Dataset = gdal.Open(uncertainty[0])

        # check all input files so we provide a list of errors instead of just the first one
        # to fail. Will allow user to debug multiple issues at once.
        if ds_density is None:
            failed = True
            self.error_messages.append(
                f"Density input file ({density[0]}) could not be opened")
        if ds_depth is None:
            failed = True
            self.error_messages.append(
                f"Depth input file ({depth[0]}) could not be opened")
        if ds_uncertainty is None:
            failed = True
            self.error_messages.append(
                f"Uncertainty input file ({uncertainty[0]}) could not be opened")

        if not failed:
            # we need all three files to be readable to check that they are all
            # the same size
            failed = not self._validate_sizes(
                ds_density, ds_depth, ds_uncertainty)

        if failed:
            return False

        b_density = ds_density.GetRasterBand(density[1])
        b_depth = ds_depth.GetRasterBand(depth[1])
        b_uncertainty = ds_uncertainty.GetRasterBand(uncertainty[1])

        if b_density is None:
            failed = True
            self.error_messages.append(
                f"Density input band ({density[1]}) could not be opened")
        if b_depth is None:
            failed = True
            self.error_messages.append(
                f"Depth input band ({depth[1]}) could not be opened")
        if b_uncertainty is None:
            failed = True
            self.error_messages.append(
                f"Uncertainty input band ({uncertainty[1]}) could not be opened")

        failed_datatype = not self._validate_datatypes(
            b_density, b_depth, b_uncertainty)

        if failed or failed_datatype:
            return False

        # we've already confirmed that all input files have the same size, so
        # assume depth raster is the size of the input and output
        size_x = ds_depth.RasterXSize
        size_y = ds_depth.RasterYSize
        projection = ds_depth.GetProjection()
        geotransform = ds_depth.GetGeoTransform()

        # create output dataset with 3 bands
        ds_output: gdal.Dataset = gdal.GetDriverByName('GTiff').Create(
            output,
            size_x,
            size_y,
            3,
            self.output_datatype,
            options=['COMPRESS=DEFLATE']
        )
        ds_output.SetProjection(projection)
        ds_output.SetGeoTransform(geotransform)

        # bands are indexed from 1
        b_output_density: gdal.Band = ds_output.GetRasterBand(1)
        b_output_density.SetDescription("density")
        b_output_density.SetNoDataValue(self.output_nodata)

        b_output_depth: gdal.Band = ds_output.GetRasterBand(2)
        b_output_depth.SetDescription("depth")
        b_output_depth.SetNoDataValue(self.output_nodata)

        b_output_uncertainty: gdal.Band = ds_output.GetRasterBand(3)
        b_output_uncertainty.SetDescription("uncertainty")
        b_output_uncertainty.SetNoDataValue(self.output_nodata)

        tile_size_x, tile_size_y = self._get_block_size(
            b_density, b_depth, b_uncertainty)

        tiles = get_tiles(
            0,
            0,
            size_x,
            size_y,
            tile_size_x,
            tile_size_y)

        for i, tile in enumerate(tiles):
            bd_density = self._get_tile_data(tile, b_density)
            bd_depth = self._get_tile_data(tile, b_depth)
            bd_uncertainty = self._get_tile_data(tile, b_uncertainty)

            b_output_density.WriteRaster(
                tile.min_x, tile.min_y,
                tile.width, tile.height,
                bd_density.tobytes(),
                tile.width, tile.height,
                self.output_datatype
            )
            b_output_density.FlushCache()

            b_output_depth.WriteRaster(
                tile.min_x, tile.min_y,
                tile.width, tile.height,
                bd_depth.tobytes(),
                tile.width, tile.height,
                self.output_datatype
            )
            b_output_depth.FlushCache()

            b_output_uncertainty.WriteRaster(
                tile.min_x, tile.min_y,
                tile.width, tile.height,
                bd_uncertainty.tobytes(),
                tile.width, tile.height,
                self.output_datatype
            )
            b_output_uncertainty.FlushCache()

            # update the progress callback
            pcb(i / len(tiles))

        pcb(1.0)
        return True
