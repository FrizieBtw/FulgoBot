import os
import io
import discord
from discord.ext import commands, tasks
from PIL import Image
import qrcode
import json
import feedparser
import aiohttp
import os

import utils.discord_helpers
import utils.image_utils
import utils.server_management
import utils.tokens_and_keys
 
intents : discord.Intents = discord.Intents.all()
tyrBot : discord.Bot = commands.Bot(intents=intents)

##################### BOT'S EVENTS #####################
@tyrBot.event
async def on_ready() -> None:
    print(f'Connected as {tyrBot.user}')
    check_new_videos.start()
    tyrBot.add_view(utils.discord_helpers.HelpView())
    
@tyrBot.event
async def on_guild_join(guild : discord.Guild) -> None:
    utils.server_management.add_server(guild.id)
    print(f"TyrBot has joined the server: {guild.name} ({guild.id})")
    
@tyrBot.event
async def on_guild_remove(guild : discord.Guild) -> None:
    utils.server_management.remove_from_server_list(guild.id)
    print(f"TyrBot has left the server: {guild.name} ({guild.id})")

@tyrBot.event
async def on_member_join(member : discord.Member) -> None:
    server_id = member.guild.id

    with open(f"data/servers/{server_id}/config.json", 'r', encoding='utf-8') as file:
        config = json.load(file)
    if not config["welcome_system"]["active"]:
        return
    
    background_image_path = config["welcome_system"]["background_image"]
    background_image = Image.open(background_image_path) if background_image_path else Image.open("data/assets/new_member_background.jpg")
      
    welcome_card = await utils.image_utils.generate_welcome_card(member, background_image) 
    
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    await member.guild.system_channel.send(file=discord.File(fp=welcome_card, filename="welcome_card.png"), content=f"{lang['welcome_message']}".format_map({"member": member.mention, "server": member.guild.name}))
    
@tyrBot.event
async def on_message_delete(message : discord.Message) -> None:
    if message.guild:
        utils.server_management.remove_associated_processes(message.id, message.type, message.guild.id)

@tyrBot.event
async def on_raw_reaction_add(payload : discord.RawReactionActionEvent) -> None:
    user_id : int = payload.user_id
    
    if user_id == tyrBot.user.id:
        return
    
    guild_id : int = payload.guild_id
    role_id : int = utils.server_management.get_associated_role_for_emoji(guild_id, payload.message_id, payload.emoji)
    guild : discord.Guild = await tyrBot.fetch_guild(guild_id)
    member : discord.Member = await guild.fetch_member(user_id)
                
    if role_id is not None:
        role : discord.Role = discord.utils.get(guild.roles, id=role_id)
        try:
            await member.add_roles(role)
        except:
            with open(f"data/servers/{guild_id}/config.json", mode="r", encoding="utf8") as file:
                config : dict[str, any] = json.load(file)
            if config["logs_channel_id"]:
                logs_channel : discord.abc.MessageableChannel = await guild.fetch_channel(int(config["logs_channel_id"]))
            with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
                lang : dict[str, any] = json.load(file)
            await logs_channel.send(lang["role_add_delete_error_log"])
        
@tyrBot.event
async def on_raw_reaction_remove(payload : discord.RawReactionActionEvent) -> None:
    user_id : int = payload.user_id
    
    if user_id == tyrBot.user.id:
        return
    
    guild_id : int = payload.guild_id
    role_id : int = utils.server_management.get_associated_role_for_emoji(guild_id, payload.message_id, payload.emoji)
    guild : discord.Guild = await tyrBot.fetch_guild(guild_id)
    member : discord.Member = await guild.fetch_member(user_id)
                
    if role_id is not None:
        role : discord.Role = discord.utils.get(guild.roles, id=role_id)
        try:
            await member.remove_roles(role)
        except:
            with open(f"data/servers/{guild_id}/config.json", mode="r", encoding="utf8") as file:
                config : dict[str, any] = json.load(file)
            if config["logs_channel_id"]:
                logs_channel : discord.TextChannel = await guild.fetch_channel(int(config["logs_channel_id"]))
            with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
                lang : dict[str, any] = json.load(file)
            await logs_channel.send(lang["role_add_delete_error_log"])
               
