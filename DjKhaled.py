import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
import asyncio
from collections import deque

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

SONG_QUEUES = {}

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix = "!", intents = intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} is online!")
        
@bot.tree.command(name="skip", description="Ohittaa nykyisen biisin.") # Skips the current playing song
async def skip(interaction: discord.Interaction):
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Selkeesti paska viisu. Skipattu.") # Skipped the current song.
    else:
        await interaction.response.send_message("Mitään ei soi???") # Not playing anything to skip.
        
@bot.tree.command(name="pause", description="Keskeyttää parhaillaan toistettavan kappaleen.") # Pause the currently playing song.
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if the bot is in a voice channel
    if voice_client is None:
        return await interaction.response.send_message("En oo kannnulla.") # I'm not in a voice channel.

    # Check if something is actually playing
    if not voice_client.is_playing():
        return await interaction.response.send_message("Mittään ei soi.") # Nothing is currently playing.
    
    # Pause the track
    voice_client.pause()
    await interaction.response.send_message("Yes Sir!") # Playback paused!
    
@bot.tree.command(name="resume", description="Jatka pysäytettyä biisiä.") # Resume the currently paused song.
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if the bot is in a voice channel
    if voice_client is None:
        return await interaction.response.send_message("En oo kannulla.") # I'm not in a voice channel.

    # Check if it's actually paused
    if not voice_client.is_paused():
        return await interaction.response.send_message("Ee oo viisu tauolla.") # I’m not paused right now.
    
    # Resume playback
    voice_client.resume()
    await interaction.response.send_message("Ja jatkuu!") # Playback resumed!
    
@bot.tree.command(name="stop", description="Pysäytä toisto ja tyhjennä jono.") # Stop playback and clear the queue.
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if the bot is in a voice channel
    if not voice_client or not voice_client.is_connected():
        return await interaction.response.send_message("En oo kannulla.") # I'm not connected to any voice channel.

    # Clear the guild's queue
    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    # If something is playing or paused, stop it
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    # (Optional) Disconnect from the channel
    # await voice_client.disconnect()

    await interaction.response.send_message("moi pitää mennä") # Stopped playback and disconnected!
    
@bot.tree.command(name="play", description="Toista kappale tai lisää se jonoon.") # Play a song or add it to the queue.
@app_commands.describe(hakusana="Hakusana") # song_query="Search query"
async def play(interaction: discord.Interaction, hakusana: str):
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel

    if voice_channel is None:
        await interaction.followup.send("Sun pitäs varmaan olla kannulla et jotain kuuluis? Haloo") # You must be in a voice channel.
        return

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    """ ydl_options = {
        "format": "bestaudio[abr<=96]/bestaudio",
        "noplaylist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
    } """
    
    ydl_options = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "js_runtimes": {
        "node": {}
        },
    }

    query = "ytsearch1: " + hakusana
    results = await search_ytdlp_async(query, ydl_options)
    tracks = results.get("entries", [])

    if tracks is None:
        await interaction.followup.send("Ei löydy.") # No results found.
        return

    first_track = tracks[0]
    audio_url = first_track["url"]
    title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(f"Lisätty jonoon: **{title}**") # f"Added to queue: **{title}**"
    else:
        await interaction.followup.send(f"Nyt soi: **{title}**") # f"Now playing: **{title}**"
        await play_next_song(voice_client, guild_id, interaction.channel)
    
async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
        audio_url, title = SONG_QUEUES[guild_id].popleft()
        
        ffmpeg_options = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn", #-c:a libopus -b:a 96k",
        }
    
        source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options, executable="bin//ffmpeg//ffmpeg.exe")
        
        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")
            asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)
        
        voice_client.play(source, after=after_play)
        asyncio.create_task(channel.send(f"Soi nyt: **{title}**")) # f"Now playing: **{title}**"
        
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()
    


bot.run(TOKEN)