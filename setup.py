from setuptools import setup, find_packages

setup(
    name='ausseabed.mbesgridchecks',
    version='0.0.1',
    url='https://github.com/ausseabed/mbes-grid-checks',
    author=(
        "Lachlan Hurst;"
        "Matt Boyd;"
    ),
    author_email=(
        "lachlan.hurst@gmail.com;"
        "matt.boyd@csiro.au;"
    ),
    description=(
        'Quality Assurance checks for grid data derived from Multi Beam Echo '
        'Sounder data'
    ),
    packages=find_packages(),
    package_data={},
    install_requires=[],
    tests_require=['pytest'],
)
