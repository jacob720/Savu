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

"""
.. module:: plugin_tools
   :platform: Unix
   :synopsis: Plugin tools

.. moduleauthor:: Jessica Verschoyle <scientificsoftware@diamond.ac.uk>

"""
import os
import copy
import logging

from colorama import Fore
from collections import OrderedDict

import savu.plugins.utils as pu
from savu.data.meta_data import MetaData
import savu.plugins.docstring_parser as doc
import scripts.config_generator.parameter_utils as param_u
from savu.data.plugin_list import CitationInformation

logger = logging.getLogger("documentationLog")


class PluginParameters(object):
    """Save the parameters for the plugin and base classes to a
    dictionary. The parameters are in yaml format inside the
    define_parameter function. These are read and checked for problems.
    """

    def __init__(self):
        super(PluginParameters, self).__init__()
        self.param = MetaData(ordered=True)
        self.docstring_info = {}
        self.parameters = {}

    def populate_parameters(self, tools_list):
        """ Set parameter definitions and default parameter values """
        # set the parameter definitions
        # populates the dictionary returned by self.get_param_definitions()
        list(map(lambda tool_class: 
                 self._set_parameter_definitions(tool_class), tools_list))
        # set the default parameter values
        # populates the dictionary returned by self.get_param_values()
        self._populate_default_parameters()

    def initialise(self, params):
        # Override default parameter values with plugin list entries
        self.set_plugin_list_parameters(copy.deepcopy(params))
        self.multi_params_dict = {}
        self.extra_dims = []
        self._get_plugin().set_parameters(self.parameters)
        
    def _populate_default_parameters(self):
        """
        This method should populate all the required parameters with
        default values. It is used for checking to see if parameter
        values are appropriate
        """
        p_defs = self.get_param_definitions()
        self.set_docstring(self.get_doc())
        self.parameters = \
            OrderedDict([(k, v['default']) for k, v in p_defs.items()])
        # parameters holds current values, this is edited outside of the
        # tools class so default and dependency display values are updated here
        self.update_dependent_defaults()
        self.check_dependencies(self.parameters)
        self._get_plugin().set_parameters(self.parameters)

    def set_docstring(self, doc_str):
        self.docstring_info['info'] = doc_str.get('verbose')
        self.docstring_info['warn'] = doc_str.get('warn')
        self.docstring_info['documentation_link'] = doc_str.get('documentation_link')
        self.docstring_info['synopsis'] = doc.find_synopsis(self._get_plugin())

    def _set_parameters_this_instance(self, indices):
        """ Determines the parameters for this instance of the plugin, in the
        case of parameter tuning.

        param np.ndarray indices: the index of the current value in the
            parameter tuning list.
        """
        dims = set(self.multi_params_dict.keys())
        count = 0
        for dim in dims:
            info = self.multi_params_dict[dim]
            name = info['label'].split('_param')[0]
            self.parameters[name] = info['values'][indices[count]]
            count += 1

    def _set_parameter_definitions(self, tool_class):
        """Load the parameters for each base class, c, check the
        dataset visibility, check data types, set dictionary values.
        """
        param_info_dict = self._load_param_from_doc(tool_class)
        if param_info_dict:
            # Check if the required keys are included
            self._check_required_keys(param_info_dict, tool_class)
            # Check that option values are valid
            self._check_options(param_info_dict, tool_class)
            # Check that the dataset visibility is set
            self._check_visibility(param_info_dict, tool_class)
            # Check that the visibility levels are valid
            self._check_dtype(param_info_dict, tool_class)
            # Use a display option to apply to dependent parameters later.
            self._set_display(param_info_dict)
            for p_name, p_value in param_info_dict.items():
                # Change the string to an integer, float, tuple, list, str, dict
                p_value['default'] = pu._dumps(p_value['default'])
                self.param.set(p_name, p_value)

    def _load_param_from_doc(self, tool_class):
        """Find the parameter information from the method docstring.
        This is provided in a yaml format.
        """
        param_info_dict = None
        if hasattr(tool_class, "define_parameters"):
            yaml_text = tool_class.define_parameters.__doc__
            if yaml_text and yaml_text.strip():
                # If yaml_text is not None and not empty or consisting of spaces
                param_info_dict = doc.load_yaml_doc(yaml_text)
                if param_info_dict:
                    if not isinstance(param_info_dict, OrderedDict):
                        error_msg = (
                            f"The parameters have not been read "
                            f"in correctly for {tool_class.__name__}"
                        )
                        raise Exception(error_msg)

        return param_info_dict


    def check_for_default(self, value, param_name, parameters):
        """If the value is changed to be 'default', then set the original
        default value. If the default contains a dictionary, then search
        for the correct value
        """
        param_info_dict = self.param.get_dictionary()
        if str(value) == "default":
            default = param_info_dict[param_name]["default"]
            value = self._set_default(default, parameters, param_name)
        return value

    def _check_required_keys(self, param_info_dict, tool_class):
        """Check the four keys ['dtype', 'description', 'visibility',
        'default'] are included inside the dictionary given for each
        parameter.
        """
        required_keys = ["dtype", "description", "visibility", "default"]
        missing_keys = False
        missing_key_dict = {}

        for p_key, p in param_info_dict.items():
            all_keys = p.keys()
            if p.get("visibility") == "hidden":
                # For hidden keys, only require a default value key
                required_keys = ["default"]

            if not all(d in all_keys for d in required_keys):
                missing_key_dict[p_key] = set(required_keys) - set(all_keys)
                missing_keys = True

        if missing_keys:
            print(
                f"{tool_class.__name__} doesn't contain all of the "
                f"required keys."
            )
            for param, missing_values in missing_key_dict.items():
                print(f"The missing required keys for '{param}' are:")
                print(*missing_values, sep=", ")
            logger.error(f"ERROR: Missing keys inside {tool_class.__name__}")
            raise Exception(f"Please edit {tool_class.__name__}")

    def _check_dtype(self, param_info_dict, tool_class):
        """
        Make sure that the dtype input is valid
        """
        dtype_valid = True
        for p_key, p in param_info_dict.items():
            if isinstance(p["dtype"], list):
                for item in p["dtype"]:
                    if item not in param_u.type_dict:
                        print(
                            f"The {p_key} parameter has been assigned an "
                            f"invalid type '{item}'."
                        )
            else:
                if p["dtype"] not in param_u.type_dict:
                    print(
                        f"The {p_key} parameter has been assigned an invalid"
                        f" type '{p['dtype']}'."
                    )
                    dtype_valid = False
        if not dtype_valid:
            print("The type options are: ")
            type_list = [
                "    {0}".format(key) for key in param_u.type_dict.keys()
            ]
            print(*type_list, sep="\n")
            raise Exception(f"Please edit {tool_class.__name__}")

    def _check_visibility(self, param_info_dict, tool_class):
        """Make sure that the visibility choice is valid"""
        visibility_levels = [
            "basic",
            "intermediate",
            "advanced",
            "datasets",
            "hidden",
            "not",
        ]
        visibility_valid = True
        for p_key, p in param_info_dict.items():
            self._check_data_keys(p_key, p)
            # Check that the data types are valid choices
            if p["visibility"] not in visibility_levels:
                print(
                    f"Inside {tool_class.__name__} the {p_key}"
                    f" parameter is assigned an invalid visibility "
                    f"level '{p['visibility']}'"
                )
                print("Valid choices are:")
                print(*visibility_levels, sep=", ")
                visibility_valid = False

        if not visibility_valid:
            raise Exception(
                f"Please change the file for {tool_class.__name__}"
            )

    def _check_data_keys(self, p_key, p):
        """Make sure that the visibility of dataset parameters is 'datasets'
        so that the display order is unchanged.
        """
        datasets = ["in_datasets", "out_datasets"]
        if p_key in datasets:
            if p["visibility"] != "datasets" and p["visibility"] != "not":
                p["visibility"] = "datasets"

    def _check_options(self, param_info_dict, tool_class):
        """Make sure that option verbose descriptions match the actual
        options
        """
        options_valid = True
        for p_key, p in param_info_dict.items():
            desc = param_info_dict[p_key]["description"]
            if isinstance(desc, dict):
                options = param_info_dict[p_key].get("options")
                option_desc = desc.get("options")
                if options and option_desc:
                    # Check that there is not an invalid option description
                    # inside the option list.
                    invalid_option = [
                        opt for opt in option_desc if opt not in options
                    ]
                    if invalid_option:
                        options_valid = False
                        break

        if options_valid is False:
            raise Exception(
                f"Please check the parameter options for {tool_class.__name__}"
            )

    def _set_display(self, param_info_dict):
        """Initially, set all of the parameters to display 'on'
        This is later altered when dependent parameters need to be shown
        or hidden
        """
        for k, v in param_info_dict.items():
            v["display"] = "on"

    def update_dependent_defaults(self):
        """
        Fix default values for parameters that have a dependency on the value 
        of another parameter, and are in dictionary form.
        """
        for name, pdict in self.get_param_definitions().items():
            if pdict["default"] and isinstance(pdict["default"], dict):
                self.parameters[name] = self.get_dependent_default(pdict)

    def does_exist(self, key, ddict):
        if not key in ddict:
            raise Exception("The dependency %s does not exist" % key)
        return ddict[key]

    def get_dependent_default(self, child):
        """
        Recursive function to replace a dictionary of default parameters with
        a single value.

        Parameters
        ----------
        child : dict
            The parameter definition dictionary of the dependent parameter.

        Returns1
        -------
        value
            The correct default value based on the current value of the
            dependency, or parent, parameter.

        """
        pdefs = self.get_param_definitions()
        parent_name = list(child['default'].keys())[0]
        parent = self.does_exist(parent_name, pdefs)

        # if the parent default is a dictionary then apply the function
        # recursively
        if isinstance(parent['default'], dict):
            self.parameters[parent_name] = \
                self.get_dependent_default(parent['default'])
        return child['default'][parent_name][self.parameters[parent_name]]

    def warn_dependents(self, mod_param, mod_value): # all defaults have already been set at this point - move this somewhere else?
        """
        Find dependents of a modified parameter # complete the docstring
        """
        # find dependents
        for name, pdict in self.get_param_definitions().items():
            default = pdict['default']
            if isinstance(default, OrderedDict):
                parent_name = list(default.keys())[0]
                if parent_name == mod_param:
                    if mod_value in default[parent_name].keys():
                        value = default[parent_name][mod_value]
                        desc = pdict['description']
                        self.make_recommendation(
                            name, desc, parent_name, value)

    def make_recommendation(self, child_name, desc, parent_name, value): # move this somewhere else - configurator?
        desc["range"] = (
            f"The recommended value with the chosen "
            f"{str(parent_name)} would be {str(value)}"
        )
        recommendation = (
            f"It's recommended that you update {str(child_name)}"
            f" to {str(value)}"
        )
        print(Fore.RED + recommendation + Fore.RESET)

    # def check_dependencies(self, parameters):
    #     """
    #     Determine which parameter values are dependent on a parent value and
    #     whether they should be hidden or shown
    #     """
    #     param_info_dict = self.get_param_definitions()
    #     for name, pdict in param_info_dict.items():
    #         if "dependency" in pdict:
    #             if isinstance(pdict, )
        
    def check_dependencies(self, parameters):
        """Determine which parameter values are dependent on a parent
        value and whether they should be hidden or shown
        """
        param_info_dict = self.param.get_dictionary()
        dep_list = {
            k: v["dependency"]
            for k, v in param_info_dict.items()
            if "dependency" in v
        }
        for p_name, dependency in dep_list.items():
            if isinstance(dependency, OrderedDict):
                # There is a dictionary of dependency values
                parent_param_name = list(dependency.keys())[0]
                # The choices which must be in the parent value
                parent_choice_list = dependency[parent_param_name]

                if parent_param_name in parameters:
                    """Check that the parameter is in the current plug in
                    This is relevant for base classes which have several
                    dependent classes
                    """
                    parent_value = parameters[parent_param_name]

                    if str(parent_value) in parent_choice_list:
                        param_info_dict[p_name]["display"] = "on"
                    else:
                        param_info_dict[p_name]["display"] = "off"
            else:
                if dependency in parameters:
                    parent_value = parameters[dependency]
                    if parent_value is None or str(parent_value) == "None":
                        param_info_dict[p_name]["display"] = "off"
                    else:
                        param_info_dict[p_name]["display"] = "on"


    def set_plugin_list_parameters(self, input_parameters):
        """
        This method is called after the plugin has been created by the
        pipeline framework.  It replaces ``self.parameters``
        default values with those given in the input process list. It
        checks for multi parameter strings, eg. 57;68;56;

        :param dict input_parameters: A dictionary of the input parameters
        for this plugin, or None if no customisation is required.
        """
        for key in input_parameters.keys():
            if key in self.parameters.keys():
                new_value = input_parameters[key]
                self.__check_multi_params(
                    self.parameters, new_value, key
                )
            else:
                error = (
                    f"Parameter '{key}' is not valid for plugin "
                    f"{self.plugin_class.name}. \nTry opening and re-saving "
                    f"the process list in the configurator to auto remove "
                    f"\nobsolete parameters."
                )
                raise ValueError(error)

    def __check_multi_params(self, parameters, value, key):
        """
        Convert parameter value to a list if it uses parameter tuning
        and set associated parameters, so the framework knows the new size
        of the data and which plugins to re-run.

        :param parameters: Dictionary of parameters and current values
        :param value: Value to set parameter to
        :param key: Parameter name
        :return:
        """
        plugin = self.plugin_class
        if param_u.is_multi_param(key, value):
            value, error_str = pu.convert_multi_params(key, value)
            if not error_str:
                parameters[key] = value
                label = key + "_params." + type(value[0]).__name__
                plugin.alter_multi_params_dict(
                    len(plugin.get_multi_params_dict()),
                    {"label": label, "values": value},
                )
                plugin.append_extra_dims(len(value))
        else:
            parameters[key] = value

    def define_parameters(self):
        pass

    """
    @dataclass
    class Parameter:
        ''' Descriptor of Parameter Information for plugins
        '''
        visibility: int
        datatype: specific_type
        description: str
        default: int
        Options: Optional[[str]]
        dependency: Optional[]

        def _get_param(self):
            param_dict = {}
            param_dict['visibility'] = self.visibility
            param_dict['type'] = self.dtype
            param_dict['description'] = self.description
            # and the remaining keys
            return param_dict
    """


