#!/bin/bash

PY="python3.8"

if [ "$#" -ne 1 ]; then
    echo "Please provide a single argument, which is the image-tag."
    exit 2
fi

image_tag="$1"
echo " image_tag: ${image_tag}"

# ningzho AS account
ada credentials update --account=533267246645 --provider=conduit --role=IibsAdminAccess-DO-NOT-DELETE --once --profile rti

# # Specify an algorithm name
algorithm_name=motion-awareness

# Update for Ring
account=$(aws --profile=rti sts get-caller-identity --query Account --output text)

# Get the region defined in the current configuration (default to us-west-2 if none defined)
region="us-east-1"
ecrname="${account}.dkr.ecr.${region}.amazonaws.com"
fullname="${ecrname}/${algorithm_name}:${image_tag}"

# # register with ECR
ecrtoken=$(aws --region ${region} --profile=rti ecr get-login-password)
sudo docker login --username AWS --password ${ecrtoken} ${ecrname}

# Build the docker image locally with the image name
tar -czh . | docker build -f Dockerfile -t ${algorithm_name} -
docker tag ${algorithm_name} ${fullname}

echo "to push image to ECR run: docker push ${fullname}"