@tyrBot.event
async def on_voice_state_update(member : discord.Member, before : discord.VoiceState, after : discord.VoiceState) -> None:
    if before.channel and len(before.channel.members) == 0:
        with open(f"data/servers/{member.guild.id}/temp_voice_channels.txt", mode="r", encoding="utf8") as file:
            data : list[str] = file.read().splitlines()
            
        if str(before.channel.id) in data:
            await before.channel.delete()
            with open(f"data/servers/{member.guild.id}/temp_voice_channels.txt", mode="w", encoding="utf8") as file:
                
                for line in data:
                    
                    if line != str(before.channel.id):
                        file.write(f"{line}\n")
    
    if after.channel:
        with open(f"data/servers/{member.guild.id}/config.json") as file:
            config : dict[str, any] = json.load(file)
            
            if str(after.channel.id) in config['join_to_create_channel_system']['join_to_create_channels_id']:
                private_channel : discord.VoiceChannel = await member.guild.create_voice_channel(name=config['join_to_create_channel_system']['channel_name_template'].format_map({"member": member.name}), category=after.channel.category)
                
                with open(f"data/servers/{member.guild.id}/temp_voice_channels.txt", mode="w", encoding="utf8") as file:
                    file.write(f"{private_channel.id}\n")
                await member.move_to(private_channel)                    
                await private_channel.set_permissions(member, connect=True, mute_members=True, deafen_members=True, move_members=True, manage_channels=True, manage_permissions=True)

##################### BOT'S TASKS #####################
@tasks.loop(minutes=5)
async def check_new_videos():
    """
    Verifies if new videos have been uploaded on the youtube channels being watched.
    """
    servers_list : list = os.listdir('data/servers')

    async with aiohttp.ClientSession() as session:
        for server_id in servers_list:
            with open(f"data/servers/{server_id}/config.json", mode="r", encoding="utf8") as file:
                config : dict[str, any] = json.load(file)

            for ytb_channel_id in config["youtube_survey"]["youtube_channels_id"]:
                rss_url : str = f"https://www.youtube.com/feeds/videos.xml?channel_id={ytb_channel_id}"
                feed : feedparser.FeedParserDict = feedparser.parse(rss_url)

                if feed.entries:
                    latest_video_url : str = feed.entries[0].link
                    video_id : str = latest_video_url.split("v=")[-1]

                if video_id != config["youtube_survey"]["youtube_channels_id"][str(ytb_channel_id)]:
                    channel : discord.TextChannel = tyrBot.get_guild(int(server_id)).get_channel(int(config["youtube_survey"]["channel_id"]))

                    # Envoi d'une requête pour récupérer le nom de la chaîne YouTube via l'API REST de YouTube avec aiohttp
                    youtube_api_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id={ytb_channel_id}&key={utils.tokens_and_keys.YOUTUBE_API_KEY}"

                    try:
                        async with session.get(youtube_api_url) as response:
                            if response.status == 200:
                                data = await response.json()
                                if "items" in data and len(data["items"]) > 0:
                                    ytb_channel_name : str = data["items"][0]["snippet"]["title"]
                    except:
                        ytb_channel_name = None
                    await channel.send(config["youtube_survey"]["new_video_message_template"].format_map({
                        "youtube_channel": ytb_channel_name if ytb_channel_name is not None else str(ytb_channel_id),
                        "youtube_video": f"https://www.youtube.com/watch?v={video_id}"
                    }))
                    config["youtube_survey"]["youtube_channels_id"][str(ytb_channel_id)] = video_id

                    with open(f"data/servers/{server_id}/config.json", mode="w", encoding="utf8") as file:
                        json.dump(config, file, indent=4)

##################### NORMAL COMMANDS #####################
@tyrBot.slash_command(name = "help", description = "Displays help about how to use the bot.")
async def help(ctx : commands.Context) -> None:
    """
        Displays the list of available commands.
    """
    embed : discord.Embed = discord.Embed(title="Help", color=0x00ff00)    
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/653287777512849419/1325952141512409149/help_thumbnail.png?ex=677da8a9&is=677c5729&hm=51331b77409b6492f7bec07411ef51eb6bc8256c92977c6d02873d0d2c1cab22&")
    command : discord.commands.SlashCommand = None
    for command in tyrBot.all_commands.values():
        embed.add_field(name=f"/{command.name}", value=command.description, inline=False)
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    embed.add_field(name="Message's templates cheatsheet", value=lang["message_template_cheat_sheet"], inline=False)
    
    embed.set_footer(text="TyrBot - 📖 Help")
    await ctx.respond(embed=embed)