class PluginCitations(object):
    """Get this citation dictionary so get_dictionary of the metadata type
    should return a dictionary of all the citation info as taken from
    docstring
    """

    def __init__(self):
        super(PluginCitations, self).__init__()
        self.cite = MetaData(ordered=True)

    def set_cite(self, tools_list):
        """Set the citations for each of the tools classes
        :param tools_list: List containing tool classes of parent plugins
        """
        list(
            map(
                lambda tool_class: self._set_plugin_citations(tool_class),
                tools_list
            )
        )

    def _set_plugin_citations(self, tool_class):
        """ Load the parameters for each base class and set values"""
        citations = self._load_cite_from_doc(tool_class)
        if citations:
            for citation in citations.values():
                if self._citation_keys_valid(citation, tool_class):
                    new_citation = CitationInformation(**citation)
                    self.cite.set(new_citation.name, new_citation)
                else:
                    print(f"The citation for {tool_class.__name__} "
                          f"was not saved.")

    def _citation_keys_valid(self, new_citation, tool_class):
        """Check that required citation keys are present. Return false if
        required keys are missing
        """
        required_keys = ["description"]
        # Inside the fresnel filter there is only a description
        citation_keys = [k for k in new_citation.keys()]
        # Check that all of the required keys are contained inside the
        # citation definition
        check_keys = all(item in citation_keys for item in required_keys)
        citation_keys_valid = False if check_keys is False else True

        all_keys = [
            "short_name_article",
            "description",
            "bibtex",
            "endnote",
            "doi",
            "dependency",
        ]
        # Keys which are not used
        additional_keys = [k for k in citation_keys if k not in all_keys]
        if additional_keys:
            print(f"Please only use the following keys inside the citation"
                  f" definition for {tool_class.__name__}:")
            print(*all_keys, sep=", ")
            print("The incorrect keys used:", additional_keys)

        return citation_keys_valid

    def _load_cite_from_doc(self, tool_class):
        """Find the citation information from the method docstring.
        This is provided in a yaml format.

        :param tool_class: Tool to retrieve citation docstring from
        :return: All citations from this tool class
        """
        all_c = OrderedDict()
        # Seperate the citation methods. __dict__ returns instance attributes.
        citation_methods = {key: value
                            for key, value in tool_class.__dict__.items()
                            if key.startswith('citation')}
        for c_method_name, c_method in citation_methods.items():
            yaml_text = c_method.__doc__
            if yaml_text is not None:
                yaml_text = self.seperate_description(yaml_text)
                current_citation = doc.load_yaml_doc(yaml_text)
                if not isinstance(current_citation, OrderedDict):
                    print(f"The citation information has not been read in "
                          f"correctly for {tool_class.__name__}.")
                else:
                    all_c[c_method_name] = current_citation
        return all_c

    def seperate_description(self, yaml_text):
        """Change the format of the docstring to retain new lines for the
        endnote and bibtex and create a key for the description so that
        it be read as a yaml file

        :param yaml_text:
        :return: Reformatted yaml text
        """
        description = doc.remove_new_lines(yaml_text.partition("bibtex:")[0])
        desc_str = "        description:" + description

        bibtex_text = \
            yaml_text.partition("bibtex:")[2].partition("endnote:")[0]
        end_text = \
            yaml_text.partition("bibtex:")[2].partition("endnote:")[2]

        if bibtex_text and end_text:
            final_str = desc_str + '\n        bibtex: |' + bibtex_text \
                      + 'endnote: |' + end_text
        elif end_text:
            final_str = desc_str + '\n        endnote: |' + end_text
        elif bibtex_text:
            final_str = desc_str + '\n        bibtex: |' + bibtex_text
        else:
            final_str = desc_str

        return final_str


