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
import yaml
from typing import List

from elyra.pipeline.component import Component, ComponentProperty, ComponentParser


class KfpComponentParser(ComponentParser):
    _type = "kfp"

    def __init__(self):
        super().__init__()

    def parse(self, component_id, component_name, component_definition, properties):
        component_yaml = self._read_component_yaml(component_definition)

        # TODO May have to adjust description if there are parsing issues
        description = ""
        if component_yaml.get('description'):
            description = ' '.join(component_yaml.get('description').split())

        component = Component(id=component_id,
                              name=component_yaml.get('name'),
                              description=description,
                              runtime=self._type,
                              properties=properties)
        return [component]

    def parse_properties(self, component_id, component_definition, location, source_type):
        component_yaml = self._read_component_yaml(component_definition)
        properties: List[ComponentProperty] = list()

        # For KFP we need a property for runtime image, path to component_id, and component_id source type
        runtime_image = component_yaml.get('implementation').get('container').get('image')
        if not runtime_image:
            raise RuntimeError("Error accessing runtime image for component_id.")
        properties.extend(self.get_runtime_specific_properties(runtime_image, location, source_type))

        # Then loop through and create custom properties
        for param in component_yaml.get('inputs'):

            # Determine whether parameter is optional
            required = False
            if "optional" in param and not param.get('optional'):
                required = True

            # Assign type, default to string
            type = "string"
            if "type" in param:
                type = param.get('type')

            # Set description
            description = ""
            if "description" in param:
                description = param.get('description')

            # Change parameter_ref and description to reflect the type of input (inputValue vs inputPath)
            ref = self.get_adjusted_parameter_fields(component_body=component_yaml,
                                                     io_object_name=param.get('name'),
                                                     io_object_type="input",
                                                     parameter_ref=param.get('name').lower().replace(' ', '_'))

            default_value = ""
            if "default" in param:
                default_value = param.get('default')

            properties.append(ComponentProperty(ref=ref,
                                                name=param.get('name'),
                                                type=type,
                                                value=default_value,
                                                description=description,
                                                required=required))
        return properties

    def get_runtime_specific_properties(self, runtime_image, location, source_type):
        """
        Define properties that are common to the KFP runtime.
        """
        properties = [ComponentProperty(ref="runtime_image",
                                        name="Runtime Image",
                                        type="string",
                                        value=runtime_image,
                                        description="Docker image used as execution environment.",
                                        control="readonly",
                                        required=True),
                      ComponentProperty(ref="component_source",
                                        name="Path to Component",
                                        type="string",
                                        value=location,
                                        description="The path to the component_id specification file.",
                                        control="readonly",
                                        required=True),
                      ComponentProperty(ref="component_source_type",
                                        name="Component Source Type",
                                        type="string",
                                        value=source_type,
                                        description="",
                                        control="readonly",
                                        required=True)]
        return properties

    def _read_component_yaml(self, component_body):
        """
        Convert component_body string to YAML object.
        """
        try:
            return yaml.safe_load(component_body)
        except yaml.YAMLError as e:
            raise RuntimeError from e

    def get_adjusted_parameter_fields(self,
                                      component_body,
                                      io_object_name,
                                      io_object_type,
                                      parameter_ref):
        """
        Change the parameter ref according if it is a KFP path parameter (as opposed to a value parameter)
        """
        ref = parameter_ref
        if "implementation" in component_body and "container" in component_body['implementation']:
            if "command" in component_body['implementation']['container']:
                for command in component_body['implementation']['container']['command']:
                    if isinstance(command, dict) and list(command.values())[0] == io_object_name and \
                            list(command.keys())[0] == f"{io_object_type}Path":
                        ref = f"elyra_path_{parameter_ref}"
            if "args" in component_body['implementation']['container']:
                for arg in component_body['implementation']['container']['args']:
                    if isinstance(arg, dict) and list(arg.values())[0] == io_object_name and \
                            list(arg.keys())[0] == f"{io_object_type}Path":
                        ref = f"elyra_path_{parameter_ref}"

        return ref
