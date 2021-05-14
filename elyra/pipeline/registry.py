#
# Copyright 2018-2020 IBM Corporation
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
import os
import io
import json
import yaml
import urllib
import re

from traitlets.config import SingletonConfigurable


cardinality = {
    'min': 0,
    'max': -1
}

inputs = {
    "id": "inPort",
    "app_data": {
        "ui_data": {
            "cardinality": cardinality,
            "label": "Input Port"
        }
    }
}

outputs = {
    "id": "outPort",
    "app_data": {
        "ui_data": {
            "cardinality": cardinality,
            "label": "Output Port"
        }
    }
}


def get_id_from_name(name):
    return ' '.join(name.lower().replace('-', '').split()).replace(' ', '-').replace('_', '-')


def set_node_type_data(id, label, description):
    node_type = {
        'id': "",
        'op': f"execute-{id}-node",
        'type': "execution_node",
        'inputs': [inputs],
        'outputs': [outputs],
        'parameters': {},
        'app_data': {
            'ui-data': {
                'label': label,
                'description': description,
                'image': "",
                'x_pos': 0,
                'y_pos': 0
            }
        }
    }

    return node_type


class ComponentParser(SingletonConfigurable):
    _type = "local"
    properties: dict() = {}
    parameters: dict() = {}

    def __init__(self):
        super().__init__()
        self.properties = self.get_common_config('properties')

    def get_common_config(self, config_name):
        common_dir = os.path.join(os.path.dirname(__file__), 'resources')
        common_file = os.path.join(common_dir, f"{config_name}.json")
        with io.open(common_file, 'r', encoding='utf-8') as f:
            common_json = json.load(f)

        return common_json

    def _get_component_catalog_json(self):
        catalog_dir = os.path.join(os.path.dirname(__file__), "resources")
        catalog_file = os.path.join(catalog_dir, f"{self._type}_component_catalog.json")
        with open(catalog_file, 'r') as f:
            catalog_json = json.load(f)

        return catalog_json['components']

    def list_all_components(self):
        components = []
        if self._type != "local":
            for component in self._get_component_catalog_json():
                assert "path" in component
                components.append(component)

        return components

    def return_component_if_exists(self, component_id):
        for component in self._get_component_catalog_json():
            if component['id'] == component_id:
                return component
        return None

    def add_component(self, request_body):
        component_json = {
            'name': request_body['name'],
            'id': get_id_from_name(request_body['name']),
            'path': request_body['path']
        }

        catalog_json = self._get_component_catalog_json()
        catalog_json['components'].append(component_json)

        catalog_dir = os.path.join(os.path.dirname(__file__), "resources")
        catalog_file = os.path.join(catalog_dir, f"{self._type}_component_catalog.json")
        with open(catalog_file, 'a') as f:
            f.write(json.dumps(catalog_json))

    def parse_component_details(self, component, component_name):
        """Get component name, id, description for palette JSON"""
        pass

    def parse_component_properties(self, component):
        """Get component properties for properties JSON"""
        raise NotImplementedError