class PluginDocumentation(object):
    """Get this documentation dictionary so get_dictionary of
    the metadata type should return a dictionary of all the
    documentation details taken from docstring
    """

    def __init__(self):
        super(PluginDocumentation, self).__init__()
        self.doc = MetaData()

    def set_doc(self, tools_list):
        # Use the tools class at the 'top'
        self.doc.set("verbose", tools_list[-1].__doc__)
        self.doc.set("warn", self.set_warn(tools_list))
        self.set_doc_link()

    def set_warn(self, tools_list):
        """Remove new lines and save config warnings for the child tools
        class only.
        """
        config_str = tools_list[-1].config_warn.__doc__
        if config_str and "\n\n" in config_str:
            # Separate multiple warnings with two new lines \n\n
            config_warn_list = [doc.remove_new_lines(l)
                                for l in config_str.split("\n\n")]
            config_str = '\n'.join(config_warn_list)
        return config_str

    def set_doc_link(self):
        """If there is a restructured text documentation file inside the
        doc/source/documentation folder, then save the link to the page.

        """
        # determine Savu base path
        savu_base_path = \
            os.path.dirname(os.path.realpath(__file__)).split("savu")[0]

        # Locate documentation file
        doc_folder = savu_base_path + "doc/source/documentation"
        module_path = \
            self.plugin_class.__module__.replace(".", "/").replace("savu", "")
        file_ = module_path + "_doc"
        file_name = file_ + ".rst"
        file_path = doc_folder + file_name
        sphinx_link = 'https://savu.readthedocs.io/en/latest/' \
                      'documentation' + file_
        if os.path.isfile(file_path):
            self.doc.set("documentation_link", sphinx_link)

    def config_warn(self):
        pass


