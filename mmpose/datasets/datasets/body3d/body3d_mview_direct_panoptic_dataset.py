# Copyright (c) OpenMMLab. All rights reserved.
import copy
import glob
import json
import os
import os.path as osp
import pickle
import warnings
from collections import OrderedDict

import mmcv
import numpy as np
from mmcv import Config

from mmpose.core.camera import SimpleCamera
from mmpose.datasets.builder import DATASETS
from mmpose.datasets.datasets.base import Kpt3dMviewRgbImgDirectDataset


@DATASETS.register_module()
class Body3DMviewDirectPanopticDataset(Kpt3dMviewRgbImgDirectDataset):
    """Panoptic dataset for top-down hand pose estimation.

    `Hand Keypoint Detection in Single Images using Multiview
    Bootstrapping' CVPR'2017
    More details can be found in the `paper
    <https://arxiv.org/abs/1704.07809>`__ .

    The dataset loads raw features and apply specified transforms
    to return a dict containing the image tensors and other information.

    Panoptic keypoint indexes::

        'neck': 0,
        'nose': 1,
        'mid-hip': 2,
        'l-shoulder': 3,
        'l-elbow': 4,
        'l-wrist': 5,
        'l-hip': 6,
        'l-knee': 7,
        'l-ankle': 8,
        'r-shoulder': 9,
        'r-elbow': 10,
        'r-wrist': 11,
        'r-hip': 12,
        'r-knee': 13,
        'r-ankle': 14,
        'l-eye': 15,
        'l-ear': 16,
        'r-eye': 17,
        'r-ear': 18,

    Args:
        ann_file (str): Path to the annotation file.
        img_prefix (str): Path to a directory where images are held.
            Default: None.
        data_cfg (dict): config
        pipeline (list[dict | callable]): A sequence of data transforms.
        dataset_info (DatasetInfo): A class containing all dataset info.
        test_mode (bool): Store True when building test or
            validation dataset. Default: False.
    """
    ALLOWED_METRICS = {'mpjpe', 'mAP'}

    def __init__(self,
                 ann_file,
                 img_prefix,
                 data_cfg,
                 pipeline,
                 dataset_info=None,
                 test_mode=False):

        if dataset_info is None:
            warnings.warn(
                'dataset_info is missing. '
                'Check https://github.com/open-mmlab/mmpose/pull/663 '
                'for details.', DeprecationWarning)
            cfg = Config.fromfile('configs/_base_/datasets/panoptic_hand2d.py')
            dataset_info = cfg._cfg_dict['dataset_info']

        super().__init__(
            ann_file,
            img_prefix,
            data_cfg,
            pipeline,
            dataset_info=dataset_info,
            test_mode=test_mode)

        self.load_config(data_cfg)
        self.ann_info['use_different_joint_weights'] = False

        self.db_file = f'group_{self.subset}_cam{self.num_cameras}.pkl'
        self.db_file = os.path.join(self.img_prefix, self.db_file)

        if osp.exists(self.db_file):
            info = pickle.load(open(self.db_file, 'rb'))
            assert info['seq_list'] == self.seq_list
            assert info['seq_frame_interval'] == self.seq_frame_interval
            assert info['cam_list'] == self.cam_list
            self.db = info['db']
        else:
            self.db = self._get_db()
            info = {
                'seq_list': self.seq_list,
                'seq_frame_interval': self.seq_frame_interval,
                'cam_list': self.cam_list,
                'db': self.db
            }
            pickle.dump(info, open(self.db_file, 'wb'))

        self.db_size = len(self.db)
        self.db = self._get_db()

        print(f'=> load {len(self.db)} samples')

    def load_config(self, data_cfg):
        """Initialize dataset attributes according to the config.

        Override this method to set dataset specific attributes.
        """
        self.num_joints = data_cfg['num_joints']
        assert self.num_joints <= 19
        self.seq_list = data_cfg['seq_list']
        self.cam_list = data_cfg['cam_list']
        self.num_cameras = data_cfg['num_cameras']
        assert self.num_cameras == len(self.cam_list)
        self.seq_frame_interval = data_cfg.get('seq_frame_interval', 1)
        self.subset = data_cfg.get('subset', 'train')
        self.need_2d_label = data_cfg.get('need_2d_label', False)
        self.need_camera_param = True
        self.root_id = data_cfg.get('root_id', 0)

    def _get_cam(self, seq):
        cam_file = osp.join(self.img_prefix, seq,
                            'calibration_{:s}.json'.format(seq))
        with open(cam_file) as cfile:
            calib = json.load(cfile)

        M = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
        cameras = {}
        for cam in calib['cameras']:
            if (cam['panel'], cam['node']) in self.cam_list:
                sel_cam = {}
                R_w2c = np.array(cam['R']).dot(M)
                T_w2c = np.array(cam['t']).reshape((3, 1)) * 10.0  # cm to mm
                R_c2w = R_w2c.T
                T_c2w = -R_w2c.T @ T_w2c
                sel_cam['R'] = R_c2w.tolist()
                sel_cam['T'] = T_c2w.tolist()
                sel_cam['K'] = cam['K'][:2]
                distCoef = cam['distCoef']
                sel_cam['k'] = [distCoef[0], distCoef[1], distCoef[4]]
                sel_cam['p'] = [distCoef[2], distCoef[3]]
                cameras[(cam['panel'], cam['node'])] = sel_cam

        return cameras

    def _get_db(self):
        width = 1920
        height = 1080
        db = []
        for seq in self.seq_list:
            cameras = self._get_cam(seq)
            curr_anno = osp.join(self.img_prefix, seq,
                                 'hdPose3d_stage1_coco19')
            anno_files = sorted(glob.iglob('{:s}/*.json'.format(curr_anno)))

            for i, file in enumerate(anno_files):
                if i % self.seq_frame_interval == 0:
                    with open(file) as dfile:
                        bodies = json.load(dfile)['bodies']
                    if len(bodies) == 0:
                        continue

                    for k, cam_param in cameras.items():
                        single_view_camera = SimpleCamera(cam_param)
                        postfix = osp.basename(file).replace('body3DScene', '')
                        prefix = '{:02d}_{:02d}'.format(k[0], k[1])
                        image_file = osp.join(seq, 'hdImgs', prefix,
                                              prefix + postfix)
                        image_file = image_file.replace('json', 'jpg')

                        all_poses_3d = []
                        all_poses_vis_3d = []
                        all_poses = []
                        all_poses_vis = []
                        for body in bodies:
                            pose3d = np.array(body['joints19']).reshape(
                                (-1, 4))
                            pose3d = pose3d[:self.num_joints]

                            joints_vis = pose3d[:, -1] > 0.1

                            if not joints_vis[self.root_id]:
                                continue

                            # Coordinate transformation
                            M = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0],
                                          [0.0, 1.0, 0.0]])
                            pose3d[:, 0:3] = pose3d[:, 0:3].dot(M) * 10.0

                            all_poses_3d.append(pose3d[:, 0:3])
                            all_poses_vis_3d.append(
                                np.repeat(
                                    np.reshape(joints_vis, (-1, 1)), 3,
                                    axis=1))

                            pose2d = np.zeros((pose3d.shape[0], 2))
                            # get pose_2d from pose_3d
                            pose2d[:, :2] = single_view_camera.world_to_pixel(
                                pose3d[:, :3])
                            x_check = np.bitwise_and(pose2d[:, 0] >= 0,
                                                     pose2d[:, 0] <= width - 1)
                            y_check = np.bitwise_and(
                                pose2d[:, 1] >= 0, pose2d[:, 1] <= height - 1)
                            check = np.bitwise_and(x_check, y_check)
                            joints_vis[np.logical_not(check)] = 0

                            all_poses.append(pose2d)
                            all_poses_vis.append(
                                np.repeat(
                                    np.reshape(joints_vis, (-1, 1)), 2,
                                    axis=1))

                        if len(all_poses_3d) > 0:
                            db.append({
                                'image_file':
                                osp.join(self.img_prefix, image_file),
                                'joints_3d':
                                all_poses_3d,
                                'joints_3d_vis':
                                all_poses_vis_3d,
                                'joints_2d':
                                all_poses,
                                'joints_2d_vis':
                                all_poses_vis,
                                'camera':
                                cam_param
                            })
        return db

    def evaluate(self,
                 outputs,
                 res_folder,
                 metric='mpjpe',
                 logger=None,
                 **kwargs):

        metrics = metric if isinstance(metric, list) else [metric]
        for _metric in metrics:
            if _metric not in self.ALLOWED_METRICS:
                raise ValueError(
                    f'Unsupported metric "{_metric}" for mpi-inf-3dhp dataset.'
                    f'Supported metrics are {self.ALLOWED_METRICS}')

        res_file = osp.join(res_folder, 'result_keypoints.json')

        mmcv.dump(outputs, res_file)

        eval_list = []
        gt_num = self.db_size // self.num_cameras
        assert len(outputs) == gt_num, 'number mismatch'

        total_gt = 0
        for i in range(gt_num):
            index = self.num_cameras * i
            db_rec = copy.deepcopy(self.db[index])
            joints_3d = db_rec['joints_3d']
            joints_3d_vis = db_rec['joints_3d_vis']

            if len(joints_3d) == 0:
                continue

            pred = outputs[i].copy()
            pred = pred[pred[:, 0, 3] >= 0]
            for pose in pred:
                mpjpes = []
                for (gt, gt_vis) in zip(joints_3d, joints_3d_vis):
                    vis = gt_vis[:, 0] > 0
                    mpjpe = np.mean(
                        np.sqrt(
                            np.sum((pose[vis, 0:3] - gt[vis])**2, axis=-1)))
                    mpjpes.append(mpjpe)
                min_gt = np.argmin(mpjpes)
                min_mpjpe = np.min(mpjpes)
                score = pose[0, 4]
                eval_list.append({
                    'mpjpe': float(min_mpjpe),
                    'score': float(score),
                    'gt_id': int(total_gt + min_gt)
                })

            total_gt += len(joints_3d)

        mpjpe_threshold = np.arange(25, 155, 25)
        aps = []
        recs = []
        for t in mpjpe_threshold:
            ap, rec = self._eval_list_to_ap(eval_list, total_gt, t)
            aps.append(ap)
            recs.append(rec)

        name_value_tuples = []
        for _metric in metrics:
            if _metric == 'mpjpe':
                stats_names = ['RECALL 500mm', 'MPJPE 500mm']
                info_str = list(
                    zip(stats_names, [
                        self._eval_list_to_recall(eval_list, total_gt),
                        self._eval_list_to_mpjpe(eval_list)
                    ]))
            elif _metric == 'mAP':
                stats_names = [
                    'AP 25', 'AP 50', 'AP 75', 'AP 100', 'AP 125', 'AP 150',
                    'mAP', 'AR 25', 'AR 50', 'AR 75', 'AR 100', 'AR 125',
                    'AR 150', 'mAR'
                ]
                mAP = np.array(aps).mean()
                mAR = np.array(recs).mean()
                info_str = list(zip(stats_names, aps + [mAP] + recs + [mAR]))
            else:
                raise NotImplementedError
            name_value_tuples.extend(info_str)

        return OrderedDict(name_value_tuples)

    @staticmethod
    def _eval_list_to_ap(eval_list, total_gt, threshold):
        eval_list.sort(key=lambda k: k['score'], reverse=True)
        total_num = len(eval_list)

        tp = np.zeros(total_num)
        fp = np.zeros(total_num)
        gt_det = []
        for i, item in enumerate(eval_list):
            if item['mpjpe'] < threshold and item['gt_id'] not in gt_det:
                tp[i] = 1
                gt_det.append(item['gt_id'])
            else:
                fp[i] = 1
        tp = np.cumsum(tp)
        fp = np.cumsum(fp)
        recall = tp / (total_gt + 1e-5)
        precise = tp / (tp + fp + 1e-5)
        for n in range(total_num - 2, -1, -1):
            precise[n] = max(precise[n], precise[n + 1])

        precise = np.concatenate(([0], precise, [0]))
        recall = np.concatenate(([0], recall, [1]))
        index = np.where(recall[1:] != recall[:-1])[0]
        ap = np.sum((recall[index + 1] - recall[index]) * precise[index + 1])

        return ap, recall[-2]

    @staticmethod
    def _eval_list_to_mpjpe(eval_list, threshold=500):
        eval_list.sort(key=lambda k: k['score'], reverse=True)
        gt_det = []

        mpjpes = []
        for i, item in enumerate(eval_list):
            if item['mpjpe'] < threshold and item['gt_id'] not in gt_det:
                mpjpes.append(item['mpjpe'])
                gt_det.append(item['gt_id'])

        return np.mean(mpjpes) if len(mpjpes) > 0 else np.inf

    @staticmethod
    def _eval_list_to_recall(eval_list, total_gt, threshold=500):
        gt_ids = [e['gt_id'] for e in eval_list if e['mpjpe'] < threshold]

        return len(np.unique(gt_ids)) / total_gt