class KfpComponentParser(ComponentParser):
    _type = "kfp"

    def __init__(self):
        super().__init__()

    def parse_component_details(self, component_body, component_name=None):
        component_json = {
            'label': component_body['name'],
            'image': "",
            'id': get_id_from_name(component_body['name']),
            'description': ' '.join(component_body['description'].split()),
            'node_types': []
        }

        node_type = set_node_type_data(component_json['id'],
                                       component_json['label'],
                                       component_json['description'])
        component_json['node_types'].append(node_type)

        return component_json

    def parse_component_properties(self, component_body):
        '''
        Build the properties object according to the YAML and return properties.
        '''
        # Start with generic properties
        component_parameters = self.get_common_config('properties')

        # TODO Do we need to/should we pop these?
        for element in ['runtime_image', 'env_vars', 'dependencies', 'outputs', 'include_subdirectories']:
            component_parameters['current_parameters'].pop(element, None)

        # Define new input group object
        input_group_info = {
            'id': "inputs",
            'type': "controls",
            'parameter_refs': []
        }

        inputs = component_body['inputs']
        for input_object in inputs:
            new_parameter_info = self.build_parameter(input_object, "input")

            # TODO: Adjust this to return an empty value for whatever type the parameter is?
            default_value = ""
            if "default" in input_object:
                default_value = input_object['default']

            # Add to existing parameter list
            component_parameters['parameters'].append({"id": new_parameter_info['parameter_ref']})
            component_parameters['current_parameters'][new_parameter_info['parameter_ref']] = default_value

            # Add to existing parameter info list
            component_parameters['uihints']['parameter_info'].append(new_parameter_info)

            # Add parameter to input group info
            input_group_info['parameter_refs'].append(new_parameter_info['parameter_ref'])

        # Append input group info to parameter details
        component_parameters['uihints']['group_info'][0]['group_info'].append(input_group_info)

        # Define new output group object
        output_group_info = {
            'id': "outputs",  # need to actually figure out the control id
            'type': "controls",
            'parameter_refs': []
        }

        outputs = component_body['outputs']
        for output_object in outputs:
            new_parameter_info = self.build_parameter(output_object, "output")

            if new_parameter_info['parameter_ref'] in input_group_info['parameter_refs']:
                new_parameter_info['parameter_ref'] = f"output_{new_parameter_info['parameter_ref']}"

            # Add to existing parameter list
            component_parameters['parameters'].append({"id": new_parameter_info['parameter_ref']})
            component_parameters['current_parameters'][new_parameter_info['parameter_ref']] = ""

            # Add to existing parameter info list
            component_parameters['uihints']['parameter_info'].append(new_parameter_info)

            # Add parameter to output group info
            output_group_info['parameter_refs'].append(new_parameter_info['parameter_ref'])

        # Append output group info to parameter details
        component_parameters['uihints']['group_info'][0]['group_info'].append(output_group_info)

        return component_parameters

    def build_parameter(self, obj, obj_type):
        data_object = {}
        # Determine whether parameter is optional
        if ("optional" in obj and obj['optional']) \
                or ("description" in obj and "required" in obj['description'].lower()):
            data_object['required'] = True
        else:
            data_object['required'] = False

        # Assign type, default to string
        data_object['format'] = "string"
        custom_control_id = "StringControl"
        if "type" in obj:
            data_object['format'] = obj['type']

            # This may not be applicable in every case
            if "string" in obj['type'].lower():
                custom_control_id = "StringControl"
            elif obj['type'].lower() in ["number", "integer"]:
                custom_control_id = "NumberControl"
            elif obj['type'].lower() in ["bool", "boolean"]:
                custom_control_id = "BooleanControl"
            elif "array" in obj['type'].lower():
                custom_control_id = "StringArrayControl"
            elif "object" in obj['type'].lower():
                custom_control_id = "StringControl"

        # Build label name
        label = obj['name']
        if obj_type not in obj['name'].lower():
            label = f"{obj['name']} ({obj_type})"

        # Build parameter info
        new_parameter = {
            'parameter_ref': obj['name'].replace(' ', '_'),
            'control': "custom",
            'custom_control_id': custom_control_id,
            'label': {
                'default': label
            },
            'description': {
                'default': obj["description"].title(),
                'placement': "on_panel"
            },
            "data": data_object
        }

        return new_parameter

    def parse_component_execution_instructions(self, component_body):
        pass


