import datetime
import os

import boto3
import sagemaker
from sagemaker.debugger import TensorBoardOutputConfig
from sagemaker.pytorch import PyTorch

import hydra
from hydra.utils import get_original_cwd
from omegaconf import DictConfig

@hydra.main(config_name="config")
def main(cfg: DictConfig) -> None:
    # Set up the SageMaker session
    boto3_session = boto3.session.Session(
        profile_name=cfg.profile_name, region_name=cfg.profile_region
    )
    sm_client = boto3_session.client("sagemaker", region_name=boto3_session.region_name)
    sagemaker_session = sagemaker.Session(sagemaker_client=sm_client)

    sts_client = boto3_session.client('sts')
    response = sts_client.get_caller_identity()
    print(f"sts {response}")

    # Get the current UTC time formatted as a string to get a unique job name
    now_utc = datetime.datetime.utcnow()
    time_str = now_utc.strftime("%Y-%m-%dT%H-%M-%SZ")
    job_name = f"{os.environ['USER']}-{cfg['experiment_name'].replace('_','-')}-{time_str}"

    output_path = f"s3://{cfg.sagemaker_base_dir_s3}/experiments/{os.environ['USER']}/{job_name}"
    tensorboard_output_config = TensorBoardOutputConfig(
        s3_output_path=os.path.join(output_path, "tensorboard"),
        container_local_output_path="/opt/ml/output/tensorboard",
    )

    sm_role =f"arn:aws:iam::{cfg.aws_account_id}:role/{cfg.iam_role_name}"

    print(f"Attempting to submit sagemaker job with role {sm_role}, output_path {output_path}")

    # Define the PyTorch estimator
    estimator = PyTorch(
        entry_point="main.py",
        source_dir=hydra.utils.get_original_cwd(), # "." would point to outputs/YYYY-MM-DD/HH-MM-SS because of hydra
        instance_count=1,
        instance_type="ml.p3.16xlarge",  # try ml.p3dn.24xlarge for gpus with 32gb
        volume_size=100,  # GB
        framework_version="2.0",
        py_version="py310",
        output_path=output_path,
        code_location=output_path,
        sagemaker_session=sagemaker_session,
        role=sm_role,
        tensorboard_output_config=tensorboard_output_config,
        checkpoint_s3_uri=os.path.join(output_path, "checkpoints"),
        checkpoint_local_path="/opt/ml/checkpoints",
        model_data=cfg.pretrained_s3
    )

    # Define the data channel. Sagemaker automatically downloads the data at the specified S3 path
    # and it will be available in "/opt/ml/input/data/train" from within the Sagemaker job
    input_data = {
        "train": cfg.mot_path_s3
    }

    # Submit the training job
    estimator.fit(inputs=input_data, wait=False, logs=True, job_name=job_name)

if __name__ == "__main__":
    main()