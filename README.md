# Fork details
Modified code to use the mmcv implementation of MultiScaleDeformableAttention (from [here](https://mmcv.readthedocs.io/en/latest/_modules/mmcv/ops/multi_scale_deform_attn.html)). Purpose is to avoid requiring the build step which is trickier to set up with Sagemaker. With this change, the step to install MSDeformAttn ops with "make.sh" is not required.

Also modified to use [hydra](https://hydra.cc/docs/intro/) config instead of command-line args.

## Usage
### Setup
* Install pytorch using conda (optional)

    ```bash
    conda create -n motrv2 python=3.7
    conda activate motrv2
    conda install pytorch=1.8.1 torchvision=0.9.1 cudatoolkit=10.2 -c pytorch
    ```

* Other requirements
    ```bash
    pip install -r requirements.txt
    ```
### Dataset preparation

1. Download YOLOX detection from [here](https://drive.google.com/file/d/1cdhtztG4dbj7vzWSVSehLL6s0oPalEJo/view?usp=share_link).
2. Please download [DanceTrack](https://dancetrack.github.io/) and [CrowdHuman](https://www.crowdhuman.org/) and unzip them as follows:

```
/data/Dataset/mot
├── crowdhuman
│   ├── annotation_train.odgt
│   ├── annotation_trainval.odgt
│   ├── annotation_val.odgt
│   └── Images
├── DanceTrack
│   ├── test
│   ├── train
│   └── val
├── det_db_motrv2.json
```

You may use the following command for generating crowdhuman trainval annotation:

```bash
cat annotation_train.odgt annotation_val.odgt > annotation_trainval.odgt
```

### Training

You may download the coco pretrained weight from [Deformable DETR (+ iterative bounding box refinement)](https://github.com/fundamentalvision/Deformable-DETR#:~:text=config%0Alog-,model,-%2B%2B%20two%2Dstage%20Deformable), and modify the `--pretrained` argument to the path of the weight. Then training MOTR on 8 GPUs as following:

```bash 
./tools/train.sh
```
Unlike the original MOTRv2 implementation, this fork uses hydra config, see the config.yaml file for all the configuration options that were previously passed as command line arguments.

# Original README
Refer to https://github.com/megvii-research/MOTRv2 for the original readme on MOTRv2
