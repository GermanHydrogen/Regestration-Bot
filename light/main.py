import os

import datetime
import logging

from discord.ext.commands import Bot

from commands.admin import Admin
from commands.user import User
from commands.moderator import Moderator
from commands.objects.state import ClientState
from commands.objects.guildconfig import RoleConfig
from util import Util

from config.loader import cfg

''' --- onLoad ----'''
client = Bot(command_prefix="!", case_insensitive=True)

client.remove_command("help")

path = os.path.dirname(os.path.abspath(__file__))


#load log

TODAY = datetime.date.today()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename=path + f"/logs/{TODAY}.log", encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s'))
logger.addHandler(handler)

discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.DEBUG)
discord_handler = logging.FileHandler(filename=path + '/logs/discord.log', encoding='utf-8', mode='w')
discord_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
discord_logger.addHandler(discord_handler)


''' ---        ----'''

state = ClientState()
guildConfig = RoleConfig(os.path.join(path, 'config', 'guildConfig.yml'))
guildConfig.load()

client.add_cog(Admin(client=client, state=state, guild_config=guildConfig))
client.add_cog(Moderator(client=client, state=state, guild_config=guildConfig))
client.add_cog(User(client=client, state=state, guild_config=guildConfig))
client.add_cog(Util(logger=logger))

client.run(cfg['token'])
