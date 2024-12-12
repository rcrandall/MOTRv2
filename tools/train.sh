#!/usr/bin/env bash

python -m torch.distributed.launch --nproc_per_node=1 --use_env src/main.py |& tee -a output.log
