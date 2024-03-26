# mbes-grid-checks
Quality Assurance checks for grid data derived from Multi Beam Echo Sounder data

# Installation

Assumes a miniconda Python distribution has been installed.

    git clone https://github.com/ausseabed/mbes-grid-checks
    cd mbes-grid-checks

    conda env create --file conda.yml
    conda activate mbesgc

    pip install .

# Run

Command line usage can be displayed using the `--help` command line arguement. eg;

    $ mbesgc --help
    Usage: mbesgc [OPTIONS]

        Run quality assurance check over input grid file

    Options:
        -i, --input TEXT       Path to input QA JSON file
        -gf, --grid-file TEXT  Path to input grid file (.tif, .bag)
        --help                 Show this message and exit.



# Tests

Unit tests can be run with the following command line

    python -m pytest -s --cov=ausseabed.mbesgc tests/ausseabed/mbesgc/lib
