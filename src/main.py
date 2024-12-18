# ------------------------------------------------------------------------
# Copyright (c) 2022 megvii-research. All Rights Reserved.
# ------------------------------------------------------------------------
# Modified from Deformable DETR (https://github.com/fundamentalvision/Deformable-DETR)
# Copyright (c) 2020 SenseTime. All Rights Reserved.
# ------------------------------------------------------------------------
# Modified from DETR (https://github.com/facebookresearch/detr)
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
# ------------------------------------------------------------------------



import argparse
import datetime
import random
import time
from pathlib import Path
import os
import boto3

import numpy as np
import torch
from torch.utils.data import DataLoader

from util.tool import load_model
import util.misc as utils
import datasets.samplers as samplers
from datasets import build_dataset
from engine import train_one_epoch_mot
from models import build_model

import hydra
from omegaconf import DictConfig
import tarfile

def download_from_s3(s3_path, local_path):
  """Downloads a file from an S3 path to a local path.

  Args:
    s3_path: The full S3 path to the file (e.g., 's3://my-bucket/path/to/file.txt').
    local_path: The local path where the file should be saved.
  """
  try:
    s3 = boto3.client('s3')
    bucket_name = s3_path.split('/')[2]  # Extract bucket name
    s3_key = '/'.join(s3_path.split('/')[3:])  # Extract key (path within bucket)

    print(f"Attempt download s3://{bucket_name}/{s3_key} to {local_path}")
    s3.download_file(bucket_name, s3_key, local_path)
    print(f"Downloaded {s3_key} from S3 bucket {bucket_name} to {local_path}")
  except Exception as e:
    print(f"Error downloading file: {e}")


