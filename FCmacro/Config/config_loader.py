""" Read configuration data from file. """

import configparser


class ConfigLoader(configparser.ConfigParser):
    """
    This class is used to read configuration data from file, and convert data to correct type.
    Config data is attached as object attribute for easier use (instead of .get() or [])
    """
    def __init__(self, config_file):
        super().__init__()

        # Read the file
        super().read(config_file)

        # Convert strings to correct data types, and store as attributes
        self.host = str(self["network"]["host"])
        self.port = int(self["network"]["port"])
        self.header = int(self["network"]["header"])
        self.format = str(self["network"]["format"])

        self.models_path = str(self["freecad"]["models_path"])


    def getConfig(self):
        """ Return all attributes for logging/debugging purposes. """
        attrs = vars(self)
        # attrs is a dictionary, get values under "_sections" key
        return attrs.get("_sections")