@tyrBot.slash_command(name = "ping", description = "Displays the latency between the bot and the discord API.")
async def ping(ctx : commands.Context) -> None:
    """ 
    Displays the latency between the bot and the discord API.
    """
    await ctx.respond(f"💫 Pong! ({int(tyrBot.latency * 1000)} ms)")

@tyrBot.slash_command(name="qr", description="Generates a QR code from the specified content, sent in DM.")
@discord.option(name="content", description="The content to be encoded in the QR code.")
async def generate_qr(ctx : commands.Context, content: str) -> None:
    """Generates a QR code from the specified content.

    Args:
        content (str): The content to be encoded in the QR code.
    """
    qr : qrcode.QRCode = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(content)
    qr.make(fit=True)
    qr_image : Image.Image = qr.make_image(fill_color="black", back_color="white")
    qr_image_bytes : io.BytesIO = io.BytesIO()
    qr_image.save(qr_image_bytes, format="PNG")
    qr_image_bytes.seek(0)
    if ctx.author.dm_channel is None:
        await ctx.author.create_dm()
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    await ctx.author.dm_channel.send(file=discord.File(qr_image_bytes, "qr_code.png"), content=lang["qr_code_message"])
    await ctx.respond(lang["qr_code_sent"])

##################### ADMIN COMMANDS #####################
@tyrBot.slash_command(name = "set_language", description = "Changes the bot's language.")
@commands.has_permissions(administrator=True)
@discord.option(name="language_prefix", description="The language to be set", choices=["fr", "en"])
async def set_language(ctx : commands.Context, language_prefix : str):
    """
    Sets the bot's language.

    Args:
        language (str): The language to be set.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    config["language"] = language_prefix
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    with open(f"data/templates/{language_prefix}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    await ctx.respond(lang["language_defined"])

@tyrBot.slash_command(name = "set_logs_channel", description = "Defines where the bot will sent important logs.")
@commands.has_permissions(administrator=True)
@discord.option(name="channel", description="The channel to be set as the logs channel.")
async def set_logs_channel(ctx : commands.Context, channel : discord.TextChannel):
    """
    Sets the logs channel for the server.

    Args:
        channel (discord.TextChannel): The channel to be set as the logs channel.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    config["logs_channel_id"] = str(channel.id)
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    await ctx.respond(lang["logs_channel_defined"])
    
@tyrBot.slash_command(name = "switch_welcome_system", description = "Enables/disables the welcome system.")
@commands.has_permissions(administrator=True)
async def switch_welcome_system(ctx : commands.Context):
    """
    Enables/disables the welcome system.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    config["welcome_system"]["active"] = not config["welcome_system"]["active"]
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    await ctx.respond(lang["welcome_system_switched"])
    
@tyrBot.slash_command(name = "set_welcome_background", description = "Defines the background image for the welcome card.")
@commands.has_permissions(administrator=True)
@discord.option(name="background_image", description="The image to be set as the welcome card background.")
async def set_welcome_background(ctx : commands.Context, background_image : discord.Attachment):
    """
    Sets the background image for the welcome card.

    Args:
        background_image (discord.Attachment): The image to be set as the welcome card background.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    await background_image.save(f"data/servers/{ctx.guild.id}/welcome_background.jpg")
    config["welcome_system"]["background_image"] = f"data/servers/{ctx.guild.id}/welcome_background.jpg"
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    await ctx.respond(lang["welcome_background_image_defined"])
    
@tyrBot.slash_command(name = "remove_welcome_background", description = "Removes the personalized welcome card background image.")
@commands.has_permissions(administrator=True)
async def remove_welcome_background(ctx : commands.Context):
    os.remove(f"data/servers/{ctx.guild.id}/welcome_background.jpg")
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    config["welcome_system"]["background_image"] = None
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    await ctx.respond(lang["welcome_background_image_removed"])
    
