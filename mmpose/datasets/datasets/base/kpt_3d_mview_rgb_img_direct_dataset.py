# Copyright (c) OpenMMLab. All rights reserved.
import copy
from abc import ABCMeta, abstractmethod

import json_tricks as json
import numpy as np
from torch.utils.data import Dataset

from mmpose.datasets import DatasetInfo
from mmpose.datasets.pipelines import Compose


class Kpt3dMviewRgbImgDirectDataset(Dataset, metaclass=ABCMeta):
    """Base class for keypoint 3D top-down pose estimation with single-view RGB
    image as the input.

    All fashion datasets should subclass it.
    All subclasses should overwrite:
        Methods:`_get_db`, 'evaluate'

    Args:
        ann_file (str): Path to the annotation file.
        img_prefix (str): Path to a directory where images are held.
            Default: None.
        data_cfg (dict): config
        pipeline (list[dict | callable]): A sequence of data transforms.
        dataset_info (DatasetInfo): A class containing all dataset info.
        coco_style (bool): Whether the annotation json is coco-style.
            Default: True
        test_mode (bool): Store True when building test or
            validation dataset. Default: False.
    """

    def __init__(self,
                 ann_file,
                 img_prefix,
                 data_cfg,
                 pipeline,
                 dataset_info=None,
                 test_mode=False):

        self.image_info = {}
        self.ann_info = {}

        self.ann_file = ann_file
        self.img_prefix = img_prefix
        self.pipeline = pipeline
        self.test_mode = test_mode

        self.ann_info['image_size'] = np.array(data_cfg['image_size'])
        self.ann_info['heatmap_size'] = np.array(data_cfg['heatmap_size'])
        self.ann_info['num_joints'] = data_cfg['num_joints']

        if dataset_info is None:
            raise ValueError(
                'Check https://github.com/open-mmlab/mmpose/pull/663 '
                'for details.')

        dataset_info = DatasetInfo(dataset_info)

        assert self.ann_info['num_joints'] <= dataset_info.keypoint_num
        self.ann_info['flip_pairs'] = dataset_info.flip_pairs
        self.ann_info['flip_index'] = dataset_info.flip_index
        self.ann_info['upper_body_ids'] = dataset_info.upper_body_ids
        self.ann_info['lower_body_ids'] = dataset_info.lower_body_ids
        self.ann_info['joint_weights'] = dataset_info.joint_weights
        self.ann_info['skeleton'] = dataset_info.skeleton
        self.sigmas = dataset_info.sigmas
        self.dataset_name = dataset_info.dataset_name

        self.load_config(data_cfg)

        self.db = []

        self.pipeline = Compose(self.pipeline)

    def load_config(self, data_cfg):
        """Initialize dataset attributes according to the config.

        Override this method to set dataset specific attributes.
        """
        self.num_joints = data_cfg['num_joints']
        self.num_cameras = data_cfg['num_cameras']
        self.seq_frame_interval = data_cfg.get('seq_frame_interval', 1)
        self.subset = data_cfg.get('subset', 'train')
        self.need_2d_label = data_cfg.get('need_2d_label', False)
        self.need_camera_param = True

    @staticmethod
    def _get_mapping_id_name(imgs):
        """
        Args:
            imgs (dict): dict of image info.

        Returns:
            tuple: Image name & id mapping dicts.

            - id2name (dict): Mapping image id to name.
            - name2id (dict): Mapping image name to id.
        """
        id2name = {}
        name2id = {}
        for image_id, image in imgs.items():
            file_name = image['file_name']
            id2name[image_id] = file_name
            name2id[file_name] = image_id

        return id2name, name2id

    @abstractmethod
    def _get_db(self):
        """Load dataset."""
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, cfg, outputs, res_folder, metric, *args, **kwargs):
        """Evaluate keypoint results."""
        raise NotImplementedError

    @staticmethod
    def _write_keypoint_results(keypoints, res_file):
        """Write results into a json file."""

        with open(res_file, 'w') as f:
            json.dump(keypoints, f, sort_keys=True, indent=4)

    def __len__(self):
        """Get the size of the dataset."""
        return len(self.db) // self.num_cameras

    def _get_single_camera(self, idx):
        """Get the sample given index."""
        results = copy.deepcopy(self.db[idx])
        results['ann_info'] = self.ann_info
        return self.pipeline(results)

    def __getitem__(self, idx):
        """Get the sample given index."""
        results = []
        # return self.pipeline(results)
        for k in range(self.num_cameras):
            single_result = self._get_single_camera(self.num_cameras * idx + k)
            results.append(single_result)

        return results