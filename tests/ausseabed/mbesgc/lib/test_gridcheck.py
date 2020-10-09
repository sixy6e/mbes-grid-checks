import unittest

from ausseabed.mbesgc.lib.gridcheck import DensityCheck


class TestDensityCheck(unittest.TestCase):

    def test_result_hist_chunk_merge(self):
        res_a = {
            0: 3,
            1: 5,
            2: 7,
            5: 8,
            10: 1
        }
        res_b = {
            0: 1,
            2: 3,
            4: 2,
            5: 3,
            9: 1
        }

        c_a = DensityCheck([])
        c_a.density_histogram = res_a

        c_b = DensityCheck([])
        c_b.density_histogram = res_b

        c_a.merge_results(c_b)

        self.assertEqual(c_a.density_histogram[0], 4)
        self.assertEqual(c_a.density_histogram[1], 5)
        self.assertEqual(c_a.density_histogram[2], 10)
        self.assertEqual(c_a.density_histogram[4], 2)
        self.assertEqual(c_a.density_histogram[5], 11)
        self.assertEqual(c_a.density_histogram[9], 1)
        self.assertEqual(c_a.density_histogram[10], 1)
