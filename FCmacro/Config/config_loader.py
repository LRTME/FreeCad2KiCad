import configparser
import os

# ---| LOGGERS |---

# Get the path to log file because configparsed doesn't search for the file in same directory, (FCMacro/Config)
# but in the directory from where the .py file was run
config_directory_path = os.path.dirname(os.path.realpath(__file__))
#parent_directory_path = os.path.dirname(config_directory_path)
config_file = os.path.join(config_directory_path, "config.ini").replace("\\", "/")

# # Set up all log file names and paths
# log_file_root = os.path.join(parent_directory_path, "Logs", "freecad_root.log").replace("\\", "/")
# log_file_scanner = os.path.join(parent_directory_path, "Logs", "pcb_scanner.log").replace("\\", "/")
#
# # Load logging config data and set log file names with defaults arguments
# logging.config.fileConfig(config_file, defaults={"logfilename_root": log_file_root,
#                                                  "logfilename_scanner": log_file_scanner})
#
#
# def getLogger(logger_name):
#     """ Function that returns a logger object. Logger with logger_name must be defined in config file. """
#     return logging.getLogger(logger_name)
#

# ---| CONFIGURATION DATA |---


class ConfigLoader(configparser.ConfigParser):

    def __init__(self):
        super().__init__()

        # Read the file
        super().read(config_file)

        # Convert strings to correct data types, and store as attributes
        self.host = str(self["network"]["host"])
        self.port = int(self["network"]["port"])
        self.header = int(self["network"]["header"])
        self.format = str(self["network"]["format"])

        self.models_path = str(self["freecad"]["models_path"])
        self.arc_epsilon = int(self["freecad"]["arc_epsilon"])