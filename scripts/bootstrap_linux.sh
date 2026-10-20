#!/bin/bash

set -e

echo "Installing Fonte dependencies..."

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

echo "Fonte environment initialized."