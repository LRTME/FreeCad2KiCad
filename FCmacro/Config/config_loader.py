import configparser


class ConfigLoader(configparser.ConfigParser):

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
        self.arc_epsilon = int(self["freecad"]["arc_epsilon"])


    def getConfig(self):
        attrs = vars(self)
        # attrs is a dictionary, get values under "_sections" key
        return attrs.get("_sections")