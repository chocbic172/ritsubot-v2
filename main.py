import aiohttp
import asyncio
import os
import datetime

import discord
from discord.ext import commands
from discord.ext.commands import context
from discord.ext.commands.errors import CommandNotFound, UserInputError


from utilities import exceptions
from utilities.config import Config
from entities.guild import GuildCache
from utilities.database import DatabaseClient


class Ritsu(commands.Bot):
    async def get_server_prefix(self, bot: commands.Bot, message: discord.Message):
        if not message.guild:
            return self.prefix
        custom_prefix = await self.retrieve_prefix(message.guild.id)
        result = commands.when_mentioned_or(custom_prefix)(bot, message)
        result.append(self.prefix)
        return result

    async def retrieve_prefix(self, guild_id):
        guild = await self.cache.get(guild_id)
        return guild.prefix

    async def process_commands(self, message: discord.Message):
        ctx = await self.get_context(message, cls=context.Context)

        if ctx.command is None:
            return

        await self.invoke(ctx)

    def __init__(self):
        super().__init__(command_prefix=self.get_server_prefix, case_insensitive=True)
        self.config = Config().get_config()
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.prefix = 'ritsu '

        self.database_client = DatabaseClient(self.config['database']['user'], self.config['database']['password'],
                                              self.config['database']['database'], self.config['database']['host'])

        print('Attempting to connect to database')
        asyncio.get_event_loop().run_until_complete(self.database_client.connect())
        print('Connection successful')

        self.cache = GuildCache(self)

        self.run(self.config['main_bot']['token'])

    async def on_ready(self):
        print('Logged in')
        await self.load_cogs()

        game = discord.Activity(name="ritsu help", type=discord.ActivityType.listening)
        await self.change_presence(status=discord.Status.online, activity=game)

        await self.reconnect()

    async def on_guild_join(self, guild):
        await self.cache.get(guild.id)

    async def on_guild_remove(self, guild):
        await self.cache.delete(guild.id)
        await self.lavalink.remove(guild.id)

    async def on_message(self, msg: discord.Message):
        if msg.author.bot:
            return

        if not msg.channel:
            return

        try:
            await self.process_commands(msg)
        except CommandNotFound:
            return
        except exceptions.OwnerOnlyException:
            await msg.channel.send('WOAH hang on a hot second... only devs can use that command')
        except exceptions.AdminOnlyException:
            await msg.channel.send('WOAH hang on a hot second... only admins of this server can use that command')

    async def on_command_error(self, ctx, err):
        if isinstance(err, CommandNotFound) or isinstance(err, UserInputError):
                return

        embed = discord.Embed(
            title=f'🚫 An internal error occurred!',
            timestamp=datetime.datetime.now(),
            color=0xff6f61,
            description=f'Please contact the developers if this problem persists.'
        )

        print(err)

        await ctx.send(embed=embed)

    async def load_cogs(self):
        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, 'cogs/')
        extensions = os.listdir(filename)

        print('Loading cogs...')

        for file in extensions:
            if file.startswith('__'):
                pass
            else:
                cog = file.split('.')[0]
                self.load_extension(f'cogs.{cog}')

        print('Finished loading cogs.')

    async def reconnect(self):
        async with self.database_client.get_pool().acquire() as conn:
            for guild in await conn.fetch('SELECT * FROM queues'):
                delete = await conn.prepare('DELETE FROM queues WHERE id = $1')
                await delete.fetchval(int(guild['guild_id']))

                player = self.lavalink.players.get(guild['guild_id'])
                player.store('channel', guild['text_channel_id'])

                await player.connect(str(guild['channel_id']))

                track = await self.lavalink.get_tracks(guild['current_track'])
                player.add(requester=self.user.id, track=track['tracks'][0])

                await player.play
                await player.seek(guild['current_position'])

                for queue_track in guild['queue'].replace('[', '').replace(']', '').replace('\'', '').split(', '):
                    track_result = await self.lavalink.get_tracks(queue_track)
                    if not track_result['tracks']:
                        return

                player.add(requester=self.user.id, track=track_result['tracks'][0])


if __name__ == '__main__':
    instance = Ritsu()
