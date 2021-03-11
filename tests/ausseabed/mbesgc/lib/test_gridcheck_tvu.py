import numpy as np
import unittest

from ausseabed.qajson.model import QajsonParam, QajsonOutputs, QajsonExecution

from ausseabed.mbesgc.lib.gridcheck import GridCheck, GridCheckState, GridCheckResult
from ausseabed.mbesgc.lib.mbesgridcheck import DensityCheck, TvuCheck
from ausseabed.mbesgc.lib.data import InputFileDetails
from ausseabed.mbesgc.lib.tiling import Tile


class TestDensityCheck(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # these objects are often needed by checks, but only for the generation of
        # spatial outputs. These dummy objects can be used where these spatial
        # outputs are not being tested.
        cls.dummy_ifd = InputFileDetails()
        cls.dummy_ifd.size_x = 5
        cls.dummy_ifd.size_y = 5
        cls.dummy_ifd.geotransform = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        cls.dummy_ifd.projection = ('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.01745329251994328,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]')  # noqa

        cls.dummy_tile = Tile(0, 0, 5, 5)

        # set up some dummy data
        mask = [
            [False,  False,  False, False],
            [False,  False,  False, False],
            [False,  False,  False, False],
            [False,  False,  False, True],
            [False,  False,  True, True]
        ]
        depth_data = [
            [-40,  -40,  -40, -40],
            [-40,  -60,  -80, -40],
            [-40,  -60,  -70, -40],
            [-40,  -30,  -70, -40],
            [-40,  -40,  -40, -40]
        ]
        cls.depth = np.ma.array(
            np.array(depth_data, dtype=np.float32),
            mask=mask
        )
        density_data = [
            [10,  1,  9, 9],
            [10,  2, 10, 10],
            [10, 10, 10, 10],
            [10, 10, 10, 10],
            [10, 10, 10, 10],
        ]
        cls.density = np.ma.array(
            np.array(density_data, dtype=np.float32),
            mask=mask
        )
        uncertainty_data = [
            [0.7,  0.7,  0.2, 0.2],
            [0.7,  0.4,  0.2, 0.2],
            [0.2,  0.2,  0.2, 0.9],
            [0.2,  0.2,  0.9, 0.0],
            [0.2,  0.2,  0.2, 0.0]
        ]
        cls.uncertainty = np.ma.array(
            np.array(uncertainty_data, dtype=np.float32),
            mask=mask
        )

    def test_tvu(self):
        input_params = [
            QajsonParam("Constant Depth Error", 0.1),
            QajsonParam("Factor of Depth Dependent Errors", 0.007)
        ]

        check = TvuCheck(input_params)
        check.run(
            ifd=self.dummy_ifd,
            tile=self.dummy_tile,
            depth=self.depth,
            density=self.density,
            uncertainty=self.uncertainty
        )

        # 17 because three of the cells are masked
        self.assertEqual(check.total_cell_count, 17)

        # calculated uncertainty works out to be the following array
        # [0.29732138 0.29732138 0.29732138 0.29732138]
        # [0.29732138 0.4317407  0.5688585  0.29732138]
        # [0.29732138 0.4317407  0.5001     0.29732138]
        # [0.29732138 0.23259409 0.5001     0.29732138]
        # [0.29732138 0.29732138 0.29732138 0.29732138]
        # and these values exceed the actual uncertainty data in 5 locations
        self.assertEqual(check.failed_cell_count, 5)
