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
import json
from jinja2 import Environment, PackageLoader

from traitlets.config import LoggingConfigurable

from elyra.pipeline.component import ComponentParser, Component
from types import SimpleNamespace
from typing import List, Dict


class ComponentRegistry(LoggingConfigurable):
    """
    Component Registry, responsible to provide a list of available components
    for each runtime. The registry uses component parser to read and parse each
    component entry from the catalog and transform them into a component value object.
    """

    def __init__(self, component_registry_location: str, parser: ComponentParser):
        super().__init__()
        self._component_registry_location = component_registry_location
        self._parser = parser
        self.log.info(f'Creating new registry using {self.registry_location}')

    @property
    def registry_location(self) -> str:
        return self._component_registry_location

    def get_all_components(self) -> List[Component]:
        """
        Retrieve all components from the component_id registry
        """
        components: List[Component] = list()

        # Read component_id catalog to get JSON
        component_entries = self._read_component_registry()

        for component_entry in component_entries:
            # Parse component_id details and add to list
            component = self._parser.parse(component_entry)
            if component:
                components.extend(component)

        return components

    def get_component(self, component_id):
        """
        Return the properties JSON for a given component_id.
        """
        # Read component_entry catalog to get component_entry with given id
        adjusted_id = self._parser.get_adjusted_component_id(component_id)
        component_entry = self._get_component_registry_entry(adjusted_id)

        # Assign adjusted id for the use of parsers if prefixes have been added
        if adjusted_id != component_id:
            component_entry.adjusted_id = component_id

        component = self._parser.parse(component_entry)[0]
        return component

    @staticmethod
    def get_generic_components() -> List[Component]:
        generic_components = [Component(id="notebooks",
                                        name="Notebook",
                                        description="Notebook file",
                                        op="execute-notebook-node"),
                              Component(id="python-script",
                                        name="Python",
                                        description="Python Script",
                                        op="execute-python-node"),
                              Component(id="r-script",
                                        name="R",
                                        description="R Script",
                                        op="execute-r-node")]
        return generic_components

    @staticmethod
    def to_canvas_palette(components: List[Component]) -> dict:
        """
        Converts registry components into appropriate canvas palette format
        """
        # Load jinja2 template
        loader = PackageLoader('elyra', 'templates/components')
        template_env = Environment(loader=loader)
        template = template_env.get_template('canvas_palette_template.jinja2')

        return template.render(components=components)

    @staticmethod
    def to_canvas_properties(component: Component) -> dict:
        """
        Converts registry components into appropriate canvas properties format
        """
        loader = PackageLoader('elyra', 'templates/components')
        template_env = Environment(loader=loader)

        # If component_id is one of the generic set, render with generic template,
        # else render with the runtime-specific property template
        if component in ('notebooks', 'python-script', 'r-script'):
            template = template_env.get_template('generic_properties_template.jinja2')
            if component == "notebooks":
                component_type = "notebook"
                file_type = ".ipynb"
            elif component == "python-script":
                component_type = "Python"
                file_type = ".py"
            elif component == "r-script":
                component_type = "R"
                file_type = ".r"

            properties_json = template.render(component_type=component_type, file_type=file_type)
        else:
            template = template_env.get_template('canvas_properties_template.jinja2')
            properties_json = template.render(properties=component.properties)

        return properties_json

    def _read_component_registry(self) -> Dict:
        """
        Read a component_id catalog and return its component_id definitions.
        """

        component_entries: list = list()
        with open(self._component_registry_location, 'r') as catalog_file:
            catalog_json = json.load(catalog_file)
            if 'components' in catalog_json.keys():
                for component_id, component_entry in catalog_json['components'].items():
                    self.log.debug(f"Component registry: processing component {component_entry.get('name')}")

                    component_type = next(iter(component_entry.get('location')))
                    entry = {
                        "id": component_id,
                        "name": component_entry["name"],
                        "type": component_type,
                        "location": component_entry["location"][component_type],
                        "adjusted_id": ""
                    }
                    component_entries.append(SimpleNamespace(**entry))

        return component_entries

    def _get_component_registry_entry(self, component_id):
        """
        Get the body of the component_id catalog entry with the given id
        """
        # Read component_id catalog to get JSON
        component_entries = self._read_component_registry()

        # Find entry with the appropriate id, if exists
        component_entry = next((entry for entry in component_entries if entry.id == component_id), None)
        if not component_entry:
            self.log.error(f"Component with ID '{component_id}' could not be found in the " +
                           f"{self._component_registry_location} component_id catalog.")
            raise ValueError(f"Component with ID '{component_id}' could not be found in the " +
                             f"{self._component_registry_location} component_id catalog.")

        return component_entry


class CachedComponentRegistry(ComponentRegistry):
    """
    Cached component_entry registry, builds on top of the vanilla component_entry registry
    adding a cache layer to optimize catalog reads.
    """

    _cache: List[Component] = None

    def __init__(self, component_registry_location: str, parser: ComponentParser, cache_ttl: int = 60):
        super().__init__(component_registry_location, parser)
        self._cache_ttl = cache_ttl

        # Initialize the cache
        self.get_all_components()

    def get_all_components(self) -> List[Component]:
        if not self._cache:
            self._cache = super().get_all_components()

        return self._cache
