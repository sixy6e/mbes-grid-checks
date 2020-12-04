from typing import Type

from .gridcheck import *


all_checks = [
    DensityCheck,
    TvuCheck
]


def get_check(id: str) -> Type:
    '''
    Gets the check class for the given id. Will return None if check not found.
    '''
    check_class = next(
        cc
        for cc in all_checks
        if cc.id == id
    )
    return check_class


def get_all_check_ids():
    '''
    Returns a list of the all check uuids that are supported by
    mbes-grid-checks
    '''
    return [check_class.id for check_class in all_checks]
