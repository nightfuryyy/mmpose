dataset_info = dict(
    dataset_name='CARD',
    paper_info=dict(
        author='Lin, Tsung-Yi and Maire, Michael and '
        'Belongie, Serge and Hays, James and '
        'Perona, Pietro and Ramanan, Deva and '
        r'Doll{\'a}r, Piotr and Zitnick, C Lawrence',
        title='Microsoft coco: Common objects in context',
        container='European conference on computer vision',
        year='2014',
        homepage='http://cocodataset.org/',
    ),
    keypoint_info={
        0:
        dict(
            name='top-left', 
            id=0, 
            color=[51, 153, 255], 
            type='upper', 
            swap='top-right'),
        1:
        dict(
            name='top-right',
            id=1,
            color=[51, 153, 255],
            type='upper',
            swap='top-left'),
        2:
        dict(
            name='bot-right',
            id=2,
            color=[51, 153, 255],
            type='lower',
            swap='bot-left'),
        3:
        dict(
            name='bot-left',
            id=3,
            color=[51, 153, 255],
            type='lower',
            swap='bot-right'),
    },
    skeleton_info={
        0:
        dict(link=('top-left', 'top-right'), id=0, color=[0, 255, 0]),
        1:
        dict(link=('top-right', 'bot-right'), id=1, color=[0, 255, 0]),
        2:
        dict(link=('bot-right', 'bot-left'), id=2, color=[255, 128, 0]),
        3:
        dict(link=('bot-left', 'top-left'), id=3, color=[255, 128, 0]),
    },
    joint_weights=[
        1., 1., 1., 1., 
    ],
    sigmas=[
        0.05, 0.05, 0.05, 0.05
    ]
    )
