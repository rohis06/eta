'''
Core status infrastructure for pipelines and jobs.

Copyright 2017-2020, Voxel51, Inc.
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

from datetime import datetime
import logging

from eta.core.serial import Serializable
import eta.core.utils as etau


logger = logging.getLogger(__name__)


class PipelineState(object):
    '''Enum describing the possible states of a pipeline.'''

    READY = "READY"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


class PipelineStatus(Serializable):
    '''Class for recording the status of a pipeline.

    Attributes:
        name: the name of the pipeline
        state: the current state of the pipeline
        start_time: the time the pipeline was started, or None if not started
        complete_time: the time the pipeline was completed, or None if not
            completed
        fail_time: the time the pipeline failed, or None if not failed
        messages: a list of StatusMessage objects listing the status updates
            for the pipeline
        jobs: a list of JobStatus objects describing the status of the jobs
            that make up the pipeline
    '''

    def __init__(
            self, name=None, state=PipelineState.READY, start_time=None,
            complete_time=None, fail_time=None, messages=None, jobs=None):
        '''Creates a PipelineStatus instance.

        Args:
            name: the name of the pipeline
            state: an optional PipelineState of the pipeline. The default is
                PipelineState.READY
            start_time: the time the pipeline started, if applicable
            complete_time: the time the pipeline completed, if applicable
            fail_time: the time the pipeline failed, if applicable
            messages: an optional list of StatusMessage instances
            jobs: an optional list of JobStatus instances
        '''
        self.name = name or ""
        self.state = state
        self.start_time = start_time
        self.complete_time = complete_time
        self.fail_time = fail_time
        self.messages = messages or []
        self.jobs = jobs or []

        self._publish_callback = None
        self._active_job = None

    def set_publish_callback(self, publish_callback):
        '''Sets the callback to use when `publish()` is called.

        Args:
            publish_callback: a function that accepts a PipelineStatus object
                and performs some desired action with it
        '''
        self._publish_callback = publish_callback

    def publish(self):
        '''Publishes the pipeline status using the callback provided via the
        `set_publish_callback()` method (if any).
        '''
        if self._publish_callback:
            self._publish_callback(self)

    @property
    def active_job(self):
        '''The JobStatus instance for the active job, or None if no job is
        active.
        '''
        return self._active_job

    def add_job(self, name):
        '''Add a new job with the given name and activate it.

        Returns:
            the JobStatus instance for the job
        '''
        self._active_job = JobStatus(name)
        self.jobs.append(self._active_job)
        return self._active_job

    def add_message(self, message):
        '''Add the given message to the messages list.

        Args:
            message: the message string
        '''
        status_message = StatusMessage(message)
        self.messages.append(status_message)
        return status_message.time

    def start(self, message="Pipeline started"):
        '''Mark the pipeline as started and record the given message.

        If the pipeline is already started, no action is taken.

        Args:
            message: an optional message string
        '''
        if self.state == PipelineState.RUNNING:
            return

        self.start_time = self.add_message(message)
        self.state = PipelineState.RUNNING

    def complete(self, message="Pipeline completed"):
        '''Mark the pipelne as complete and record the given message.

        If the pipeline is already complete, no action is taken.

        Args:
            message: an optional message string
        '''
        if self.state == PipelineState.COMPLETE:
            return

        self.complete_time = self.add_message(message)
        self.state = PipelineState.COMPLETE

    def fail(self, message="Pipeline failed"):
        '''Mark the pipelne as failed and record the given message.

        If the pipeline is already failed, no action is taken.

        Args:
            message: an optional message string
        '''
        if self.state == PipelineState.FAILED:
            return

        self.fail_time = self.add_message(message)
        self.state = PipelineState.FAILED

    def attributes(self):
        '''Returns a list of class attributes to be serialized.

        Returns:
            a list of attributes
        '''
        return [
            "name", "state", "start_time", "complete_time", "fail_time",
            "messages", "jobs"]

    @classmethod
    def from_dict(cls, d):
        '''Constructs a PipelineStatus instance from a JSON dictionary.

        Args:
            d: a JSON dictionary

        Returns:
            a PipelineStatus instance
        '''
        name = d["name"]
        state = d["state"]
        start_time = d["start_time"]
        complete_time = d["complete_time"]
        fail_time = d["fail_time"]
        messages = [StatusMessage.from_dict(sd) for sd in d["messages"]]
        jobs = [JobStatus.from_dict(jd) for jd in d.get("jobs", [])]
        return cls(
            name, state=state, start_time=start_time,
            complete_time=complete_time, fail_time=fail_time,
            messages=messages, jobs=jobs)


class JobState(object):
    '''Enum describing the possible states of a pipeline.'''

    READY = "READY"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    SKIPPED = "SKIPPED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


class JobStatus(Serializable):
    '''Class for recording the status of a job.'''

    def __init__(
            self, name, state=JobState.READY, start_time=None,
            complete_time=None, fail_time=None, messages=None):
        '''Creates a JobStatus instance.

        Args:
            name: the name of the job
            state: the current state of the job. The default is
                `JobState.READY`
            start_time: the start time of the job, or None if not started
            complete_time: the time the job was completed, or None if not
                completed
            fail_time: the time the job failed, or None if not failed
            messages: a list of StatusMessage objects listing the status
                updates for the job
        '''
        self.name = name
        self.state = state
        self.start_time = start_time
        self.complete_time = complete_time
        self.fail_time = fail_time
        self.messages = messages or []

    def add_message(self, message):
        '''Add the given message to the messages list.

        Args:
            message: the message string
        '''
        status_message = StatusMessage(message)
        self.messages.append(status_message)
        return status_message.time

    def skip(self, message="Job skipped"):
        '''Mark the job as skipped and record the given message.

        Args:
            message: an optional message
        '''
        self.add_message(message)
        self.state = JobState.SKIPPED

    def start(self, message="Job started"):
        '''Mark the job as started and record the given message.

        Args:
            message: an optional message
        '''
        self.start_time = self.add_message(message)
        self.state = JobState.RUNNING

    def complete(self, message="Job completed"):
        '''Mark the job as complete and record the given message.

        Args:
            message: an optional message
        '''
        self.complete_time = self.add_message(message)
        self.state = JobState.COMPLETE

    def fail(self, message="Job failed"):
        '''Mark the job as failed and record the given message.

        Args:
            message: an optional message
        '''
        self.fail_time = self.add_message(message)
        self.state = JobState.FAILED

    def attributes(self):
        '''Returns the list of attributes to serialize.

        Returns:
            the list of attributes
        '''
        return [
            "name", "state", "start_time", "complete_time", "fail_time",
            "messages"]

    @classmethod
    def from_dict(cls, d):
        '''Constructs a JobStatus instance from a JSON dictionary.

        Args:
            d: a JSON dictionary

        Returns:
            a JobStatus instance
        '''
        start_time = d.get("start_time", None)
        if start_time is not None:
            start_time = etau.parse_isotime(start_time)

        complete_time = d.get("complete_time", None)
        if complete_time is not None:
            complete_time = etau.parse_isotime(complete_time)

        fail_time = d.get("fail_time", None)
        if fail_time is not None:
            fail_time = etau.parse_isotime(fail_time)

        messages = d.get("messages", None)
        if messages is not None:
            messages = [StatusMessage.from_dict(md) for md in messages]

        return cls(
            d["name"], start_time=start_time, complete_time=complete_time,
            fail_time=fail_time, messages=messages)


class StatusMessage(Serializable):
    '''Class encapsulating a status message with a timestamp.

    Attributes:
        message: the message string
        time: a datetime recording the message time
    '''

    def __init__(self, message, time=None):
        '''Creates a StatusMessage instance.

        Args:
            message: a message string
            time: an optional datetime for the message. By default, the current
                time is used
        '''
        self.message = message
        self.time = time or datetime.now()

    def attributes(self):
        '''Returns the list of attributes to serialize.

        Returns:
            the list of attributes
        '''
        return ["message", "time"]

    @classmethod
    def from_dict(cls, d):
        '''Constructs a StatusMessage instance from a JSON dictionary.

        Args:
            d: a JSON dictionary

        Returns:
            a StatusMessage instance
        '''
        time = d.get("time", None)
        if time is not None:
            time = etau.parse_isotime(time)

        return StatusMessage(d["message"], time=time)
