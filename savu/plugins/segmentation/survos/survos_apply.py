# Copyright 2014 Diamond Light Source Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from savu.plugins.driver.gpu_plugin import GpuPlugin

"""
.. module:: survos_apply
   :platform: Unix
   :synopsis: A plugin to apply the segmentation generated by SuRVoS

.. moduleauthor:: Mark Bashham <mark.basham@rfi.ac.uk>

"""

import logging
import sys

from pathlib import Path

import fastai.vision as faiv
import numpy as np
import torch.nn.functional as F
from skimage import exposure, img_as_float, img_as_ubyte, io


from savu.plugins.filters.base_filter import BaseFilter
from savu.plugins.driver.gpu_plugin import GpuPlugin
from savu.plugins.utils import register_plugin
from savu.data.plugin_list import CitationInformation


# Need these in the namespace in order to load the model
def bce_loss(logits, labels):
    """Defines the binary cross entropy loss function used when training a U-net on binary data."""
    logits = logits[:,1,:,:].float()
    labels = labels.squeeze(1).float()
    return F.binary_cross_entropy_with_logits(logits, labels)


class BinaryLabelList(faiv.SegmentationLabelList):
    def open(self, fn): return faiv.open_mask(fn)


class BinaryItemList(faiv.SegmentationItemList):
    _label_cls = BinaryLabelList


# force them into the __main__ namespace for pickling time
sys.modules['__main__'].__dict__['bce_loss'] = bce_loss
sys.modules['__main__'].__dict__['BinaryItemList'] = BinaryItemList
sys.modules['__main__'].__dict__['BinaryLabelList'] = BinaryLabelList


def fix_odd_sides(example_image):
    if (list(example_image.size)[0] % 2) != 0:
        example_image = faiv.crop_pad(example_image,
                                      size=(list(example_image.size)[0]+1,
                                            list(example_image.size)[1]),
                                      padding_mode = 'reflection')
    if (list(example_image.size)[1] % 2) != 0:
        example_image = faiv.crop_pad(example_image,
                                      size=(list(example_image.size)[0],
                                            list(example_image.size)[1] + 1),
                                      padding_mode = 'reflection')

@register_plugin
class SurvosApply(BaseFilter, GpuPlugin):
    """
    A plugin to apply Paganin filter (contrast enhancement) on projections.

    :u*param SegmentationModelFile: Location of the config file to \
        be applied. Default: "models/unet.pkl".
    :u*param pattern: Direction to process the data (VOLUME_YZ|VOLUME_XY|VOLUME_XZ). Default: "VOLUME_YZ".
    """

    def __init__(self):
        logging.debug("initialising survos_apply segmentaion")
        logging.debug("Calling super to make sure that all superclases are " +
                      " initialised")
        super(SurvosApply, self).__init__("SurvosApply")


    def get_plugin_pattern(self):
        return self.parameters['pattern']

    def pre_process(self):
        model_path = Path(self.parameters['SegmentationModelFile'])
        # Load the model
        self.learn = faiv.load_learner(model_path.parent, model_path.name)
        # Remove the restriction on the model prediction size
        self.learn.data.single_ds.tfmargs['size'] = None

    def process_frames(self, data):
        # TODO Deal with the 4 different configurations
        # data = img_as_float(data)
        # Convert data to a fastai Image object
        data_pad = data[0]
        img = faiv.Image(faiv.pil2tensor(data_pad, data_pad.dtype))
        fix_odd_sides(img)
        prediction = self.learn.predict(img)
        out = img_as_ubyte(prediction[1][0])
        # return the unpadded size
        return out[0:data_pad.shape[0], 0:data_pad.shape[1]]

    def get_max_frames(self):
        return 'single'

    def get_citation_information(self):
        cite_info = CitationInformation()
        cite_info.description = \
            ("The Segmenation conducted in this dataset was produced through" +
             " the SuRVoS applicaiton")
        cite_info.bibtex = \
            ("@article{luengo2017survos,\n" +
             "title={SuRVoS: super-region volume segmentation workbench},\n" +
             "author={Luengo, Imanol and Darrow, Michele C and Spink, " +
             "Matthew C and Sun, Ying and Dai, Wei and He, Cynthia Y " +
             "and Chiu, Wah and Pridmore, Tony and Ashton, Alun W and Duke, " +
             "Elizabeth MH and others},\n" +
             "journal={Journal of Structural Biology},\n" +
             "volume={198},\n" +
             "number={1},\n" +
             "pages={43--53},\n" +
             "year={2017},\n" +
             "publisher={Elsevier}\n" +
             "}")
        cite_info.endnote = \
            ("%0 Journal Article\n" +
             "%T SuRVoS: super-region volume segmentation workbench\n" +
             "%A Luengo, Imanol\n" +
             "%A Darrow, Michele C\n" +
             "%A Spink, Matthew C\n" +
             "%A Sun, Ying\n" +
             "%A Dai, Wei\n" +
             "%A He, Cynthia Y\n" +
             "%A Chiu, Wah\n" +
             "%A Pridmore, Tony\n" +
             "%A Ashton, Alun W\n" +
             "%A Duke, Elizabeth MH\n" +
             "%J Journal of Structural Biology\n" +
             "%V 198\n" +
             "%N 1\n" +
             "%P 43-53\n" +
             "%@ 1047-8477\n" +
             "%D 2017\n" +
             "%I Elsevier")
        cite_info.doi = "https://doi.org/10.1016/j.jsb.2017.02.007"
        return cite_info
