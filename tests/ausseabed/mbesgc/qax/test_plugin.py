import unittest
from typing import List

from ausseabed.mbesgc.qax.plugin import FileGrouping, MbesGridChecksQaxPlugin

class TestGrouping(unittest.TestCase):

    def test_calculate_grouping(self):
        filename_list: List[str] = [
            ("/test/foo/bar/in2018_c01_CombinedSurface_CUBE_2m_Rev2_depth.tif", "Survey DTMs"),
            ("/test/foo/bar/in2018_c01_CombinedSurface_CUBE_2m_Rev2_density.tif", "Survey DTMs"),
            ("/test/foo/bar/in2018_c01_CombinedSurface_CUBE_2m_Rev2_uncertainty.tif", "Survey DTMs"),
            ("/test/foo/in2018_c02_CombinedSurface_CUBE_2m_Rev2_depth.tif", "Survey DTMs"),
            ("/test/foo/in2018_c02_CombinedSurface_CUBE_2m_Rev2_density.tif", "Survey DTMs"),
            ("/test/foo/in2018_c02_CombinedSurface_CUBE_2m_Rev2_uncertainty.tif", "Survey DTMs"),
            ("/test/foo/in2018_c03_CombinedSurface_CUBE_2m_Rev2.tif", "Survey DTMs"),
            ("/test/pinkcharts/in2018_c02_CombinedSurface_CUBE_2m_Rev2.shp", "Pink Chart"),
            ("/test/pinkcharts/in2018_c01_CombinedSurface_CUBE_2m_Rev2.shp", "Pink Chart"),
            ("/test/pinkcharts/in2018_c03_CombinedSurface_CUBE_2m_Rev2.shp", "Pink Chart")
        ]

        groups = FileGrouping.calculate_groupings(filename_list)

        for g in groups:
            print()
            print(g.grouping_name)
            for f,t in g.files:
                print("    " + f)

    def test_extract_revision(self):
        fn = "foo_bar_r123_xyz"

        plugin = MbesGridChecksQaxPlugin()
        revision = plugin._revision_from_filename(fn)

        self.assertEqual(revision, 'r123')
