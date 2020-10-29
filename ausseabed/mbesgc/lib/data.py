'''
Module handles mapping input files of varying types (tif, bag) to conventions
implemented within mdes-grid-checks such as the mapping of band numbers
to what they represent
'''

from enum import Enum
from osgeo import gdal
from typing import Tuple, List
import os
import os.path


class BandType(str, Enum):
    depth = 'depth'
    density = 'density'
    uncertainty = 'uncertainty'


class InputFileDetails:

    def __init__(self):
        self.size_x = None
        self.size_y = None
        self.input_band_details = []

        # list of check uuids that this input file will be run through
        self.check_ids_and_params = []

    def add_band_details(
            self,
            input_file: str,
            band_index: int,
            band_type: BandType) -> None:
        ibd = (input_file, band_index, band_type)
        self.input_band_details.append(ibd)

    def get_band(self, band_type: BandType) -> Tuple[str, int]:
        band_details = next(
            ibd
            for ibd in self.input_band_details
            if ibd[2] == band_type
        )
        if band_details is None:
            return None
        else:
            return band_details[0], band_details[1]

    def __repr__(self):
        bd = [f'  {fn} {bi} {bt}' for (fn, bi, bt) in self.input_band_details]
        bds = '\n'.join(bd)
        return (
            f'size: {self.size_x}, {self.size_y}\n'
            f'{bds}'
        )


def _get_tiff_details(input_file):
    '''
    Single tiffs include all 3 bands
    '''
    raster = gdal.Open(input_file)
    if raster is None:
        raise RuntimeError(
            f'input file {input_file} could not be opened'
        )
    size_x = raster.RasterXSize
    size_y = raster.RasterYSize

    if raster.RasterCount != 3:
        raise RuntimeError(
            f'input file ({input_file}) has {raster.RasterCount} bands and '
            '3 are expected'
        )

    ifd = InputFileDetails()
    ifd.size_x = size_x
    ifd.size_y = size_y
    # band order is assumed based on convention
    ifd.add_band_details(
        input_file,
        1,
        BandType.density
    )
    ifd.add_band_details(
        input_file,
        2,
        BandType.depth
    )
    ifd.add_band_details(
        input_file,
        3,
        BandType.uncertainty
    )
    return ifd


def _get_bag_details(input_file):
    '''
    Bag file bands are split across multiple files. This function identifies
    these files, the bands within them, and their size (in px).
    '''
    fn_no_extension = os.path.splitext(input_file)[0]
    input_file_density = f'{fn_no_extension}_Density.bag'
    if not os.path.isfile(input_file_density):
        raise RuntimeError(
            'Could not find density file for bag , expected '
            f'{input_file_density}'
        )

    depth_raster = gdal.Open(input_file)
    depth_size_x = depth_raster.RasterXSize
    depth_size_y = depth_raster.RasterYSize
    density_raster = gdal.Open(input_file_density)
    density_size_x = density_raster.RasterXSize
    density_size_y = density_raster.RasterYSize

    if depth_size_x != density_size_x or depth_size_y != density_size_y:
        raise RuntimeError(
            f'mismatch in data sizes across depth and density inputs. '
            'Both files must have the same size.'
        )

    if depth_raster.RasterCount != 2:
        raise RuntimeError(
            f'input file ({input_file}) has {depth_raster.RasterCount} bands'
            ' and 2 are expected.'
        )

    if density_raster.RasterCount != 2:
        raise RuntimeError(
            f'input file ({input_file_density}) has '
            f'{density_raster.RasterCount} bands and 2 are expected.'
        )

    ifd = InputFileDetails()
    ifd.size_x = depth_size_x
    ifd.size_y = depth_size_y
    # band order is assumed based on convention
    ifd.add_band_details(
        input_file,
        1,
        BandType.depth
    )
    ifd.add_band_details(
        input_file,
        2,
        BandType.uncertainty
    )
    ifd.add_band_details(
        input_file_density,
        1,
        BandType.density
    )
    return ifd


def get_input_details(
        inputfiles: List[str],
        relative_to: str = None) -> List[str]:
    '''
    Extracts relevant band numbers, size(px), and appropriate file names
    from list of input files.
    '''
    inputdetails = []
    for inputfile in inputfiles:
        if not os.path.isfile(inputfile) and relative_to is not None:
            test_rel_file = os.path.join(relative_to, inputfile)
            if os.path.isfile(test_rel_file):
                inputfile = test_rel_file
        if (inputfile.lower().endswith('.tif')
                or inputfile.lower().endswith('.tiff')):
            tifdetails = _get_tiff_details(inputfile)
            inputdetails.append(tifdetails)
        elif inputfile.lower().endswith('_density.bag'):
            # ignore these bag files, we'll handle these in the next if case
            continue
        elif inputfile.lower().endswith('.bag'):
            bagdetails = _get_bag_details(inputfile)
            inputdetails.append(bagdetails)
        else:
            # ignore all other files passed in
            continue

    return inputdetails
