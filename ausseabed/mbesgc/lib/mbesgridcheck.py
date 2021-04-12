from typing import Optional, Dict, List, Any
from ausseabed.qajson.model import QajsonParam, QajsonOutputs, QajsonExecution
from ausseabed.mbesgc.lib.data import InputFileDetails
from ausseabed.mbesgc.lib.tiling import Tile

import collections
import numpy as np
import numpy.ma as ma
import scipy.ndimage as ndimage
import geojson
from geojson import MultiPolygon
from osgeo import gdal, ogr, osr
from affine import Affine

from .gridcheck import GridCheck, GridCheckState, GridCheckResult


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
    input_params = [
        QajsonParam("Minimum Soundings per node", 5),
        QajsonParam("Minimum Soundings per node at percentage", 5),
        QajsonParam("Minumum Soundings per node percentage", 95),
    ]

    def __init__(self, input_params: List[QajsonParam]):
        super().__init__(input_params)

        # if any node has fewer soundings than this value, it will fail
        self._min_spn = self.get_param('Minimum Soundings per node')

        # if a percentage `_min_spn_p` of all nodes is above a threshold
        # `_min_spn_ap` then this check will also fail
        self._min_spn_p = self.get_param(
            'Minumum Soundings per node percentage')
        self._min_spn_ap = self.get_param(
            'Minimum Soundings per node at percentage')

        self.tiles_geojson = MultiPolygon()

        # amount of padding to place around failing pixels
        # this simplifies the geometry, and enlarges the failing area that
        # will allow it to be shown in the UI more easily
        self.pixel_growth = 5

    def run(
            self,
            ifd: InputFileDetails,
            tile: Tile,
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
            if isinstance(val, ma.core.MaskedConstant):
                continue
            # following gets serialized to JSON and as numpy types are not
            # supported by default we convert the float32 and int64 types to
            # plain python ints
            hist[int(val)] = int(count)

        self.density_histogram = hist

        bad_cells_mask = density < self._min_spn
        bad_cells_mask.fill_value = False
        bad_cells_mask = bad_cells_mask.filled()
        bad_cells_mask_int8 = bad_cells_mask.astype(np.int8)

        # grow out failed pixels to make them more obvious. We've already
        # calculated the pass/fail stats so this won't impact results.
        bad_cells_mask_int8 = self._grow_pixels(
            bad_cells_mask_int8, self.pixel_growth)

        # simplify distance is calculated as the distance pixels are grown out
        # `ifd.geotransform[1]` is pixel size
        simplify_distance = self.pixel_growth * ifd.geotransform[1]

        src_affine = Affine.from_gdal(*ifd.geotransform)
        tile_affine = src_affine * Affine.translation(
            tile.min_x,
            tile.min_y
        )
        tile_ds = gdal.GetDriverByName('MEM').Create(
            '',
            tile.max_x - tile.min_x,
            tile.max_y - tile.min_y,
            1,
            gdal.GDT_Byte
        )
        # tf = '/Users/lachlan/work/projects/qa4mb/repo/mbes-grid-checks/t.tif'
        # tile_ds = gdal.GetDriverByName('GTiff').Create(
        #     tf,
        #     tile.max_x - tile.min_x,
        #     tile.max_y - tile.min_y,
        #     1,
        #     gdal.GDT_Byte
        # )
        tile_ds.SetGeoTransform(tile_affine.to_gdal())

        tile_band = tile_ds.GetRasterBand(1)
        tile_band.WriteArray(bad_cells_mask_int8, 0, 0)
        tile_band.SetNoDataValue(0)
        tile_band.FlushCache()
        tile_ds.SetProjection(ifd.projection)

        # dst_layername = "POLYGONIZED_STUFF"
        # drv = ogr.GetDriverByName("ESRI Shapefile")
        # dst_ds = drv.CreateDataSource(tf + ".shp")
        # dst_layer = dst_ds.CreateLayer(dst_layername, srs = None )
        ogr_srs = osr.SpatialReference()
        ogr_srs.ImportFromWkt(ifd.projection)

        ogr_driver = ogr.GetDriverByName('Memory')
        ogr_dataset = ogr_driver.CreateDataSource('shapemask')
        ogr_layer = ogr_dataset.CreateLayer('shapemask', srs=ogr_srs)

        # used the input raster data 'tile_band' as the input and mask, if not
        # used as a mask then a feature that outlines the entire dataset is
        # also produced
        gdal.Polygonize(
            tile_band,
            tile_band,
            ogr_layer,
            -1,
            [],
            callback=None
        )

        ogr_simple_driver = ogr.GetDriverByName('Memory')
        ogr_simple_dataset = ogr_simple_driver.CreateDataSource('failed_poly')
        ogr_simple_layer = ogr_simple_dataset.CreateLayer(
            'failed_poly', srs=None)

        self._simplify_layer(ogr_layer, ogr_simple_layer, simplify_distance)

        ogr_srs_out = osr.SpatialReference()
        ogr_srs_out.ImportFromEPSG(4326)
        transform = osr.CoordinateTransformation(ogr_srs, ogr_srs_out)

        for feature in ogr_simple_layer:
            transformed = feature.GetGeometryRef()
            transformed.Transform(transform)

            geojson_feature = geojson.loads(feature.ExportToJson())
            self.tiles_geojson.coordinates.extend(
                geojson_feature.geometry.coordinates
            )

        ogr_simple_dataset.Destroy()
        ogr_dataset.Destroy()

        # # includes only the tile boundaries, used for debug
        # tile_geojson = tile.to_geojson(ifd.projection, ifd.geotransform)
        # self.tiles_geojson.coordinates.append(tile_geojson.coordinates)

    def merge_results(self, last_check: GridCheck):
        '''
        merge the density histogram of the last_check into the current check
        '''
        self.start_time = last_check.start_time

        for soundings_count, last_count in last_check.density_histogram.items():
            if soundings_count in self.density_histogram:
                self.density_histogram[soundings_count] += last_count
            else:
                self.density_histogram[soundings_count] = last_count

        self.tiles_geojson.coordinates.extend(
            last_check.tiles_geojson.coordinates
        )

    def get_outputs(self) -> QajsonOutputs:

        execution = QajsonExecution(
            start=self.start_time,
            end=self.end_time,
            status=self.execution_status,
            error=self.error_message
        )

        if len(self.density_histogram) == 0:
            # there's no data to check, so fail
            return QajsonOutputs(
                execution=execution,
                files=None,
                count=None,
                percentage=None,
                messages=[
                    'No counts were extracted, was a valid raster provided'],
                data=None,
                check_state=GridCheckState.cs_fail
            )

        # sort the list of sounding counts and the number of occurances
        counts = collections.OrderedDict(
            sorted(self.density_histogram.items()))

        messages = []
        data = {}
        check_state = None

        lowest_sounding_count, occurances = next(iter(counts.items()))
        if lowest_sounding_count < self._min_spn:
            c = 0
            for sounding_count, occurances in iter(counts.items()):
                if sounding_count >= self._min_spn:
                    break
                c += occurances
            messages.append(
                f'{c} nodes were found to be under the Minimum Soundings per '
                f'node setting ({self._min_spn})'
            )
            check_state = GridCheckState.cs_fail

        total_soundings = sum(counts.values())
        under_threshold_soundings = 0
        for sounding_count, occurances in counts.items():
            if sounding_count >= self._min_spn_ap:
                break
            under_threshold_soundings += occurances

        percentage_over_threshold = \
            (1.0 - under_threshold_soundings / total_soundings) * 100.0

        if percentage_over_threshold < self._min_spn_p:
            messages.append(
                f'{percentage_over_threshold:.1f}% of nodes were found to have a '
                f'sounding count above {self._min_spn_ap}. This is required to'
                f' be {self._min_spn_p}% of all nodes'
            )
            check_state = GridCheckState.cs_fail

        if check_state is None:
            check_state = GridCheckState.cs_pass

        str_key_counts = collections.OrderedDict()
        for key, val in counts.items():
            str_key_counts[str(key)] = val

        data['chart'] = {
            'type': 'histogram',
            'data': str_key_counts
        }

        data['map'] = self.tiles_geojson

        result = QajsonOutputs(
            execution=execution,
            files=None,
            count=None,
            percentage=None,
            messages=messages,
            data=data,
            check_state=check_state
        )

        return result


class TvuCheck(GridCheck):
    '''
    Total Vertical Uncertainty check. An allowable value is calculated on a
    per node basis that is derived from some constants (constant depth error,
    factor of depth dependent error) and the depth itself. This is then
    compared against the calculated uncertainty value within the data.
    '''

    id = 'b5c0469c-6559-4aea-bf9c-d0b337550e89'
    name = 'Total Vertical Uncertainty Check'
    version = '1'
    input_params = [
        QajsonParam("Constant Depth Error", 0.2),
        QajsonParam("Factor of Depth Dependent Errors", 0.007)
    ]

    def __init__(self, input_params: List[QajsonParam]):
        super().__init__(input_params)

        self._depth_error = self.get_param('Constant Depth Error')
        self._depth_error_factor = self.get_param(
            'Factor of Depth Dependent Errors')

        self.tiles_geojson = MultiPolygon()

        # amount of padding to place around failing pixels
        # this simplifies the geometry, and enlarges the failing area that
        # will allow it to be shown in the UI more easily
        self.pixel_growth = 5

    def merge_results(self, last_check: GridCheck):
        self.start_time = last_check.start_time

        self.total_cell_count += last_check.total_cell_count
        self.failed_cell_count += last_check.failed_cell_count

        self.tiles_geojson.coordinates.extend(
            last_check.tiles_geojson.coordinates
        )

    def run(
            self,
            ifd: InputFileDetails,
            tile: Tile,
            depth,
            density,
            uncertainty,
            progress_callback=None):
        # run check on tile data
        a = self._depth_error
        b = self._depth_error_factor

        # calculate allowable uncertainty based on equation and depth data
        allowable_uncertainty = np.sqrt(a**2 + (b * depth)**2)

        failed_uncertainty = uncertainty > allowable_uncertainty

        # count of all cells/nodes/pixels that are not NaN in the uncertainty
        # array
        self.total_cell_count = int(uncertainty.count())

        failed_uncertainty.fill_value = False
        failed_uncertainty = failed_uncertainty.filled()
        failed_uncertainty_int8 = failed_uncertainty.astype(np.int8)

        # count of cells that failed the check
        self.failed_cell_count = int(failed_uncertainty.sum())
        # fraction_failed = failed_cell_count / total_cell_count
        # print(f"total = {total_cell_count}")
        # print(f"failed_cell_count = {failed_cell_count}")
        # print(f"fraction_failed = {fraction_failed}")

        # grow out failed pixels to make them more obvious. We've already
        # calculated the pass/fail stats so this won't impact results.
        failed_uncertainty_int8 = self._grow_pixels(
            failed_uncertainty_int8, self.pixel_growth)

        # simplify distance is calculated as the distance pixels are grown out
        # `ifd.geotransform[1]` is pixel size
        simplify_distance = self.pixel_growth * ifd.geotransform[1]

        src_affine = Affine.from_gdal(*ifd.geotransform)
        tile_affine = src_affine * Affine.translation(
            tile.min_x,
            tile.min_y
        )
        # tf = '/Users/lachlan/work/projects/qa4mb/repo/mbes-grid-checks/au2.tif'
        # tile_ds = gdal.GetDriverByName('GTiff').Create(
        #     tf,
        #     tile.max_x - tile.min_x,
        #     tile.max_y - tile.min_y,
        #     1,
        #     gdal.GDT_Float32
        # )
        tile_ds = gdal.GetDriverByName('MEM').Create(
            '',
            tile.max_x - tile.min_x,
            tile.max_y - tile.min_y,
            1,
            gdal.GDT_Float32
        )
        tile_ds.SetGeoTransform(tile_affine.to_gdal())

        tile_band = tile_ds.GetRasterBand(1)
        tile_band.WriteArray(allowable_uncertainty, 0, 0)
        tile_band.SetNoDataValue(0)
        tile_band.FlushCache()
        tile_ds.SetProjection(ifd.projection)
        #
        # tf2 = '/Users/lachlan/work/projects/qa4mb/repo/mbes-grid-checks/fu.tif'
        # tile_failed_ds = gdal.GetDriverByName('GTiff').Create(
        #     tf2,
        #     tile.max_x - tile.min_x,
        #     tile.max_y - tile.min_y,
        #     1,
        #     gdal.GDT_Byte
        # )
        tile_failed_ds = gdal.GetDriverByName('MEM').Create(
            '',
            tile.max_x - tile.min_x,
            tile.max_y - tile.min_y,
            1,
            gdal.GDT_Byte
        )
        tile_failed_ds.SetGeoTransform(tile_affine.to_gdal())

        tile_failed_band = tile_failed_ds.GetRasterBand(1)
        tile_failed_band.WriteArray(failed_uncertainty_int8, 0, 0)
        tile_failed_band.SetNoDataValue(0)
        tile_failed_band.FlushCache()
        tile_failed_ds.SetProjection(ifd.projection)

        # dst_layername = "POLYGONIZED_STUFF"
        # drv = ogr.GetDriverByName("ESRI Shapefile")
        # dst_ds = drv.CreateDataSource(tf + ".shp")
        # dst_layer = dst_ds.CreateLayer(dst_layername, srs = None )
        ogr_srs = osr.SpatialReference()
        ogr_srs.ImportFromWkt(ifd.projection)

        ogr_driver = ogr.GetDriverByName('Memory')
        ogr_dataset = ogr_driver.CreateDataSource('shapemask')
        ogr_layer = ogr_dataset.CreateLayer('shapemask', srs=ogr_srs)

        # ogr_driver = ogr.GetDriverByName("ESRI Shapefile")
        # ogr_dataset = ogr_driver.CreateDataSource(tf2 + "_2.shp")
        # ogr_layer = ogr_dataset.CreateLayer("failed_poly", srs=None)

        # used the input raster data 'tile_band' as the input and mask, if not
        # used as a mask then a feature that outlines the entire dataset is
        # also produced
        gdal.Polygonize(
            tile_failed_band,
            tile_failed_band,
            ogr_layer,
            -1,
            [],
            callback=None
        )

        ogr_simple_driver = ogr.GetDriverByName('Memory')
        ogr_simple_dataset = ogr_simple_driver.CreateDataSource('failed_poly')
        ogr_simple_layer = ogr_simple_dataset.CreateLayer(
            'failed_poly', srs=None)

        self._simplify_layer(ogr_layer, ogr_simple_layer, simplify_distance)

        ogr_srs_out = osr.SpatialReference()
        ogr_srs_out.ImportFromEPSG(4326)
        transform = osr.CoordinateTransformation(ogr_srs, ogr_srs_out)

        for feature in ogr_simple_layer:
            # transform feature into epsg:4326 before export to geojson
            transformed = feature.GetGeometryRef()
            transformed.Transform(transform)

            geojson_feature = geojson.loads(feature.ExportToJson())

            self.tiles_geojson.coordinates.extend(
                geojson_feature.geometry.coordinates
            )

        ogr_simple_dataset.Destroy()
        ogr_dataset.Destroy()

    def get_outputs(self) -> QajsonOutputs:

        execution = QajsonExecution(
            start=self.start_time,
            end=self.end_time,
            status=self.execution_status,
            error=self.error_message
        )

        data = {
            "failed_cell_count": self.failed_cell_count,
            "total_cell_count": self.total_cell_count,
            "fraction_failed": self.failed_cell_count / self.total_cell_count,
        }

        data['map'] = self.tiles_geojson

        if self.failed_cell_count > 0:
            percent_failed = (
                self.failed_cell_count / self.total_cell_count * 100
            )
            msg = (
                f"{self.failed_cell_count} nodes failed the TVU check this "
                f"represents {percent_failed:.1f}% of all nodes within data."
            )
            return QajsonOutputs(
                execution=execution,
                files=None,
                count=None,
                percentage=None,
                messages=[msg],
                data=data,
                check_state=GridCheckState.cs_fail
            )
        else:
            return QajsonOutputs(
                execution=execution,
                files=None,
                count=None,
                percentage=None,
                messages=[],
                data=data,
                check_state=GridCheckState.cs_pass
            )


class ResolutionCheck(GridCheck):
    '''
    Determines what areas of the grid satisfy a resolution check. The check
    first calculates a feature detection size (fds) on a per pixel basis, two
    values for this are calculated above and below a threshold depth. In both
    cases the fds value is calculated from the pixels depth and linear equation
    parameters provided as input parameters to this check. eg;

        fds = Depth Multiplier * depth + Depth Constant

    This equation is calculated using different a different Depth Multiplier
    and Depth Constant depending on whether the depth at that location is
    above of below the threshold.

    Once fds has been calculated per pixel a boolean check is performed to find
    pixels where the grid resolution is lower than the fds * feature
    detection multiplier. If any pixel is false, then the QA check fails.

    '''

    id = 'c73119ea-4f79-4001-86e3-11c4cbaaeb2d'
    name = 'Resolution Check'
    version = '1'

    # default values taken from IHO - 1a spec
    input_params = [
        QajsonParam("Feature Detection Size Multiplier", 1.0),
        QajsonParam("Threshold Depth", 40.0),
        QajsonParam("Above Threshold FDS Depth Multiplier", 0.0),
        QajsonParam("Above Threshold FDS Depth Constant", 2),
        QajsonParam("Below Threshold FDS Depth Multiplier", 0.025),
        QajsonParam("Below Threshold FDS Depth Constant", 0)
    ]

    def __init__(self, input_params: List[QajsonParam]):
        super().__init__(input_params)

        self._fds_multiplier = self.get_param(
            'Feature Detection Size Multiplier')

        self._threshold_depth = self.get_param(
            'Threshold Depth')

        self._a_fds_depth_multiplier = self.get_param(
            'Above Threshold FDS Depth Multiplier')
        self._a_fds_depth_constant = self.get_param(
            'Above Threshold FDS Depth Constant')

        self._b_fds_depth_multiplier = self.get_param(
            'Below Threshold FDS Depth Multiplier')
        self._b_fds_depth_constant = self.get_param(
            'Below Threshold FDS Depth Constant')

        self.tiles_geojson = MultiPolygon()

        # amount of padding to place around failing pixels
        # this simplifies the geometry, and enlarges the failing area that
        # will allow it to be shown in the UI more easily
        self.pixel_growth = 5

    def merge_results(self, last_check: GridCheck):
        self.start_time = last_check.start_time

        self.total_cell_count += last_check.total_cell_count
        self.failed_cell_count += last_check.failed_cell_count

        self.tiles_geojson.coordinates.extend(
            last_check.tiles_geojson.coordinates
        )

    def run(
            self,
            ifd: InputFileDetails,
            tile: Tile,
            depth,
            density,
            uncertainty,
            progress_callback=None):
        # run check on tile data

        abs_depth = np.abs(depth)
        abs_threshold_depth = abs(self._threshold_depth)

        # refer to docs at top of class defn, this is described there
        fds = np.piecewise(
            abs_depth,
            [
                abs_depth < abs_threshold_depth,
                abs_depth >= abs_threshold_depth
            ],
            [
                lambda d: self._a_fds_depth_multiplier * d + self._a_fds_depth_constant,
                lambda d: self._b_fds_depth_multiplier * d + self._b_fds_depth_constant
            ]
        )

        fds = np.ma.masked_where(np.ma.getmask(depth), fds)

        self.grid_resolution = ifd.geotransform[1]
        # easier to calc a feature size from a single grid resolution and the
        # FDS multiplier than to rescale the whole fds array
        feature_size = self.grid_resolution / self._fds_multiplier

        # The idea of the standard here is that the deeper the water gets the
        # less ability you have to pick up features on the seafloor and also
        # features become less important the deeper the water gets as under
        # keel clearance for ships becomes less of an issue.
        failed_resolution = fds < feature_size

        # count of all cells/nodes/pixels that are not NaN in the uncertainty
        # array
        self.total_cell_count = int(depth.count())

        # failed_resolution.fill_value = False
        # failed_resolution = failed_resolution.filled()
        failed_resolution_int8 = failed_resolution.astype(np.int8)

        # count of cells that failed the check
        self.failed_cell_count = int(failed_resolution.sum())
        # fraction_failed = failed_cell_count / total_cell_count
        # print(f"total = {total_cell_count}")
        # print(f"failed_cell_count = {failed_cell_count}")
        # print(f"fraction_failed = {fraction_failed}")

        # grow out failed pixels to make them more obvious. We've already
        # calculated the pass/fail stats so this won't impact results.
        failed_resolution_int8 = self._grow_pixels(
            failed_resolution_int8, self.pixel_growth)

        # simplify distance is calculated as the distance pixels are grown out
        # `ifd.geotransform[1]` is pixel size
        simplify_distance = self.pixel_growth * ifd.geotransform[1]

        src_affine = Affine.from_gdal(*ifd.geotransform)
        tile_affine = src_affine * Affine.translation(
            tile.min_x,
            tile.min_y
        )

        # Switch from a masked array to an array with a nodata value, this allows
        # us to include nodata in the gdal output.
        # fds.fill_value = -9999.0
        # fds = fds.filled()

        # tf = '/Users/lachlan/work/projects/qa4mb/repo/mbes-grid-checks/au2.tif'
        # tile_ds = gdal.GetDriverByName('GTiff').Create(
        #     tf,
        #     tile.max_x - tile.min_x,
        #     tile.max_y - tile.min_y,
        #     1,
        #     gdal.GDT_Float32
        # )
        # tild_ds was only ever used to support debugging
        # tile_ds = gdal.GetDriverByName('MEM').Create(
        #     '',
        #     tile.max_x - tile.min_x,
        #     tile.max_y - tile.min_y,
        #     1,
        #     gdal.GDT_Float32
        # )
        # tile_ds.SetGeoTransform(tile_affine.to_gdal())

        # tile_band = tile_ds.GetRasterBand(1)
        # tile_band.WriteArray(fds, 0, 0)
        # tile_band.SetNoDataValue(-9999.0)
        # tile_band.FlushCache()
        # tile_ds.SetProjection(ifd.projection)

        # tf2 = '/Users/lachlan/work/projects/qa4mb/repo/mbes-grid-checks/fu.tif'
        # tile_failed_ds = gdal.GetDriverByName('GTiff').Create(
        #     tf2,
        #     tile.max_x - tile.min_x,
        #     tile.max_y - tile.min_y,
        #     1,
        #     gdal.GDT_Byte
        # )
        tile_failed_ds = gdal.GetDriverByName('MEM').Create(
            '',
            tile.max_x - tile.min_x,
            tile.max_y - tile.min_y,
            1,
            gdal.GDT_Byte
        )
        tile_failed_ds.SetGeoTransform(tile_affine.to_gdal())

        tile_failed_band = tile_failed_ds.GetRasterBand(1)
        tile_failed_band.WriteArray(failed_resolution_int8, 0, 0)
        tile_failed_band.SetNoDataValue(0)
        tile_failed_band.FlushCache()
        tile_failed_ds.SetProjection(ifd.projection)

        # dst_layername = "POLYGONIZED_STUFF"
        # drv = ogr.GetDriverByName("ESRI Shapefile")
        # dst_ds = drv.CreateDataSource(tf + ".shp")
        # dst_layer = dst_ds.CreateLayer(dst_layername, srs = None )
        ogr_srs = osr.SpatialReference()
        ogr_srs.ImportFromWkt(ifd.projection)

        ogr_driver = ogr.GetDriverByName('Memory')
        ogr_dataset = ogr_driver.CreateDataSource('shapemask')
        ogr_layer = ogr_dataset.CreateLayer('shapemask', srs=ogr_srs)

        # ogr_driver = ogr.GetDriverByName("ESRI Shapefile")
        # ogr_dataset = ogr_driver.CreateDataSource(tf2 + "_2.shp")
        # ogr_layer = ogr_dataset.CreateLayer("failed_poly", srs=None)

        # used the input raster data 'tile_band' as the input and mask, if not
        # used as a mask then a feature that outlines the entire dataset is
        # also produced
        gdal.Polygonize(
            tile_failed_band,
            tile_failed_band,
            ogr_layer,
            -1,
            [],
            callback=None
        )

        ogr_simple_driver = ogr.GetDriverByName('Memory')
        ogr_simple_dataset = ogr_simple_driver.CreateDataSource('failed_poly')
        ogr_simple_layer = ogr_simple_dataset.CreateLayer(
            'failed_poly', srs=None)

        self._simplify_layer(ogr_layer, ogr_simple_layer, simplify_distance)

        ogr_srs_out = osr.SpatialReference()
        ogr_srs_out.ImportFromEPSG(4326)
        transform = osr.CoordinateTransformation(ogr_srs, ogr_srs_out)

        for feature in ogr_simple_layer:
            # transform feature into epsg:4326 before export to geojson
            transformed = feature.GetGeometryRef()
            transformed.Transform(transform)

            geojson_feature = geojson.loads(feature.ExportToJson())

            self.tiles_geojson.coordinates.extend(
                geojson_feature.geometry.coordinates
            )

        ogr_simple_dataset.Destroy()
        ogr_dataset.Destroy()

    def get_outputs(self) -> QajsonOutputs:

        execution = QajsonExecution(
            start=self.start_time,
            end=self.end_time,
            status=self.execution_status,
            error=self.error_message
        )

        data = {
            "failed_cell_count": self.failed_cell_count,
            "total_cell_count": self.total_cell_count,
            "fraction_failed": self.failed_cell_count / self.total_cell_count,
            "grid_resolution": self.grid_resolution
        }

        data['map'] = self.tiles_geojson

        if self.failed_cell_count > 0:
            percent_failed = (
                self.failed_cell_count / self.total_cell_count * 100
            )
            msg = (
                f"{self.failed_cell_count} nodes failed the resolution check "
                f"this represents {percent_failed:.1f}% of all nodes within "
                "data."
            )
            return QajsonOutputs(
                execution=execution,
                files=None,
                count=None,
                percentage=None,
                messages=[msg],
                data=data,
                check_state=GridCheckState.cs_fail
            )
        else:
            return QajsonOutputs(
                execution=execution,
                files=None,
                count=None,
                percentage=None,
                messages=[],
                data=data,
                check_state=GridCheckState.cs_pass
            )
