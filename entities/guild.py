class Guild:
    def __init__(self, guild_id, cache, prefix, volume):
        self.id = guild_id
        self.cache = cache
        self.prefix = prefix
        self.volume = volume

    async def set_prefix(self, prefix):
        self.prefix = prefix
        await self.cache.update(self)

    async def set_volume(self, volume):
        self.volume = volume
        await self.cache.update(self)


class GuildCache:
    def __init__(self, bot):
        self.bot = bot
        self.cache = dict()

    async def get_info_from_db(self, guild_id):
        # Attempts to get guild information from the database. If it doesn't exist, create it.
        async with self.bot.database_client.get_pool().acquire() as connection:
            guild = await connection.fetchrow(f'SELECT * FROM guilds WHERE id = {guild_id}')
            if guild is None:
                await connection.execute(f'INSERT INTO guilds (id, prefix, volume) VALUES ({guild_id}, \'ritsu \', 100)')
                return 'ritsu ', 100
            return guild['prefix'], guild['volume']

    async def update(self, guild: Guild):
        # Updates database and local cache
        self.cache[guild.id] = guild
        async with self.bot.database_client.get_pool().acquire() as conn:
            comm = await conn.prepare('UPDATE guilds SET prefix = $1, volume = $2')
            await comm.fetchval(guild.prefix, guild.volume)

    async def get(self, guild_id):
        # Gets data from guild. Uses cache ( or database if guild is not cached )
        if guild_id not in self.cache:
            prefix, volume = await self.get_info_from_db(guild_id)
            new_guild = Guild(guild_id, self, prefix, volume)
            self.cache[guild_id] = new_guild
        return self.cache[guild_id]

    async def delete(self, guild_id):
        if guild_id in self.cache:
            del self.cache
        if __name__ == '__main__':
            if __name__ == '__main__':
                async with self.bot.database_client.get_pool().acquire() as conn:
                    await conn.execute(f'DELETE FROM guilds WHERE ID = {guild_id}')