@tyrBot.slash_command(name = "set_welcome_message_template", description = "Defines the message to be set as the welcome message.")
@commands.has_permissions(administrator=True)
@discord.option(name="message_template", description="The message to be set as the welcome message.")
async def set_welcome_message_template(ctx : commands.Context, message_template : str):
    """
    Sets the welcome message template.

    Args:
        message_template (str): The message to be set as the welcome message.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    config["welcome_system"]["welcome_message_template"] = message_template
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    await ctx.respond(lang["welcome_message_defined"])
    
@tyrBot.slash_command(name = "add_role_react", description = "Adds a role react to a message.")
@commands.has_permissions(administrator=True)
@discord.option(name="emoji", description="The emoji to be used as a role react.")
@discord.option(name="role", description="The role to be assigned when the emoji is clicked.")
@discord.option(name="message_id", description="The id of the message to which the role react will be added.")
@discord.option(name="channel", description="The channel in which the message is located, actual if not specified.", required=False)
async def add_role_react(ctx : commands.Context, emoji: str, role: discord.Role, message_id : str, channel: discord.TextChannel = None):
    """
    Adds a role react to a message.

    Args:
        emoji (str): The emoji to be used as a role react.
        role (discord.Role): The role to be assigned when the emoji is clicked.
        message_id (str): The id of the message to which the role react will be added.
        channel (discord.TextChannel, optional): The channel in which the message is located. If not specified, the actual channel will be used. 
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
        
    if str(message_id) in config["role_react"].keys() and emoji in config["role_react"][str(message_id)].keys():
        await ctx.respond(lang["emoji_already_used"])
        return
        
    config["role_react"][str(message_id)] = {}
    config["role_react"][str(message_id)][emoji] = str(role.id)
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
        
    if channel is None:
        channel : discord.abc.MessageableChannel = ctx.channel
    
    message : discord.PartialMessage = await channel.fetch_message(message_id)
    await message.add_reaction(emoji)
    await ctx.respond(lang["role_react_added"])
 
@tyrBot.slash_command(name = "remove_role_react", description = "Deletes a role react from a message.")
@commands.has_permissions(administrator=True)
@discord.option(name="emoji", description="The emoji to be removed.")
@discord.option(name="message_id", description="The id of the message from which the role react will be removed.")
@discord.option(name="channel", description="The channel in which the message is located, actual if not specified.", required=False)
async def remove_role_react(ctx : commands.Context, emoji: str, message_id : str, channel : discord.TextChannel = None):
    """
    Removes a role react from a message.
    
    Args:
        emoji (str): The emoji to be removed.
        message_id (str): The id of the message from which the role react will be removed.
        channel (discord.TextChannel, optional): The channel in which the message is located. If not specified, the actual channel will be used.
    """ 
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
        
    if not emoji in config["role_react"][message_id].keys():
        ctx.respond(lang["emoji_not_used"])
        return
    
    config["role_react"][str(message_id)].pop(emoji)
    if len(config["role_react"][str(message_id)].keys()) == 0:
        config["role_react"].pop(str(message_id))
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
        
    if channel is None:
        channel : discord.abc.MessageableChannel = ctx.channel
    
    message : discord.PartialMessage = await channel.fetch_message(message_id)
    await message.remove_reaction(emoji, tyrBot.user)
    await ctx.respond(lang["role_react_removed"])
    
