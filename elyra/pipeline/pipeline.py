#
# Copyright 2018-2021 Elyra Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from logging import Logger
import os
import sys
from types import SimpleNamespace
from typing import Dict
from typing import Optional


class Operation(object):
    """
    Represents a single operation in a pipeline
    """

    def __init__(self, id, type, name, classifier, parent_operations=None, component_source_type=None,
                 component_source=None, component_params=None):
        """
        :param id: Generated UUID, 128 bit number used as a unique identifier
                   e.g. 123e4567-e89b-12d3-a456-426614174000
        :param type: The type of node e.g. execution_node
        :param classifier: classifier for processor execution e.g. Argo
        :param name: The name of the operation
        :param filename: The relative path to the source file in the users local environment
                         to be executed e.g. path/to/file.ext
        :param runtime_image: The DockerHub image to be used for the operation
                               e.g. user/docker_image_name:tag
        :param dependencies: List of local files/directories needed for the operation to run
                             and packaged into each operation's dependency archive
        :param include_subdirectories: Include or Exclude subdirectories when packaging our 'dependencies'
        :param env_vars: List of Environmental variables to set in the docker image
                         e.g. FOO="BAR"
        :param inputs: List of files to be consumed by this operation, produced by parent operation(s)
        :param outputs: List of files produced by this operation to be included in a child operation(s)
        :param parent_operations: List of parent operation 'ids' required to execute prior to this operation
        :param cpu: number of cpus requested to run the operation
        :param memory: amount of memory requested to run the operation (in Gi)
        :param gpu: number of gpus requested to run the operation
        :param component_source_type: source type of a non-standard component, either filepath or url
        :param component_params: dictionary of parameter key:value pairs that are used in the creation of a
                                 a non-standard operation instance
        """

        # Validate that the operation has all required properties
        if not id:
            raise ValueError("Invalid pipeline operation: Missing field 'operation id'.")
        if not type:
            raise ValueError("Invalid pipeline operation: Missing field 'operation type'.")
        if not classifier:
            raise ValueError("Invalid pipeline operation: Missing field 'operation classifier'.")
        if not name:
            raise ValueError("Invalid pipeline operation: Missing field 'operation name'.")

        self._id = id
        self._type = type
        self._classifier = classifier
        self._name = name

        self._parent_operations = parent_operations or []
        self._component_source = component_source
        self._component_source_type = component_source_type

        if component_source == "elyra":
            if not component_params.get('filename'):
                raise ValueError("Invalid pipeline operation: Missing field 'operation filename'.")
            if not component_params.get('runtime_image'):
                raise ValueError("Invalid pipeline operation: Missing field 'operation runtime image'.")
            if component_params.get('cpu') and not _validate_range(component_params.get('cpu'), min_value=1):
                raise ValueError("Invalid pipeline operation: CPU must be a positive value or None")
            if component_params.get('gpu') and not _validate_range(component_params.get('gpu'), min_value=0):
                raise ValueError("Invalid pipeline operation: GPU must be a positive value or None")
            if component_params.get('memory') and not _validate_range(component_params.get('memory'), min_value=1):
                raise ValueError("Invalid pipeline operation: Memory must be a positive value or None")

            # Re-build object to include default values
            component_params = {
                "filename": component_params.get('filename'),
                "runtime_image": component_params.get('runtime_image'),
                "dependencies": component_params.get('dependencies', []),
                "include_subdirectories": component_params.get('include_subdirectories', False),
                "env_vars": component_params.get('env_vars', []),
                "inputs": component_params.get('inputs', []),
                "outputs": component_params.get('outputs', []),
                "cpu": component_params.get('cpu'),
                "gpu": component_params.get('gpu'),
                "memory": component_params.get('memory')
            }

        # IDEA Feed a dictionary and convert to attributes; consider SimpleNamespace object
        self._component_params = SimpleNamespace(**component_params)

    @property
    def id(self):
        return self._id

    @property
    def type(self):
        return self._type

    @property
    def classifier(self):
        return self._classifier

    @property
    def name(self):
        if self._component_source == "elyra" and \
                self._name == os.path.basename(self._filename):
            self._name = os.path.basename(self._name).split(".")[0]
        return self._name

    @property
    def filename(self):
        # return self._filename
        return self._component_params.filename

    @property
    def runtime_image(self):
        # return self._runtime_image
        return self._component_params.runtime_image

    @property
    def dependencies(self):
        # return self._dependencies
        return self._component_params.dependencies

    @property
    def include_subdirectories(self):
        # return self._include_subdirectories
        return self._component_params.include_subdirectories

    @property
    def env_vars(self):
        # return self._env_vars
        return self._component_params.env_vars

    @property
    def cpu(self):
        # return self._cpu
        return self._component_params.cpu

    @property
    def memory(self):
        # return self._memory
        return self._component_params.memory

    @property
    def gpu(self):
        # return self._gpu
        return self._component_params.gpu

    def env_vars_as_dict(self, logger: Optional[Logger] = None) -> Dict:
        """
        Operation stores environment variables in a list of name=value pairs, while
        subprocess.run() requires a dictionary - so we must convert.  If no envs are
        configured on the Operation, an empty dictionary is returned, otherwise envs
        configured on the Operation are converted to dictionary entries and returned.
        """
        envs = {}
        for nv in self._component_params.env_vars:
            if nv:
                nv_pair = nv.split("=", 1)
                if len(nv_pair) == 2 and nv_pair[0].strip():
                    if len(nv_pair[1]) > 0:
                        envs[nv_pair[0]] = nv_pair[1]
                    else:
                        Operation._log_info(f"Skipping inclusion of environment variable: "
                                            f"`{nv_pair[0]}` has no value...",
                                            logger=logger)
                else:
                    Operation._log_warning(f"Could not process environment variable entry `{nv}`, skipping...",
                                           logger=logger)
        return envs

    @staticmethod
    def _log_info(msg: str, logger: Optional[Logger] = None):
        if logger:
            logger.info(msg)
        else:
            print(msg)

    @staticmethod
    def _log_warning(msg: str, logger: Optional[Logger] = None):
        if logger:
            logger.warning(msg)
        else:
            print(f"WARNING: {msg}")

    @property
    def inputs(self):
        # return self._inputs
        return self._component_params.inputs

    @inputs.setter
    def inputs(self, value):
        # self._inputs = value
        self._component_params.inputs = value

    @property
    def outputs(self):
        # return self._outputs
        return self._component_params.outputs

    @outputs.setter
    def outputs(self, value):
        # self._outputs = value
        self._component_params.outputs = value

    @property
    def parent_operations(self):
        return self._parent_operations

    @property
    def component_source(self):
        return self._component_source

    @property
    def component_source_type(self):
        return self._component_source_type

    @property
    def component_params(self):
        return self._component_params

    @property
    def component_params_as_dict(self):
        return self._component_params.__dict__

    def __eq__(self, other: object) -> bool:
        if isinstance(self, other.__class__):
            return self.id == other.id and \
                self.type == other.type and \
                self.classifier == other.classifier and \
                self.name == other.name and \
                self.component_params.__eq__(other.component_params)
        return False

    def __str__(self) -> str:
        params = ""
        for key, value in self.component_params_as_dict.items():
            params += f"\t{key}: {value}, \n"

        return "componentID : {id} \n " \
            "name : {name} \n " \
            "parent_operations : {parent_op} \n " \
            "component_source_type: {source_type} \n " \
            "component_source: {source} \n " \
            "component_parameters: {{\n{params}}} \n ".format(id=self.id,
                                                              name=self.name,
                                                              parent_op=self.parent_operations,
                                                              source_type=self.component_source_type,
                                                              source=self.component_source,
                                                              params=params)