class AirflowComponentParser(ComponentParser):
    _type = "airflow"

    def __init__(self):
        super().__init__()

    def parse_component_details(self, component_body, component_name):
        # Component_body never used

        label = ' '.join(component_name.split('_')).title()

        # TODO: Is there any way to reliably get the description for the operator overall?
        # Could maybe pull from a class description but this wouldn't work for operators
        # with multiple classes or those without docstrings at all.
        description = ""

        component_json = {
            'label': label,
            'image': "",
            'id': get_id_from_name(label),
            'description': ' '.join(description.split()),
            'node_types': []
        }

        node_type = set_node_type_data(get_id_from_name(label), label, description)
        component_json['node_types'].append(node_type)

        return component_json

    def parse_component_properties(self, component):
        '''
        Build the properties object according to the operator python file and return properties.
        '''
        # Start with generic properties
        component_parameters = self.get_common_config('properties')

        # TODO Do we need to/should we pop these?
        for element in ['runtime_image', 'env_vars', 'dependencies', 'outputs', 'include_subdirectories']:
            component_parameters['current_parameters'].pop(element, None)

        class_regex = re.compile(r"class ([\w]+)\(\w*\):")
        init_regex = re.compile(r"def __init__\(([\s\d\w,=\-\'\"\*]*)\):")

        # Organize lines according to the class to which they belong
        classes = {}
        class_name = "no_class"
        classes[class_name] = {
            'lines': [],
            'init_args': []
        }
        for line in component:
            line = line.decode("utf-8")
            match = class_regex.search(line)
            if match:
                class_name = match.group(1)
                classes[class_name] = {'lines': [], 'init_args': []}
            classes[class_name]['lines'].append(line)

        # Loop through classes to get parameters for each class
        for class_name in classes:
            if class_name == "no_class":
                continue

            group_info = {
                'id': class_name,
                'type': "controls",
                'parameter_refs': []
            }

            # Concatenate class body and search for __init__ function
            class_content = ''.join(classes[class_name]['lines'])
            for match in init_regex.finditer(class_content):
                classes[class_name]['init_args'] = [x.strip() for x in match.group(1).split(',')]

                # For each argument to the init function, build a new parameter and add to existing
                for arg in classes[class_name]['init_args']:
                    if arg in ['self', '*args', '**kwargs']:
                        continue

                    default_value = ""
                    if '=' in arg:
                        split_arg = arg.split('=')
                        arg = split_arg[0]
                        default_value = split_arg[1]

                    new_parameter_info = self.build_parameter(arg, class_name, class_content)

                    # Add to existing parameter list
                    component_parameters['parameters'].append({"id": new_parameter_info['parameter_ref']})
                    component_parameters['current_parameters'][new_parameter_info['parameter_ref']] = default_value

                    # Add to existing parameter info list
                    component_parameters['uihints']['parameter_info'].append(new_parameter_info)

                    # Add parameter to output group info
                    group_info['parameter_refs'].append(new_parameter_info['parameter_ref'])

            # Append output group info to parameter details
            component_parameters['uihints']['group_info'][0]['group_info'].append(group_info)

        return component_parameters

    def build_parameter(self, parameter_name, class_name, component_body):
        # Search for parameter description in class doctring
        parameter_description = ""
        param_regex = re.compile(f":param {parameter_name}" + r":([\w ]*)")  # TODO Fix this regex to capture more
        match = param_regex.search(component_body)
        if match:
            parameter_description = match.group(1)

        data_object = {}
        # Search description to determine whether parameter is optional
        # Another potential check for 'required' status would be if there is
        # an = sign in the init function parameters, this implies that it is
        # not required and all else are required.
        if ("not optional" in parameter_description.lower()) or \
                ("required" in parameter_description.lower() and
                 "not required" not in parameter_description.lower() and
                 "n't required" not in parameter_description.lower()):
            data_object['required'] = True
        else:
            data_object['required'] = False

        # Default type will be string
        data_object['format'] = "string"
        custom_control_id = "StringControl"
        # Search for :type [param] information in class docstring
        type_regex = re.compile(f":type {parameter_name}" + r":([\w ]*)")
        match = type_regex.search(component_body)
        if match:
            data_object['format'] = match.group(1)

            # This may not be applicable in every case
            if "string" in match.group(1).lower():
                custom_control_id = "StringControl"
            elif match.group(1).lower() in ["number", "integer"]:
                custom_control_id = "NumberControl"
            elif match.group(1).lower() in ["bool", "boolean"]:
                custom_control_id = "BooleanControl"
            elif "array" in match.group(1).lower():
                custom_control_id = "StringArrayControl"
            elif "object" in match.group(1).lower():
                custom_control_id = "StringControl"

        # Build parameter info
        new_parameter = {
            'parameter_ref': f"{class_name}_{parameter_name}",
            'control': "custom",
            'custom_control_id': custom_control_id,
            'label': {
                'default': parameter_name
            },
            'description': {
                'default': parameter_description.title(),
                'placement': "on_panel"
            },
            "data": data_object
        }

        return new_parameter


class ComponentReader(SingletonConfigurable):
    _type = 'local'

    def __init__(self):
        super().__init__()

    def get_component_body(self, component_path):
        raise NotImplementedError()


class FilesystemComponentReader(ComponentReader):
    _type = 'file'
    _dir_path: str = 'resources'

    def __init__(self):
        super().__init__()

    def get_component_body(self, component_path):
        component_dir = os.path.join(os.path.dirname(__file__), self._dir_path)
        component_file = os.path.join(component_dir, component_path)

        component_name, component_extension = os.path.splitext(component_path)
        with open(component_file, 'r') as f:
            if component_extension == '.yaml':
                try:
                    return yaml.safe_load(f), component_name.split('/')[-1], component_extension
                except yaml.YAMLError as e:
                    raise RuntimeError from e
            elif component_extension == '.py':
                # TODO: Find better way to read in file. Can we assume operator files are always
                # small enough to be read into memory? Reading and yielding by line likely won't
                # work because multiple lines need to be checked at once (or multiple times).
                return f.readlines(), component_name.split('/')[-1], component_extension
            else:
                raise ValueError(f'File type {component_extension} is not supported.')


