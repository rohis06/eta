#!/usr/bin/env python
'''
A module that uses an `eta.core.learning.ObjectDetector` to detect objects in
videos or images.

Info:
    type: eta.core.types.Module
    version: 0.1.0

Copyright 2017-2019, Voxel51, Inc.
voxel51.com

Brian Moore, brian@voxel51.com
'''
# pragma pylint: disable=redefined-builtin
# pragma pylint: disable=unused-wildcard-import
# pragma pylint: disable=wildcard-import
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from builtins import *
# pragma pylint: enable=redefined-builtin
# pragma pylint: enable=unused-wildcard-import
# pragma pylint: enable=wildcard-import

import logging
import os
import sys

from eta.core.config import Config, ConfigError
import eta.core.image as etai
import eta.core.learning as etal
import eta.core.module as etam
import eta.core.utils as etau
import eta.core.video as etav


logger = logging.getLogger(__name__)


class ApplyObjectDetectorConfig(etam.BaseModuleConfig):
    '''Module configuration settings.

    Attributes:
        data (DataConfig)
        parameters (ParametersConfig)
    '''

    def __init__(self, d):
        super(ApplyObjectDetectorConfig, self).__init__(d)
        self.data = self.parse_object_array(d, "data", DataConfig)
        self.parameters = self.parse_object(d, "parameters", ParametersConfig)


class DataConfig(Config):
    '''Data configuration settings.

    Inputs:
        video_path (eta.core.types.Video): [None] the input video
        input_labels_path (eta.core.types.VideoLabels): [None] an optional
            input VideoLabels file to which to add the detections generated by
            processing `video_path`
        image_path (eta.core.types.Image): [None] the input image
        input_image_labels_path (eta.core.types.ImageLabels): [None] an
            optional input ImageLabels files to which to add the detections
            generated by processing `image_path`
        images_dir (eta.core.types.ImageFileDirectory): [None] an input
            directory of images
        input_image_set_labels_path (eta.core.types.ImageSetLabels): [None] an
            optional input ImageSetLabels file to which to add the detections
            generated by processing `images_dir`

    Outputs:
        output_labels_path (eta.core.types.VideoLabels): [None] a VideoLabels
            file containing the detections generated by processing `video_path`
        video_features_dir (eta.core.types.VideoObjectsFeaturesDirectory):
            [None] a directory in which to write features for the detected
            objects in each frame of `video_path`. If provided, the detector
            used must support generating features
        output_image_labels_path (eta.core.types.ImageLabels): [None] an
            ImageLabels file containing the detections generated by
            processing `image_path`
        image_features_dir (eta.core.types.ImageObjectsFeaturesDirectory):
            [None] a directory in which to write features for the objects in
            `image_path`. If provided, the detector used must support
            generating features
        output_image_set_labels_path (eta.core.types.ImageSetLabels): [None] an
            ImageSetLabels file containing the detections generated by
            processing `images_dir`
        image_set_features_dir (eta.core.types.ImageSetObjectsFeaturesDirectory):
            [None] a directory in which to write features for the objects in
            the images in `images_dir`.  If provided, the detector used must
            support generating features
    '''

    def __init__(self, d):
        # Single video
        self.video_path = self.parse_string(d, "video_path", default=None)
        self.input_labels_path = self.parse_string(
            d, "input_labels_path", default=None)
        self.output_labels_path = self.parse_string(
            d, "output_labels_path", default=None)
        self.video_features_dir = self.parse_string(
            d, "video_features_dir", default=None)

        # Single image
        self.image_path = self.parse_string(d, "image_path", default=None)
        self.input_image_labels_path = self.parse_string(
            d, "input_image_labels_path", default=None)
        self.output_image_labels_path = self.parse_string(
            d, "output_image_labels_path", default=None)
        self.image_features_dir = self.parse_string(
            d, "image_features_dir", default=None)

        # Directory of images
        self.images_dir = self.parse_string(d, "images_dir", default=None)
        self.input_image_set_labels_path = self.parse_string(
            d, "input_image_set_labels_path", default=None)
        self.output_image_set_labels_path = self.parse_string(
            d, "output_image_set_labels_path", default=None)
        self.image_set_features_dir = self.parse_string(
            d, "image_set_features_dir", default=None)

        self._validate()

    def _validate(self):
        if self.video_path:
            if not self.output_labels_path:
                raise ConfigError(
                    "`output_labels_path` is required when `video_path` is "
                    "set")

        if self.image_path:
            if not self.output_image_labels_path:
                raise ConfigError(
                    "`output_image_labels_path` is required when `image_path` "
                    "is set")

        if self.images_dir:
            if not self.output_image_set_labels_path:
                raise ConfigError(
                    "`output_image_set_labels_path` is required when "
                    "`images_dir` is set")


class ParametersConfig(Config):
    '''Parameter configuration settings.

    Parameters:
        detector (eta.core.types.ObjectDetector): an
            `eta.core.learning.ObjectDetectorConfig` describing the
            `eta.core.learning.ObjectDetector` to use
        objects (eta.core.types.ObjectArray): [None] an array of objects
            describing the labels and confidence thresholds of objects to
            detect. If omitted, all detections emitted by the detector are
            used
    '''

    def __init__(self, d):
        self.detector = self.parse_object(
            d, "detector", etal.ObjectDetectorConfig)
        self.objects = self.parse_object_array(
            d, "objects", ObjectsConfig, default=None)