class Pipeline(object):
    """
    Represents a single pipeline constructed in the pipeline editor
    """

    def __init__(self, id, name, runtime, runtime_config, source=None):
        """
        :param id: Generated UUID, 128 bit number used as a unique identifier
                   e.g. 123e4567-e89b-12d3-a456-426614174000
        :param name: Pipeline name
                     e.g. test-pipeline-123456
        :param runtime: Type of runtime we want to use to execute our pipeline
                        e.g. kfp OR airflow
        :param runtime_config: Runtime configuration that should be used to submit the pipeline to execution
        :param source: The pipeline source, e.g. a pipeline file or a notebook.
        """

        if not name:
            raise ValueError('Invalid pipeline: Missing pipeline name.')
        if not runtime:
            raise ValueError('Invalid pipeline: Missing runtime.')
        if not runtime_config:
            raise ValueError('Invalid pipeline: Missing runtime configuration.')

        self._id = id
        self._name = name
        self._source = source
        self._runtime = runtime
        self._runtime_config = runtime_config
        self._operations = {}

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def source(self):
        return self._source

    @property
    def runtime(self):
        """
        Describe the runtime type where the pipeline will be executed
        """
        return self._runtime

    @property
    def runtime_config(self):
        """
        Describe the runtime configuration that should be used to submit the pipeline to execution
        """
        return self._runtime_config

    @property
    def operations(self):
        return self._operations

    def __eq__(self, other: object) -> bool:
        if isinstance(self, other.__class__):
            return self.id == other.id and \
                self.name == other.name and \
                self.source == other.source and \
                self.runtime == other.runtime and \
                self.runtime_config == other.runtime_config and \
                self.operations == other.operations

###########################
# Utility functions
###########################


def _validate_range(value: str, min_value=0, max_value=sys.maxsize) -> bool:
    is_valid = False

    if value is None:
        is_valid = True
    elif int(value) in range(min_value, max_value):
        is_valid = True

    return is_valid