@tyrBot.slash_command(name = "add_join_to_create_channel", description = "Adds a private voice channel creator.")
@commands.has_permissions(administrator=True)
@discord.option(name="channel", description="The voice channel to be set as a private voice channel creator.")
async def add_join_to_create_channel(ctx : commands.Context, channel : discord.VoiceChannel):
    """
    Adds a private voice channel creator.

    Args:
        channel (discord.VoiceChannel): The voice channel to be set as a private voice channel creator.
    """
    with open(f"data/servers/{channel.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
        
    if str(channel.id) in config["join_to_create_channel_system"]:
        await ctx.respond(lang["channel_already_used"])
        return
    
    config["join_to_create_channel_system"]["join_to_create_channels_id"].append(str(channel.id))
    with open(f"data/servers/{channel.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    await ctx.respond(lang["join_to_create_channel_added"])
    
@tyrBot.slash_command(name = "remove_join_to_create_channel", description = "Deletes a private voice channel creator.")
@commands.has_permissions(administrator=True)
@discord.option(name="channel", description="The voice channel to be removed from the private voice channel creators.")
async def remove_join_to_create_channel(ctx : commands.Context, channel : discord.VoiceChannel):
    """
    Removes a private voice channel creator.
    
    Args:
        channel (discord.VoiceChannel): The voice channel to be removed from the private voice channel creators.
    """
    with open(f"data/servers/{channel.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
        
    if not str(channel.id) in config["join_to_create_channel_system"]["join_to_create_channels_id"]:
        await ctx.respond(lang["is_not_join_to_create_channel"])
        return
    
    config["join_to_create_channel_system"]["join_to_create_channels_id"].remove(str(channel.id))
    with open(f"data/servers/{channel.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    await ctx.respond(lang["join_to_create_channel_removed"])

@tyrBot.slash_command(name = "add_ytb", description = "Adds a youtube channel to be watched.")
@commands.has_permissions(administrator=True)
@discord.option(name="ytb_channel_id", description="The id of the youtube channel to watched channels.")
@discord.option(name="dc_channel", description="The discord channel in which the new videos will be posted, actual if never specified.", required=False)
async def add_ytb(ctx : commands.Context, ytb_channel_id : str, dc_channel : discord.TextChannel = None):
    """
    Adds a youtube channel to be watched

    Args:
        ytb_channel_id (str): The id of the youtube channel to be watched.
        dc_channel (discord.TextChannel, optional): The discord channel in which the new videos will be posted. If not specified, the actual channel will be used.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
        
    if dc_channel is not None:
        config["youtube_survey"]["channel_id"] = str(dc_channel.id)
        with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
            json.dump(config, file, indent=4)
    else:
        dc_channel : discord.TextChannel = await ctx.guild.fetch_channel(int(config["youtube_survey"]["channel_id"])) if config["youtube_survey"]["channel_id"] else ctx.channel
        if not config["youtube_survey"]["channel_id"]:
            config["youtube_survey"]["channel_id"] = str(dc_channel.id)
            with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
                json.dump(config, file, indent=4)
    
    if ytb_channel_id in config["youtube_survey"]["youtube_channels_id"].keys():
        await ctx.respond(lang["youtube_channel_already_watched"])
        return
    
    config["youtube_survey"]["youtube_channels_id"][str(ytb_channel_id)] = None
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ytb_channel_id}"
    
    try:
        feed : feedparser.FeedParserDict = feedparser.parse(rss_url)
        
        if feed.bozo:
            await ctx.respond(lang)
            return
        
    except:
        await ctx.respond(lang["youtube_channel_fetch_error"])
        return
    
    await ctx.respond(lang["youtube_channel_added"].format_map({"dc_channel_id": dc_channel.id}))
    
@tyrBot.slash_command(name = "remove_ytb", description = "Removes a youtube channel from the watched channels.")
@commands.has_permissions(administrator=True)
@discord.option(name="ytb_channel_id", description="The id of the youtube channel to be removed.")
async def remove_ytb(ctx : commands.Context, ytb_channel_id : str):
    """
    Removes a youtube channel from the watched channels.

    Args:
        ytb_channel_id (str): The id of the youtube channel to be removed.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    
    if not ytb_channel_id in config["youtube_survey"]["youtube_channels_id"].keys():
        await ctx.respond(lang["youtube_channel_not_watched"])
        return
    
    config["youtube_survey"]["youtube_channels_id"].pop(ytb_channel_id)
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    await ctx.respond(lang["youtube_channel_removed"])
        
@tyrBot.slash_command(name="add_help_channel", description="Adds a help ticket system to a text channel.")
@commands.has_permissions(administrator=True)
@discord.option(name="channel", description="The text channel to which the help ticket system will be added.")
@discord.option(name="help_role", description="The role that manages the help tickets.")
@discord.option(name="help_category", description="The category in which the help tickets will be created, actual if never specified.", required=False)
async def add_help_channel(ctx : commands.Context, channel : discord.TextChannel, help_role : discord.Role, help_category : discord.CategoryChannel = None):
    """
    Adds a help ticket system to a text channel.

    Args:
        channel (discord.TextChannel): The text channel to which the help ticket system will be added.
        help_role (discord.Role): The role that manages the help tickets.
        help_category (discord.CategoryChannel, optional): The category in which the help tickets will be created.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
        
    if str(channel.id) in config["help_system"]["channels_id"].keys():
        await ctx.respond(lang["help_system_channel_already_defined"])
        return
    
    if help_category.id is not None:
        config["help_system"]["help_category_id"] = help_category.id
    elif config["help_system"]["help_category_id"]:
        help_category : discord.CategoryChannel = ctx.guild.get_channel(int(config["help_system"]["help_category_id"]))
    else:
        help_category : discord.CategoryChannel = channel.category
        config["help_system"]["help_category_id"] = str(help_category.id) 
        
    config["help_system"]["channels_id"][str(channel.id)] = str(help_role.id)
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
    embed = discord.Embed(title="Help ticket", description=lang["help_ticket_description"], color=discord.Color.green())
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/653287777512849419/1325952141512409149/help_thumbnail.png?ex=677da8a9&is=677c5729&hm=51331b77409b6492f7bec07411ef51eb6bc8256c92977c6d02873d0d2c1cab22&")
    embed.set_footer(text="TyrBot - 🎫 Help")
    view = utils.discord_helpers.HelpView()
    await channel.send(embed=embed, view=view)
    await ctx.respond(lang["help_channel_system_added"])
    
@tyrBot.slash_command(name="remove_help_channel", description="Removes a help ticket system from a text channel.")
@commands.has_permissions(administrator=True)
@discord.option(name="channel", description="The text channel from which the help ticket system will be removed.")
async def remove_help_channel(ctx : commands.Context, channel : discord.TextChannel):
    """
    Removes a help ticket system from a text channel.
    
    Args:
        channel (discord.TextChannel): The text channel from which the help ticket system will be removed.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
        
    if str(channel.id) not in config["help_system"]["channels_id"].keys():
        await ctx.respond(lang["help_system_channel_not_defined"])
        return
        
    del config["help_system"]["channels_id"][str(channel.id)]
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="w", encoding="utf8") as file:
        json.dump(config, file, indent=4)
        
    try:
        await channel.delete()
    except:
        await ctx.respond(lang["help_system_channel_deletion_error"])
        
    await ctx.respond(lang["help_system_channel_removed"])
    
@tyrBot.slash_command(name="export_config", description="Exports the server's configuration.")
@commands.has_permissions(administrator=True)
async def export_config(ctx: commands.Context):
    """
    Exports the server's configuration.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", "rb") as file:
        config_file: io.BytesIO = io.BytesIO(file.read())
        config: dict[str, any] = json.loads(config_file.getvalue().decode())

    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang: dict[str, any] = json.load(file)

    await ctx.respond(file=discord.File(config_file, "config.json"), content=lang["server_config"])
        
@tyrBot.slash_command(name= "import_config", description="Imports a server's configuration.")
@commands.has_permissions(administrator=True)
@discord.option(name="file", description="JSON file containing config (Don't import a random file, it could break the bot in your server)")
async def import_config(ctx : commands.Context, conf_file : discord.Attachment):
    """
    Imports the server's configuration.

    Args:
        file (discord.Attachment): The file containing the configuration to be imported.
    """
    with open(f"data/servers/{ctx.guild.id}/config.json", mode="r", encoding="utf8") as file:
        config : dict[str, any] = json.load(file)
    with open(f"data/templates/{config['language']}_lang.json", mode="r", encoding="utf8") as file:
        lang : dict[str, any] = json.load(file)
    if not conf_file.filename.endswith(".json"):
        await ctx.respond(lang["not_json_file"])
        return
    os.remove(f"data/servers/{ctx.guild.id}/config.json")
    await conf_file.save(f"data/servers/{ctx.guild.id}/config.json")
    await ctx.respond(lang["server_config_imported"])

tyrBot.run(utils.tokens_and_keys.TYR_BOT_TOKEN)