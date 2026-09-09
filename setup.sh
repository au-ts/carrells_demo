#!/usr/bin/env sh

cd ./dep/dynamic-microkit && \
nix develop --command bash -c "python build_sdk.py --skip-tar --boards=x86_64_generic_vtx --sel4=../sel4 --configs=smp-debug" && \
pip install ./dep/microkit_sdf_gen