class UrlComponentReader(ComponentReader):
    _type = 'url'
    _url_path: str

    def __init__(self):
        super().__init__()

    def get_component_body(self, component_path):
        parsed_path = urllib.parse.urlparse(component_path).path
        component_name, component_extension = os.path.splitext(parsed_path)
        component_body = urllib.request.urlopen(component_path)

        if component_extension == ".yaml":
            try:
                return yaml.safe_load(component_body), component_name.split('/')[-1], component_extension
            except yaml.YAMLError as e:
                raise RuntimeError from e
        elif component_extension == ".py":
            return component_body.readlines(), component_name.split('/')[-1], component_extension
        else:
            raise ValueError(f'File type {component_extension} is not supported.')


class ComponentRegistry(SingletonConfigurable):

    parsers = {
        KfpComponentParser._type: KfpComponentParser(),
        AirflowComponentParser._type: AirflowComponentParser(),
        ComponentParser._type: ComponentParser()
    }

    readers = {
        FilesystemComponentReader._type: FilesystemComponentReader(),
        UrlComponentReader._type: UrlComponentReader(),
        'local': ComponentReader()
    }

    def get_all_components(self, registry_type, processor_type):
        """
        Builds a component palette in the form of a dictionary of components.
        """

        parser = self._get_parser(processor_type)
        assert processor_type == parser._type

        # Get components common to all runtimes
        components = parser.get_common_config('palette')

        # Loop through all the component definitions for the given registry type
        reader = None
        for component in parser.list_all_components():
            print(f"component registry -> found component {component['name']}")

            # Get appropriate reader in order to read component definition
            if reader is None or reader._type != list(component['path'].keys())[0]:
                reader = self._get_reader(component)

            component_body, component_name, _ = reader.get_component_body(component['path'][reader._type])

            # Parse the component definition in order to add to palette
            component_json = parser.parse_component_details(component_body, component_name)
            if component_json is None:
                continue
            components['categories'].append(component_json)

        return components

    def get_properties(self, processor_type, component_id):
        """
        Return the properties JSON for a given component.
        """
        default_components = ["notebooks", "python-script", "r-script"]

        parser = self._get_parser(processor_type)

        properties = {}
        if parser._type == "local" or component_id in default_components:
            properties = parser.get_common_config('properties')
        else:
            component = parser.return_component_if_exists(component_id)
            if component is None:
                raise ValueError(f"Component with ID {component_id} not found.")

            reader = self._get_reader(component)

            component_path = component['path'][reader._type]
            component_body, _, _ = reader.get_component_body(component_path)
            properties = parser.parse_component_properties(component_body)

        return properties

    def add_component(self, processor_type, request_body):
        """
        Add a component based on the provided definition. Definition will be provided in POST body
        in the format {"name": "desired_name", path": {"file/url": "filepath/urlpath"}}.
        """

        parser = self._get_parser(processor_type)
        parser.add_component(request_body)  # Maybe make this async to prevent reading issues in get_all_components()

        components = self.get_all_components(None, parser._type)
        return components

    def get_component_execution_details(self, processor_type, component_id):
        """
        Returns the implementation details of a given component.
        """
        parser = self._get_parser(processor_type)
        assert parser._type != "local"  # Local components should not have execution details

        component = parser.return_component_if_exists(component_id)

        reader = self._get_reader(component)
        component_path = component['path'][reader._type]
        component_body, _, _ = reader.get_component_body(component_path)

        execution_instructions = parser.parse_component_execution_instructions(component_body)
        return execution_instructions

    def _get_reader(self, component):
        """
        Find the proper reader based on the given registry component.
        """

        try:
            component_type = list(component['path'].keys())[0]
            return self.readers.get(component_type)
        except Exception:
            raise ValueError("Unsupported registry type.")

    def _get_parser(self, processor_type: str):
        """
        Find the proper parser based on processor type.
        """

        try:
            return self.parsers.get(processor_type)
        except Exception:
            raise ValueError(f"Unsupported processor type: {processor_type}")