class PluginTools(PluginParameters, PluginCitations, PluginDocumentation):
    """Holds all of the parameter, citation and documentation information
    for one plugin class - cls"""

    def __init__(self, cls):
        super(PluginTools, self).__init__()
        self.plugin_class = cls
        self.tools_list = self._find_tools()
        self._set_tools_data()

    def _get_plugin(self):
        return self.plugin_class

    def _find_tools(self):
        """Using the method resolution order, find base class tools"""
        tool_list = []
        for tool_class in self.plugin_class.__class__.__mro__[::-1]:
            plugin_tools_id = tool_class.__module__ + "_tools"
            p_tools = pu.get_tools_class(plugin_tools_id)
            if p_tools:
                tool_list.append(p_tools)
        return tool_list

    def _set_tools_data(self):
        """Populate the parameters, citations and documentation
        with information from all of the tools classes
        """
        self.populate_parameters(self.tools_list)
        self.set_cite(self.tools_list)
        self.set_doc(self.tools_list)

    def get_param_definitions(self):
        """
        Returns
        -------
        dict
            Original parameter definitions read from tools file.
        """
        return self.param.get_dictionary()

    def get_param_values(self):
        """
        Returns
        -------
        dict
            Plugin parameter values for this instance.

        """
        return self.parameters

    def get_citations(self):
        return self.cite.get_dictionary()

    def get_doc(self):
        return self.doc.get_dictionary()
