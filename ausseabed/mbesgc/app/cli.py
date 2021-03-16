#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Command line tool that executes quality assurance checks on grid data
    derived from multibeam echosounder data.
"""

import click
import json
import os
import sys

from osgeo import gdal
from typing import Optional, Dict, List, Any

from ausseabed.mbesgc.lib.data import get_input_details, \
    inputs_from_qajson_checks
from ausseabed.mbesgc.lib.executor import Executor
from ausseabed.mbesgc.lib.check_utils import get_all_check_ids, get_check
from ausseabed.mbesgc.lib.allchecks import all_checks
from ausseabed.qajson.parser import QajsonParser
from ausseabed.qajson.model import QajsonCheck


def inputs_from_qajson(check_dicts: List, relative_to: str = None):
    # convert the json dict representation into Qajson classes
    # it's easier to work with these
    qajson_checks = [
        QajsonCheck.from_dict(check_dict)
        for check_dict in check_dicts
    ]

    return inputs_from_qajson_checks(qajson_checks, relative_to)


@click.command()
@click.option(
    '-i', '--input',
    required=False,
    help='Path to input QA JSON file')
@click.option(
    '-gf', '--grid-file',
    required=False,
    help='Path to input grid file (.tif, .bag)')
def cli(
        input,
        grid_file):
    '''Run quality assurance check over input grid file'''

    exe = None

    if grid_file is not None:
        if not os.path.isfile(grid_file):
            click.echo(
                "Grid file ({}) does not exist".format(grid_file),
                err=True)
            sys.exit(os.EX_NOINPUT)

        # build a list of the check ids that will be run, and include default
        # parameters for each one.
        all_check_ids = get_all_check_ids(all_checks)
        all_check_ids_and_params = []
        for check_id in all_check_ids:
            check = get_check(check_id, all_checks)
            check_default_params = check.input_params
            all_check_ids_and_params.append( (check_id, check_default_params) )

        inputs = get_input_details(None, [grid_file])
        for input in inputs:
            input.check_ids_and_params = all_check_ids_and_params

        exe = Executor(inputs, all_checks)

    elif input is not None:
        if not os.path.isfile(input):
            click.echo(
                "Input file ({}) does not exist".format(input),
                err=True)
            sys.exit(os.EX_NOINPUT)
        qajson_folder = os.path.dirname(input)
        with open(input) as jsonfile:
            qajson = json.load(jsonfile)
            output = qajson
            spdatachecks = qajson['qa']['survey_products']['checks']
            inputs = inputs_from_qajson(spdatachecks, qajson_folder)

            exe = Executor(inputs, all_checks)
    else:
        click.echo(
            "'-input' or '--grid-file' command line arg must be provided")
        sys.exit(os.EX_NOINPUT)

    def print_prog(progress):
        click.echo(f"progress = {progress}")
    exe.run(print_prog)

    for check_id, check in exe.check_result_cache.items():
        print()
        print(check_id)
        output = check.get_outputs()
        output_dict = output.to_dict()
        print(json.dumps(output_dict, indent=4))


if __name__ == '__main__':
    cli()
