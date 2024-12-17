FROM 763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-training:1.12.1-gpu-py38-cu113-ubuntu20.04-sagemaker

# set FORCE_CUDA because during `docker build` cuda is not accessible
ENV FORCE_CUDA="1"
# This will by default build detectron2 for all common cuda architectures and take a lot more time,
# because inside `docker build`, there is no way to tell which architecture will be used.
ARG TORCH_CUDA_ARCH_LIST="Kepler;Kepler+Tesla;Maxwell;Maxwell+Tegra;Pascal;Volta;Turing"
ENV TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST}"

# Update the conda environment
COPY environment.yaml .

# Make sure we update the base conda environment in the docker container, because when
# we run the training in sagemaker, it will use /opt/conda/bin/python. 
# For local runs, we may want to use a different environment name like "svo", 
# so just replace it inline here when creating the container
RUN sed -i 's/^name:.*/name: base/' environment.yaml
RUN conda env update -f environment.yaml
