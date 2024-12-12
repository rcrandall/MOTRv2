#!/bin/bash

# ningzho AS account
ada credentials update --account=533267246645 --provider=conduit --role=IibsAdminAccess-DO-NOT-DELETE --once --profile rti

account=$(aws sts get-caller-identity --query Account --output text --profile rti)
region="us-east-1"
ecrname="763104351884.dkr.ecr.${region}.amazonaws.com"
ecrtoken=$(aws --region ${region} ecr get-login-password --profile rti)
docker login --username AWS --password ${ecrtoken} ${ecrname}

aws ecr get-login-password --region ${region} --profile rti | docker login --username AWS --password-stdin 763104351884.dkr.ecr.${region}.amazonaws.com

docker pull 763104351884.dkr.ecr.${region}.amazonaws.com/pytorch-training:1.12.1-gpu-py38-cu113-ubuntu20.04-sagemaker
