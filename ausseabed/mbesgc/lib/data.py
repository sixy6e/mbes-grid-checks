'''
Module handles mapping input files of varying types (tif, bag) to conventions
implemented within mdes-grid-checks such as the mapping of band numbers
to what they represent
'''

from enum import Enum
from osgeo import gdal
from typing import Tuple, List, Type
import os
import os.path
from pathlib import Path

from ausseabed.qajson.model import QajsonCheck, QajsonRoot, \
    QajsonParam, QajsonQa, QajsonDataLevel, QajsonInfo, QajsonGroup, \
    QajsonInputs, QajsonFile
from ausseabed.qajson.utils import latest_schema_version

# from ausseabed.mbesgc.lib.gridcheck import GridCheck


class BandType(str, Enum):
    depth = 'depth'
    density = 'density'
    uncertainty = 'uncertainty'
    pinkChart = 'pinkChart'


class InputFileDetails:

    def __init__(self):
        self.size_x = None
        self.size_y = None

        # geotransform of the raster data file. This is needed to georeference
        # the output data arrays later
        self.geotransform = None
        self.projection = None

        self.input_band_details = []

        # pink chart filename, if one was given
        self.pink_chart_filename = None

        # list of check uuids that this input file will be run through
        self.check_ids_and_params = []

        # keep track of the qajson check entry so that results can be written
        # to it.
        self.qajson_check = None

    def add_band_details(
            self,
            input_file: str,
            band_index: int,
            band_type: BandType) -> None:
        ibd = (input_file, band_index, band_type)
        self.input_band_details.append(ibd)

    @property
    def band_count(self):
        return len(self.input_band_details)

    def clear_band_details(self):
        self.input_band_details.clear()

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

    def get_filename(self) -> str:
        ''' Gets the filename (no extension or full path) of from the band
        information.
        '''
        if len(self.input_band_details) == 0:
            return None
        else:
            input_file, _, _ = self.input_band_details[0]
            fn = Path(input_file).stem
            return fn

    def __repr__(self):
        bd = [f'  {fn} {bi} {bt}' for (fn, bi, bt) in self.input_band_details]
        bds = '\n'.join(bd)
        return (
            f'size: {self.size_x}, {self.size_y}\n'
            f'pink chart file: {self.pink_chart_filename}\n'
            f'{bds}'
        )

    def clone(self):
        ''' Returns a new instance of InputFileDetails. Note: does not
        clone input_band_details list.
        '''
        ifd = InputFileDetails()
        ifd.size_x = self.size_x
        ifd.size_y = self.size_y
        ifd.geotransform = self.geotransform
        ifd.projection = self.projection
        ifd.pink_chart_filename = self.pink_chart_filename
        ifd.check_ids_and_params = self.check_ids_and_params
        ifd.qajson_check = self.qajson_check
        # only thing we don't clone
        ifd.check_ids_and_params = []

        return ifd


