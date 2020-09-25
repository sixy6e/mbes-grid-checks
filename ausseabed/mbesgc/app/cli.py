#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Command line tool that executes quality assurance checks on grid data
    derived from multibeam echosounder data.
"""

import click
import os

from osgeo import gdal


@click.command()
@click.option(
    '-i', '--input-file',
    required=True,
    help='Path to input file')
@click.option(
    '-c', '--check-name',
    required=True,
    help='Name of check to run')
def cli(
        input_file,
        check_name):
    '''Run quality assurance check over input grid file'''
    if not os.path.isfile(input_file):
        click.echo(
            "Input file ({}) does not exist".format(input_file),
            err=True)
        sys.exit(os.EX_NOINPUT)

    src_ds = gdal.Open(input_file)
    if src_ds is None:
        print('Unable to open {}'.format(input_file))
        sys.exit(1)

    for band in range(src_ds.RasterCount):
        band += 1

        src_band = src_ds.GetRasterBand(band)
        src_data_type = src_band.DataType
        src_data_type_name = gdal.GetDataTypeName(src_data_type)
        print("band: {}".format(band))
        print("  data type: {}".format(src_data_type_name))


if __name__ == '__main__':
    cli()