@hydra.main(config_name="config")
def main(args: DictConfig) -> None:
    utils.init_distributed_mode(args)
    print("git:\n  {}\n".format(utils.get_sha()))

    # Determine if we're running in Sagemaker, and if so, use the correct pretrained model
    # path and dataset paths
    if "SM_TRAINING_ENV" in os.environ:
        if utils.get_local_rank() == 0:
            # download the pretrained_s3 to local
            args.pretrained = os.path.join(os.environ['SM_MODEL_DIR'], os.path.basename(args.pretrained_s3))
            download_from_s3(args.pretrained_s3, args.pretrained)

            # print("Extracting training data")
            # targz_file = os.path.join(os.environ['SM_CHANNEL_TRAIN'], os.path.basename(args.mot_path_s3))
            # with tarfile.open(targz_file, 'r:gz') as tar:
            #     tar.extractall(path=os.environ['SM_CHANNEL_TRAIN'])
            # args.mot_path = os.path.join(os.environ['SM_CHANNEL_TRAIN'], "MOT_datasets")
            # print("Extracted training data!")

            args.mot_path = os.path.join(os.environ['SM_CHANNEL_TRAIN'])

            print(f"Contents of {os.environ['SM_CHANNEL_TRAIN']}:")
            for filename in os.listdir(os.environ['SM_CHANNEL_TRAIN']):
                print(f" - {filename}")
            
            print(f"mot_path: {args.mot_path}")
        
        torch.distributed.barrier()  # Ensures all processes wait for rank 0 to finish
        

    if args.frozen_weights is not None:
        assert args.masks, "Frozen training is meant for segmentation only"
    print(args)

    if args.rank == 0 and args.use_wandb and args.wandb_key is not None:
        import wandb
        wandb.login(key=args.wandb_key)
        wandb.init(
            project=args.experiment_name,
        )
    else:
        wandb = None


    device = torch.device(args.device)

    # fix the seed for reproducibility
    seed = args.seed + utils.get_rank()
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    model, criterion, postprocessors = build_model(args)
    model.to(device)

    model_without_ddp = model
    n_parameters = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print('number of params:', n_parameters)

    dataset_train = build_dataset(image_set='train', args=args)

    if args.distributed:
        if args.cache_mode:
            sampler_train = samplers.NodeDistributedSampler(dataset_train)
        else:
            sampler_train = samplers.DistributedSampler(dataset_train)
    else:
        sampler_train = torch.utils.data.RandomSampler(dataset_train)

    batch_sampler_train = torch.utils.data.BatchSampler(
        sampler_train, args.batch_size, drop_last=True)
    collate_fn = utils.mot_collate_fn
    data_loader_train = DataLoader(dataset_train, batch_sampler=batch_sampler_train,
                                   collate_fn=collate_fn, num_workers=args.num_workers,
                                   pin_memory=True)

    def match_name_keywords(n, name_keywords):
        out = False
        for b in name_keywords:
            if b in n:
                out = True
                break
        return out

    param_dicts = [
        {
            "params":
                [p for n, p in model_without_ddp.named_parameters()
                 if not match_name_keywords(n, args.lr_backbone_names) and not match_name_keywords(n, args.lr_linear_proj_names) and p.requires_grad],
            "lr": args.lr,
        },
        {
            "params": [p for n, p in model_without_ddp.named_parameters() if match_name_keywords(n, args.lr_backbone_names) and p.requires_grad],
            "lr": args.lr_backbone,
        },
        {
            "params": [p for n, p in model_without_ddp.named_parameters() if match_name_keywords(n, args.lr_linear_proj_names) and p.requires_grad],
            "lr": args.lr * args.lr_linear_proj_mult,
        }
    ]
    if args.sgd:
        optimizer = torch.optim.SGD(param_dicts, lr=args.lr, momentum=0.9,
                                    weight_decay=args.weight_decay)
    else:
        optimizer = torch.optim.AdamW(param_dicts, lr=args.lr,
                                      weight_decay=args.weight_decay)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, args.lr_drop)

    if args.distributed:
        model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[args.gpu])
        model_without_ddp = model.module

    if args.frozen_weights is not None:
        checkpoint = torch.load(args.frozen_weights, map_location='cpu')
        model_without_ddp.detr.load_state_dict(checkpoint['model'])

    if args.pretrained is not None:
        model_without_ddp = load_model(model_without_ddp, args.pretrained)

    output_dir = Path(args.output_dir)
    if args.resume:
        if args.resume.startswith('https'):
            checkpoint = torch.hub.load_state_dict_from_url(
                args.resume, map_location='cpu', check_hash=True)
        else:
            checkpoint = torch.load(args.resume, map_location='cpu')
        missing_keys, unexpected_keys = model_without_ddp.load_state_dict(checkpoint['model'], strict=False)
        unexpected_keys = [k for k in unexpected_keys if not (k.endswith('total_params') or k.endswith('total_ops'))]
        if len(missing_keys) > 0:
            print('Missing Keys: {}'.format(missing_keys))
        if len(unexpected_keys) > 0:
            print('Unexpected Keys: {}'.format(unexpected_keys))
        if not args.eval and 'optimizer' in checkpoint and 'lr_scheduler' in checkpoint and 'epoch' in checkpoint:
            import copy
            p_groups = copy.deepcopy(optimizer.param_groups)
            optimizer.load_state_dict(checkpoint['optimizer'])
            for pg, pg_old in zip(optimizer.param_groups, p_groups):
                pg['lr'] = pg_old['lr']
                pg['initial_lr'] = pg_old['initial_lr']
            # print(optimizer.param_groups)
            lr_scheduler.load_state_dict(checkpoint['lr_scheduler'])
            # todo: this is a hack for doing experiment that resume from checkpoint and also modify lr scheduler (e.g., decrease lr in advance).
            args.override_resumed_lr_drop = True
            if args.override_resumed_lr_drop:
                print('Warning: (hack) args.override_resumed_lr_drop is set to True, so args.lr_drop would override lr_drop in resumed lr_scheduler.')
                lr_scheduler.step_size = args.lr_drop
                lr_scheduler.base_lrs = list(map(lambda group: group['initial_lr'], optimizer.param_groups))
            lr_scheduler.step(lr_scheduler.last_epoch)
            args.start_epoch = checkpoint['epoch'] + 1

    print("Start training")
    start_time = time.time()

    dataset_train.set_epoch(args.start_epoch)
    for epoch in range(args.start_epoch, args.epochs):
        if args.distributed:
            sampler_train.set_epoch(epoch)
        train_stats = train_one_epoch_mot(
            model, criterion, data_loader_train, optimizer, device, epoch, args.clip_max_norm, wandb
        )

        lr_scheduler.step()
        if args.output_dir:
            checkpoint_paths = [output_dir / 'checkpoint.pth']
            # extra checkpoint before LR drop and every 5 epochs
            if (epoch + 1) % args.lr_drop == 0 or (epoch + 1) % args.save_period == 0 or (((args.epochs >= 100 and (epoch + 1) > 100) or args.epochs < 100) and (epoch + 1) % 5 == 0):
                checkpoint_paths.append(output_dir / f'checkpoint{epoch:04}.pth')
            for checkpoint_path in checkpoint_paths:
                utils.save_on_master({
                    'model': model_without_ddp.state_dict(),
                    'optimizer': optimizer.state_dict(),
                    'lr_scheduler': lr_scheduler.state_dict(),
                    'epoch': epoch,
                    'args': args,
                }, checkpoint_path)

        dataset_train.step_epoch()
    total_time = time.time() - start_time
    total_time_str = str(datetime.timedelta(seconds=int(total_time)))
    print('Training time {}'.format(total_time_str))


if __name__ == '__main__':

    os.environ["HYDRA_FULL_ERROR"] = "1"
    
    main()