def _get_tiff_details(input_files):
    '''
    Single tiffs include all 3 bands
    '''
    ifd = InputFileDetails()

    for input_file in input_files:

        raster: gdal.Dataset = gdal.Open(input_file)
        if raster is None:
            raise RuntimeError(
                f'input file {input_file} could not be opened'
            )
        size_x = raster.RasterXSize
        size_y = raster.RasterYSize
        geotransform = raster.GetGeoTransform()
        projection = raster.GetProjection()

        # assumes the size,proj,geotransform of all input bands is the
        # same, which is not enforced when there are multiple input
        # files
        ifd.size_x = size_x
        ifd.size_y = size_y
        ifd.geotransform = geotransform
        ifd.projection = projection

        file_added = False
        for band_index in range(1, raster.RasterCount + 1):
            band: gdal.Band = raster.GetRasterBand(band_index)
            band_name: str = band.GetDescription().lower()
            if 'depth' in band_name:
                ifd.add_band_details(input_file, band_index, BandType.depth)
                file_added = True
            elif 'density' in band_name:
                ifd.add_band_details(input_file, band_index, BandType.density)
                file_added = True
            elif 'uncertainty' in band_name:
                ifd.add_band_details(input_file, band_index, BandType.uncertainty)
                file_added = True

        name_only = Path(input_file).stem.lower()

        if file_added:
            # already added, so skip this
            pass
        elif (ifd.band_count == raster.RasterCount or ifd.band_count == 3):
            # then we were able to identify all available bands based on the names
            pass
        elif raster.RasterCount == 1 and 'depth' in name_only:
            # then the band type is assumed by the filename
            ifd.add_band_details(input_file, 1, BandType.depth)
        elif raster.RasterCount == 1 and 'density' in name_only:
            ifd.add_band_details(input_file, 1, BandType.density)
        elif raster.RasterCount == 1 and 'uncertainty' in name_only:
            ifd.add_band_details(input_file, 1, BandType.uncertainty)
        else:
            # then we need to assume the default ordering of bands
            # 1. depth
            # 2. density
            # 3. uncertainty

            # first clear out anything that may have been added. Users must
            # label all bands, or no labels will be used at all
            ifd.clear_band_details()
            for band_index in range(1, raster.RasterCount):
                if band_index == 1:
                    band_type = BandType.depth
                elif band_index == 2:
                    band_type = BandType.density
                else:
                    band_type = BandType.uncertainty
                ifd.add_band_details(input_file, band_index, band_type)

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
        qajson_check: QajsonCheck,
        inputfiles: List[str],
        relative_to: str = None) -> List[InputFileDetails]:
    '''
    Extracts relevant band numbers, size(px), and appropriate file names
    from list of input files.
    '''
    inputdetails = []

    # update list of input files for relative path if one has been
    # provided
    for i in range(0, len(inputfiles)):
        inputfile = inputfiles[i]
        if not os.path.isfile(inputfile) and relative_to is not None:
            test_rel_file = os.path.join(relative_to, inputfile)
            if os.path.isfile(test_rel_file):
                inputfiles[i] = test_rel_file

    print("inputfiles")
    print(inputfiles)

    if len(inputfiles) == 0:
        raise RuntimeError("No gridded input files provided")

    if (inputfiles[0].lower().endswith('.tif')
            or inputfiles[0].lower().endswith('.tiff')):
        # assume all files are tif files if the first one is
        tifdetails = _get_tiff_details(inputfiles)
        inputdetails.append(tifdetails)
    elif inputfiles[0].lower().endswith('_density.bag'):
        # ignore these bag files, we'll handle these in the next if case
        pass
    elif inputfile[0].lower().endswith('.bag'):
        bagdetails = _get_bag_details(inputfiles[0])
        inputdetails.append(bagdetails)

    # maintain reference to the qajson entity this lot of input files was
    # generated from so we can update the qajson after check is complete.
    for inputdetail in inputdetails:
        inputdetail.qajson_check = qajson_check

    return inputdetails


def inputs_from_qajson_checks(
        qajson_checks: List[QajsonCheck],
        relative_to: str = None) -> List[InputFileDetails]:

    print("def inputs_from_qajson_checks")
    inputs = []
    for qajson_check in qajson_checks:
        check_id = qajson_check.info.id
        grid_filenames = [
            qajson_file.path
            for qajson_file in qajson_check.inputs.files
            if qajson_file.file_type == "Survey DTMs"
        ]
        check_inputs = get_input_details(qajson_check, grid_filenames, relative_to)

        pc_filenames = [
            qajson_file.path
            for qajson_file in qajson_check.inputs.files
            if qajson_file.file_type == "Pink Chart"
        ]

        for ci in check_inputs:
            cid_and_params = (check_id, qajson_check.inputs.params)
            ci.check_ids_and_params.append(cid_and_params)

            if len(pc_filenames) > 0:
                ci.pink_chart_filename = pc_filenames[0]

        inputs.extend(check_inputs)
    return inputs


def qajson_from_inputs(
        input: InputFileDetails,
        check_classes: List[Type['GridCheck']]) -> QajsonRoot:

    checks = []
    for check_class in check_classes:
        info = QajsonInfo(
            id=check_class.id,
            name=check_class.name,
            description=None,
            version=check_class.version,
            group=QajsonGroup("", "", ""),
        )

        input_file_path, _, _ = input.input_band_details[0]
        input_file = QajsonFile(
            path=input_file_path,
            file_type="Survey DTMs",
            description=None
        )

        inputs = QajsonInputs(
            files=[input_file],
            params=check_class.input_params
        )
        check = QajsonCheck(
            info=info,
            inputs=inputs,
            outputs=None
        )
        checks.append(check)

    datalevel = QajsonDataLevel(checks=checks)
    qa = QajsonQa(
        version=latest_schema_version(),
        raw_data=QajsonDataLevel([]),
        survey_products=datalevel,
        chart_adequacy=None
    )
    root = QajsonRoot(qa)

    return root
