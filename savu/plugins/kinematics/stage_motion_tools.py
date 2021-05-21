from savu.plugins.plugin_tools import PluginTools

class StageMotionTools(PluginTools):
    """A Plugin to calculate stage motion from motion positions.
    """
    def define_parameters(self):
        """
        in_datasets:
            visibility: datasets
            dtype: list
            description: Create a list of the dataset(s)
            default: ["pmean"]

        out_datasets:
            visibility: datasets
            dtype: list
            description: Create a list of the dataset(s)
            default: ["qmean"]

        use_min_max:
            visibility: intermediate
            dtype: bool
            description: Also use the min and max datasets
              including all combinations of min, mean and max.
            default: False

        extra_in_datasets:
            visibility: intermediate
            dtype: list
            description: The extra datasets to use as input for min and max.
            default: ["pmin", "pmax"]

        extra_out_datasets:
           visibility: intermediate
           dtype: list
           description: The extra datasets to use as output for min and max.
           default: ["qmin", "qmax"]

        """
