# mbes-grid-checks
Quality Assurance checks for grid data derived from Multi Beam Echo Sounder data

# Installation

Assumes a miniconda Python distribution has been installed.

    git clone https://github.com/ausseabed/mbes-grid-checks
    cd mbes-grid-checks

    conda create -y -n mbesgc python=3.7
    conda activate mbesgc

    pip install -r requirements.txt
    conda install -y -c conda-forge --file requirements_conda.txt

# Tests

Unit tests can be run with the following command line

    python -m pytest -s --cov=ausseabed.mbesgc tests/