class ObjectsConfig(Config):
    '''Objects configuration settings.'''

    def __init__(self, d):
        self.labels = self.parse_array(d, "labels", default=None)
        self.threshold = self.parse_number(d, "threshold", default=None)


def _build_object_filter(labels, threshold):
    if threshold is not None:
        threshold = float(threshold)

    if labels is None:
        if threshold is None:
            logger.info("Detecting all objects")
            filter_fcn = lambda obj: True
        else:
            logger.info(
                "Detecting all objects with confidence >= %g", threshold)
            filter_fcn = lambda obj: obj.confidence >= threshold
    else:
        if threshold is None:
            logger.info("Detecting %s", labels)
            filter_fcn = lambda obj: obj.label in labels
        else:
            logger.info(
                "Detecting %s with confidence >= %g", labels, threshold)
            filter_fcn = (
                lambda obj: obj.label in labels and obj.confidence >= threshold
            )

    return filter_fcn


def _build_detection_filter(objects_config):
    if objects_config is None:
        # Return all detections
        return lambda objs: objs

    # Parse object filter
    obj_filters = [
        _build_object_filter(oc.labels, oc.threshold) for oc in objects_config]
    return lambda objs: objs.get_matches(obj_filters)


def _apply_object_detector(config):
    # Build detector
    detector = config.parameters.detector.build()
    logger.info("Loaded detector %s", type(detector))

    # Build object filter
    object_filter = _build_detection_filter(config.parameters.objects)

    # Process data
    with detector:
        for data in config.data:
            if data.video_path:
                logger.info("Processing video '%s'", data.video_path)
                _process_video(data, detector, object_filter)
            if data.image_path:
                logger.info("Processing image '%s'", data.image_path)
                _process_image(data, detector, object_filter)
            if data.images_dir:
                logger.info("Processing image directory '%s'", data.images_dir)
                _process_images_dir(data, detector, object_filter)


def _ensure_featurizing_detector(detector):
    if not isinstance(detector, etal.FeaturizingDetector):
        raise ConfigError(
            "Features are requested, but %s does not implement the %s "
            "mixin" % (type(detector), etal.FeaturizingDetector))

    if not detector.generates_features:
        raise ConfigError(
            "Features are requested, but the provided detector, an instance "
            "of %s, cannot generate features" % type(detector))


def _process_video(data, detector, object_filter):
    if data.video_features_dir:
        _ensure_featurizing_detector(detector)

    if data.input_labels_path:
        logger.info(
            "Reading existing labels from '%s'", data.input_labels_path)
        video_labels = etav.VideoLabels.from_json(data.input_labels_path)
    else:
        video_labels = etav.VideoLabels()

    # Detect objects in frames of video
    with etav.FFmpegVideoReader(data.video_path) as vr:
        for img in vr:
            logger.debug("Processing frame %d", vr.frame_number)

            # Detect objects in frame
            objects = object_filter(detector.detect(img))
            for obj in objects:
                obj.frame_number = vr.frame_number
                video_labels.add_object(obj, vr.frame_number)

    logger.info("Writing labels to '%s'", data.output_labels_path)
    video_labels.write_json(data.output_labels_path)


def _process_image(data, detector, object_filter):
    if data.image_features_dir:
        _ensure_featurizing_detector(detector)

    if data.input_image_labels_path:
        logger.info(
            "Reading existing labels from '%s'", data.input_image_labels_path)
        image_labels = etai.ImageLabels.from_json(data.input_image_labels_path)
    else:
        image_labels = etai.ImageLabels()

    # Detect objects in image
    img = etai.read(data.image_path)
    objects = object_filter(detector.detect(img))
    image_labels.add_objects(objects)

    logger.info("Writing labels to '%s'", data.output_image_labels_path)
    image_labels.write_json(data.output_image_labels_path)


def _process_images_dir(data, detector, object_filter):
    if data.image_set_features_dir:
        _ensure_featurizing_detector(detector)

    if data.input_image_set_labels_path:
        logger.info(
            "Reading existing labels from '%s'",
            data.input_image_set_labels_path)
        image_set_labels = etai.ImageSetLabels.from_json(
            data.input_image_set_labels_path)
    else:
        image_set_labels = etai.ImageSetLabels()

    # Classify images in directory
    for filename in etau.list_files(data.images_dir):
        inpath = os.path.join(data.images_dir, filename)
        logger.info("Processing image '%s'", inpath)

        # Classify image
        img = etai.read(inpath)
        objects = object_filter(detector.detect(img))
        image_set_labels[filename].add_objects(objects)

    logger.info("Writing labels to '%s'", data.output_image_set_labels_path)
    image_set_labels.write_json(data.output_image_set_labels_path)


def run(config_path, pipeline_config_path=None):
    '''Run the apply_object_detector module.

    Args:
        config_path: path to a ApplyObjectDetectorConfig file
        pipeline_config_path: optional path to a PipelineConfig file
   '''
    config = ApplyObjectDetectorConfig.from_json(config_path)
    etam.setup(config, pipeline_config_path=pipeline_config_path)
    _apply_object_detector(config)


if __name__ == "__main__":
    run(*sys.argv[1:])
