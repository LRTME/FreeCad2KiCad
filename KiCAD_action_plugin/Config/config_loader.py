import configparser
import os

# Get the path to log file because configparsed doesn't search for the file in same directory, (FCMacro/Config)
# but in the directory from where the .py file was run
config_directory_path = os.path.dirname(os.path.realpath(__file__))
config_file = os.path.join(config_directory_path, "config.ini").replace("\\", "/")


class ConfigLoader(configparser.ConfigParser):

    def __init__(self):
        super().__init__()

        # Read the file
        super().read(config_file)

        # Convert strings to correct data types, and store as attributes
        self.host = str(self["network"]["host"])
        self.port = int(self["network"]["port"])
        self.max_port_search_range = int(self["network"]["max_port_search_range"])
        self.header = int(self["network"]["header"])
        self.format = str(self["network"]["format"])