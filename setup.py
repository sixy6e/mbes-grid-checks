from setuptools import setup, find_packages

setup(
    name='ausseabed.mbesgc',
    namespace_packages=['ausseabed'],
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
    entry_points={
        "gui_scripts": [],
        "console_scripts": [
            'mbesgc = ausseabed.mbesgc.app.cli:cli',
        ],
    },
    packages=['ausseabed.mbesgc'],
    package_data={},
    install_requires=[
        'Click',
        'ausseabed.qajson'
    ],
    tests_require=['pytest'],
)
