import re
import asyncio

import discord
import lavalink
from discord.ext import commands


url_rx = re.compile(r'https?://(?:www\.)?.+')


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        if not hasattr(bot, 'lavalink'):
            bot.lavalink = lavalink.Client(bot.user.id)
            bot.lavalink.add_node(bot.config['lavalink']['host'], bot.config['lavalink']['port'],
                                  bot.config['lavalink']['password'], 'eu', 'default-node')
            bot.add_listener(bot.lavalink.voice_update_handler, 'on_socket_response')

        lavalink.add_event_hook(self.track_hook)

    def cog_unload(self):
        self.bot.lavalink._event_hooks.clear()

    async def cog_before_invoke(self, ctx):
        guild_check = ctx.guild is not None

        if guild_check:
            await self.ensure_voice(ctx)

        return guild_check

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send(error.original)
        print(error)

    async def ensure_voice(self, ctx):
        """ This check ensures that the bot and command author are in the same voicechannel. """
        player = self.bot.lavalink.player_manager.create(ctx.guild.id, endpoint=str(ctx.guild.region))

        should_connect = ctx.command.name in ('play',)

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandInvokeError('Join a voice channel to use music commands <:owo:763815803988475904>')

        if not player.is_connected:
            if not should_connect:
                raise commands.CommandInvokeError('Sorry, I can\'t connect :c')

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if not permissions.connect or not permissions.speak:  # Check user limit too?
                raise commands.CommandInvokeError('I need the `CONNECT` and `SPEAK` permissions.')

            player.store('channel', ctx.channel.id)
            await self.connect_to(ctx.guild.id, str(ctx.author.voice.channel.id))
        else:
            if int(player.channel_id) != ctx.author.voice.channel.id and should_connect:
                player.store('channel', ctx.channel.id)
                await self.connect_to(ctx.guild.id, str(ctx.author.voice.channel.id))
            elif int(player.channel_id) != ctx.author.voice.channel.id:
                raise commands.CommandInvokeError('I can\'t play you music if we\'re not in the same voice channel <:owo:763815803988475904>')

    async def track_hook(self, event):
        if isinstance(event, lavalink.events.QueueEndEvent):
            timeout = asyncio.create_task(self.disconnect(10.0, event.player))
            await timeout
        elif isinstance(event, lavalink.events.TrackStartEvent):
            player = event.player
            channel = player.fetch('last_channel')
            results = player.current
            embed = discord.Embed(title='Now Playing:', description=results.title, color=0x92a8d1)
            msg = await channel.send(embed=embed)
            player.store('now_playing', msg)
        elif isinstance(event, lavalink.events.TrackEndEvent):
            player = event.player
            msg = player.fetch('now_playing')
            if msg:
                await msg.delete()

    async def connect_to(self, guild_id: int, channel_id: str):
        """ Connects to the given voicechannel ID. A channel_id of `None` means disconnect. """
        ws = self.bot._connection._get_websocket(guild_id)
        await ws.voice_state(str(guild_id), channel_id)

    async def disconnect(self, timeout, player):
        await asyncio.sleep(timeout)
        if not player.current:
            await self.connect_to(player.guild_id, 'None')
            ch = player.fetch('channel')
            if ch:
                ch = self.bot.get_channel(ch)
                return await ch.send(embed=discord.Embed(title='Ritsu Disconnected',colour=0xff6f61,
                                                         description="I haven't been used in 5 minutes,"
                                                                     " so i decided to leave :(\nIf you want to keep"
                                                                     " me in the voice channel forever, don\'t bother"
                                                                     " contacting the devs because i cba to add that"
                                                                     " yet :p"), delete_after=30)

    @commands.command(aliases=['p'])
    async def play(self, ctx, *, query: str):
        """ Searches and plays a song from a given query. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        query = query.strip('<>')

        if not url_rx.match(query):
            query = f'ytsearch:{query}'

        results = await player.node.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.send('Ah I couldn\'t find that one :c')

        embed = discord.Embed(color=discord.Color.default())

        # Valid loadTypes are:
        #   TRACK_LOADED    - single video/direct URL)
        #   PLAYLIST_LOADED - direct URL to playlist)
        #   SEARCH_RESULT   - query prefixed with either ytsearch: or scsearch:.
        #   NO_MATCHES      - query yielded no results
        #   LOAD_FAILED     - most likely, the video encountered an exception during loading.
        if results['loadType'] == 'PLAYLIST_LOADED':
            tracks = results['tracks']

            for track in tracks:
                # Add all of the tracks from the playlist to the queue.
                player.add(requester=ctx.author.id, track=track)

            embed.title = 'Added Playlist to Listen Queue :p'
            embed.description = f'{results["playlistInfo"]["name"]} - {len(tracks)} tracks'
        else:
            track = results['tracks'][0]
            embed.title = 'Added Track to Listen Queue :p'
            embed.description = f'[{track["info"]["title"]}]({track["info"]["uri"]})'
            embed.set_thumbnail(url="https://cog-creators.github.io/discord-embed-sandbox/")

            # You can attach additional information to audiotracks through kwargs, however this involves
            # constructing the AudioTrack class yourself.
            track = lavalink.models.AudioTrack(track, ctx.author, recommended=True, title=track["info"]["title"])
            player.add(requester=ctx.author, track=track)
            player.store(key="last_channel", value=ctx.channel)

        await ctx.send(embed=embed)

        # We don't want to call .play() if the player is playing as that will effectively skip
        # the current track.
        if not player.is_playing:
            await player.play()

    @commands.command(aliases=['vol'])
    async def volume(self, ctx, *, query: str):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        embed = discord.Embed(color=discord.Color.default())

        if not player.is_connected:
            return await ctx.send('I\'m not connected to a voice channel haha')

        if not ctx.author.voice or (player.is_connected and ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send('You can\'t change my volume if you\'re not in my voice channel :pensive:')

        if query.isnumeric() and 0 <= int(query) <= 150:
            embed.title = 'Changing music volume'
            embed.description = f'Volume level set to {query}%'
            await player.set_volume(int(query))
        else:
            return await ctx.send('Ah I can\'t do that sorry')

        await ctx.send(embed=embed)

    @commands.command(aliases=['s'])
    async def skip(self, ctx):
        """ Skips the currently playing song """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send('I\'m not connected to a voice channel haha')

        if not ctx.author.voice or (player.is_connected and ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send('You can\'t skip a track if you\'re not in my voice channel :pensive:')

        await player.skip()
        await ctx.send('Got it :) , i\'ll skip to the next song')

    @commands.command()
    async def stop(self, ctx):
        """ Stops the currently playing song """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send('I\'m not connected to a voice channel haha')

        if not ctx.author.voice or (player.is_connected and ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send('You can\'t stop my music if you\'re not in my voice channel :pensive:')

        await player.stop()
        await ctx.send('No worries, i\'ll stop playing for now')

    # @commands.command(aliases=['queue', 'q', 'ls'])
    # async def list(self, ctx, *, query: str):
    #     player = self.bot.lavalink.player_manager.get(ctx.guild.id)
    #     pages = paginate.Page(player.queue, page=int(query), items_per_page=10)
    #     await ctx.send("```nim" + "\n".join(['', '\nNow Playing: ' + player.current.title, '', '-'*25, ''] + ["".join(str(x[0]+1) + ") " + x[1].title) for x in enumerate(player.queue)]) + "```")

    @commands.command(aliases=['dc', 'disconnect'])
    async def leave(self, ctx):
        """ Disconnects Ritsu from the voice channel and clears the queue. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send('I\'m not connected to a voice channel haha')

        if not ctx.author.voice or (player.is_connected and ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send('You can\'t disconnect me if you\'re not in my voice channel :pensive:')

        player.queue.clear()
        await player.stop()
        await self.connect_to(ctx.guild.id, None)
        await ctx.send('Byeeeeeee :wave:')

    @commands.command(aliases=['np'])
    async def now(self, ctx):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        current = player.current

        next_in_queue = f'**Up next:** {player.queue[0].author} - {player.queue[0].title}' if player.queue else \
            'No more songs in queue'

        embed = discord.Embed(title=f'🎶 Now Playing', url=current.uri, color=0x92a8d1,
                              description=f'**{current.author} - {current.title}**')
        embed.set_thumbnail(url='https://img.youtube.com/vi/'+current.uri.split('=')[-1]+'/0.jpg')
        print(current.requester)
        embed.set_footer(text=f"Requested by: {current.requester.nick} "
                              f" [ {current.requester.name}#{current.requester.discriminator} ]",
                         icon_url=current.requester.avatar_url)

        embed.add_field(name='Next In Queue', value=f'{next_in_queue}', inline=False)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Music(bot))
    print("Lavalink Cog Loaded")
