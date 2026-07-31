from Services.TeamService import TeamService
from Services.LeaveService import LeaveService


class ContextService:

    def __init__(self):
        self.team_service = TeamService()
        self.leave_service = LeaveService()

    def get_context(self):

        context = f"""
==========================
TEAM MEMBERS INFORMATION
==========================

{self.team_service.get_context()}

==========================
LEAVE PLAN
==========================

{self.leave_service.get_context()}
"""

        return context