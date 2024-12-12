FROM 763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-training:1.12.1-gpu-py38-cu113-ubuntu20.04-sagemaker

# Update the conda environment
COPY environment.yaml .

# Make sure we update the base conda environment in the docker container, because when
# we run the training in sagemaker, it will use /opt/conda/bin/python. 
# For local runs, we may want to use a different environment name like "svo", 
# so just replace it inline here when creating the container
RUN sed -i 's/^name:.*/name: base/' environment.yaml
RUN conda env update -f environment.yaml
