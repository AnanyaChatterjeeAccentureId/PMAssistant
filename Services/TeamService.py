import pandas as pd

class TeamService:

    def __init__(self):
        self.file_path = "Data/TeamMembers.xlsx"

    def load_data(self):
        return pd.read_excel(self.file_path)

    def get_dataframe(self):
        return self.load_data()

    def get_context(self):

        df = self.load_data()

        context = "Team Members Information:\n\n"

        context += df.to_string(index=False)

        return context