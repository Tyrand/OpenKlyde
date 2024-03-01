import aiohttp
import asyncio
import config
import datetime
import discord
import duckduckgo_search
import functions
import httpx
import importlib
import json
import nltk
import os
import profanity_check
import random
import requests
import wikipedia
from bs4 import BeautifulSoup
import re
from aiohttp import ClientSession
from config import *
from discord import Interaction, app_commands
from discord.ext import commands
from duckduckgo_search import DDGS, AsyncDDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException
from nltk.corpus import wordnet
from profanity_check import predict, predict_prob
import time
from commands import *

intents = discord.Intents.all()
client = commands.Bot(command_prefix="$", intents=intents)
intents.message_content = True
# Create our queues up here somewhere
queue_to_process_message = asyncio.Queue()  # Process messages and send to LLM
queue_to_process_image = asyncio.Queue()  # Process images from SD API
queue_to_send_message = asyncio.Queue()  # Send messages to chat and the user
# Character Card (current character personality)
character_card = {}
# Global card for API information. Used with use_api_backend.
text_api = {}
image_api = {}
status_last_update = None
# Dictionary to keep track of the last message time for each user
last_message_time = {}

async def bot_behavior(message):
    if LogAllMessages:
        # log all messages into separate channel files
        if message.guild:
            await functions.add_to_channel_history(
                message.guild, message.channel, message.author, message.content
            )

    if MessageDebug:
        print('_______________________')
        if message.channel:
            if isinstance(message.channel, discord.DMChannel):
                MessageChannel = "DM"
                MessageGuild = ""
            else:
                MessageChannel = message.channel.name
                MessageGuild = message.guild.name
        print(datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S') + " | " + MessageGuild + " > " + MessageChannel + " | " + message.author.name + ": " + message.content)
    
    # If the message is from a blocked user, don't respond
    if ( message.author.id in BlockedUsers or message.author.name in BlockedUsers ):
        if MessageDebug:
            print("Denied: Blocked user")
        return False

    # Don't respond to yourself or other bots unless specified
    if (
        message.author == client.user
        or message.author.bot and not ReplyToBots
    ):
        if MessageDebug:
            print("Denied: Self or other bot")
        return False
    
    # If the message is empty, don't respond
    if not message.content or message.content == "":
        if MessageDebug:
            print("Denied: Empty message")
        return False


    # If the message starts with a symbol, don't respond.
    if IgnoreSymbols and message.content.startswith((".", ",", "!", "?", ":", "'", "\"", "/", "<", ">", "(", ")", "[", "]", ":", "http")):
            if MessageDebug:
                print("Denied: IgnoreSymbols is True and message starts with a symbol")
            return False

    if message.guild is None:
        if AllowDirectMessages:
            await bot_answer(message)
            return True
        else:
            if MessageDebug:
                print("Denied: AllowDirectMessages is False")
            return False

    # Check if the bot is in specific guild mode - if it is, check if the message is from the correct guild
    if SpecificGuildMode and not (message.guild.id in SpecificGuildModeIDs or message.guild.name in SpecificGuildModeNames):
        if MessageDebug:
            print(f"Denied: Guild id ({message.guild.id}) or name ({message.guild.name}) does not match ({SpecificGuildModeIDs}) or ({SpecificGuildModeNames})")
        return False

    # Check if the bot is in specific channel mode - if it is, check if the message is from the correct channel
    if SpecificChannelMode and not (message.channel.id in SpecificChannelModeIDs or message.channel.name in SpecificChannelModeNames):
        if MessageDebug:
            print(f"Denied: Channel id ({message.channel.id}) or name ({message.channel.name}) does not match ({SpecificChannelModeIDs}) or ({SpecificChannelModeNames})")
        return False

    # Check if mentions are required to trigger the bot    
    if MentionOrReplyRequired and not (client.user.mentioned_in(message) or (message.reference and message.reference.resolved.author == client.user)):
        if MessageDebug:
            print("Denied: MentionOrReplyRequired is True and bot was not mentioned or replied to")
        return False

    # If the message has not yet been returned False, the bot will respond
    if MessageDebug:
        print("Allowed: Bot will respond")

    await bot_answer(message)
    return True

async def bot_answer(message):
    # Check if the user has sent a message within the last UserRateLimitSeconds seconds
    if message.author.id in last_message_time:
        current_time = time.time()
        last_time = last_message_time[message.author.id]
        if current_time - last_time < UserRateLimitSeconds:
            # Ignore rate limit if user is admin
            if (message.guild and message.author.guild_permissions.administrator) or message.author.id in DiscordAccountIDs:
                return True
            await message.add_reaction(RateLimitedEmoji)
            if MessageDebug:
                print(f"Denied: User's last message was {last_time - current_time} seconds ago. UserRateLimitSeconds is {UserRateLimitSeconds}")
            return False
    else:
        last_message_time[message.author.id] = time.time()
    if DenyProfanityInput:
        # Deny the prompt if it doesn't pass the profanity filter
        keywords = ["ethical", "guidelines", "authori", "permission", "consent", "appro", "allow"]
        if (profanity_check.predict_prob([message.content])>=ProfanityRating) or (len([keyword for keyword in keywords if keyword in message.content.lower()]) >= 2):
            await message.add_reaction(ProfanityEmoji)
            return False
    await message.add_reaction(ReactionEmoji)
    user = message.author
    userID = message.author.id
    UserName = message.author.name
    # Clean the user's message to make it easy to read
    user_input = functions.clean_user_message(client,message.clean_content)
    if isinstance(message.channel, discord.TextChannel):
        print(f"{message.channel.name} | {UserName}: {user_input}")
    else:
        print(f"DM | {UserName}: {user_input}")
    # Log the received message
    await functions.write_to_log(f"Received message from {UserName}: {user_input}")
    # Is this an image request?
    image_request = functions.check_for_image_request(user_input)
    character = functions.get_character(character_card)
    global text_api
    if image_request and (message.author.id in DiscordAccountIDs):
        prompt = await functions.create_image_prompt(user_input, character, text_api)
    else:
        Memory = ""
        History = ""
        DDGSearchResultsString = ""
        reply = await get_reply(message)
        if UseGuildMemory and message.guild:
            GuildMemory = str(await functions.get_guild_memory(message.guild, GuildMemoryAmount))
            if GuildMemory is None or GuildMemory == "(None, 0)":
                GuildMemory = ""
            Memory = GuildMemory + Memory
        if UseChannelMemory and message.guild:
            if ChannelHistoryOverride:
                ChannelName = ChannelHistoryOverride
            else:
                ChannelName = message.channel.name
            ChannelMemory = str(await functions.get_channel_memory(message.guild.name, ChannelName, ChannelMemoryAmount))
            if ChannelMemory is None or ChannelMemory == "(None, 0)":
                ChannelMemory = ""
            Memory = ChannelMemory + Memory
        if UseUserMemory:
            Memory = str(await functions.get_user_memory(user, UserMemoryAmount))
            if Memory is None or Memory == "(None, 0)":
                Memory = ""
        if UseChannelHistory and message.guild:
            if ChannelHistoryOverride:
                ChannelName = ChannelHistoryOverride
            else:
                ChannelName = message.channel.name
            ChannelHistory = str(await functions.get_channel_history(message.guild.name, ChannelName, ChannelHistoryAmount))
            if ChannelHistory is None or ChannelHistory == "(None, 0)":
                ChannelHistory = ""
            History = f"[Chat log for channel '{message.channel.name}' begins] " + ChannelHistory + f" [Chat log for channel '{message.channel.name}' ends]" + History
        if UseUserHistory:
            History = str(await functions.get_user_history(user, UserHistoryAmount))
            if History is None or History == "(None, 0)":
                History = ""
        if DuckDuckGoSearch:
            if SynonymRequired:
                for word in nltk.word_tokenize(message.content[:20]):
                    synsets = wordnet.synsets(word)
                    if any(w.lemmas()[0].name() for w in synsets if w.lemmas()[0].name() in ["search", "who", "what", "why", "when", "where"]):
                        break
                else:
                    max_results = 0
            elif DuckDuckGoMaxSearchResultsWithParams and ("inurl:" in message.content or "intitle:" in message.content):
                max_results = DuckDuckGoMaxSearchResultsWithParams
            elif message.content.startswith("!"):
                max_results = 0
            else:
                max_results = DuckDuckGoMaxSearchResults
            if max_results > 0:
                try:
                    DDGSearchResults =  DDGS().text(message.content.split('\n')[0] + " " + reply[:50] + " " + datetime.datetime.now().strftime('%Y/%m/%d'), 
                                max_results=max_results, safesearch='off', region='us-en', backend='api')
                    result_count = 0
                    DDGSearchResultsString = [
                        f"\nTitle: {result['title']}\nLink: {result['href']}\nBody: {result['body']}"
                        for i, result in enumerate(DDGSearchResults)
                    ]
                    if MessageDebug:
                        print(f"DuckDuckGo Search Results: {DDGSearchResultsString}")
                        for i, result in enumerate(DDGSearchResults):
                            print(f"Result {i+1}: {result}")
                except DuckDuckGoSearchException as e:
                    print(f"An error occurred while searching: {e}")
                History = f"[Latest Information: {DDGSearchResultsString}]" + History
        if AllowWikipediaExtracts:
            wikipedia_links = re.findall(r'wikipedia.org/wiki/([^/]+)', message.content)
            if wikipedia_links:
                for link in wikipedia_links:
                    try:
                        page = wikipedia.page(link)
                        History = f"[Wikipedia Page: {page.content}]" + History
                        if MessageDebug:
                            print(f"Wikipedia Page extracted: {link}")
                    except wikipedia.exceptions.DisambiguationError as e:
                        print(f"Wikipedia Disambiguation Error: {e}")
                    except wikipedia.exceptions.PageError as e:
                        print(f"Wikipedia Page Error: {e}")
        History = f"[Current UTC date and time: ({datetime.datetime.now().strftime('%Y-%m-%d %H-%M')}) (Unix time: {int(time.time())})]" + History
        image_request = functions.check_for_image_request(user_input)
        if GenerateImageOnly and image_request:
            character = ""
            character_card["name"] = ""
            character_card["persona"] = ""
            character_card["instructions"] = ""
            Memory = ""
            History = ""
            reply = ""
        prompt = await functions.create_text_prompt(
            f"\n{user_input}",
            user,
            character,
            character_card["name"],
            Memory,
            History,
            reply,
            text_api,
        )
        if PromptDebug:
            print("User Input:", user_input)
            print("User:", user)
            print("Character:", character)
            print("Character Card Name:", character_card['name'])
            print("User Memory:", Memory[:50])
            print("User History:", History[:50])
            print("Reply:", reply)
            print("Text API:", text_api)
    queue_item = {
        "prompt": prompt,
        "message": message,
        "user_input": user_input,
        "UserName": UserName,
        "user": user,
        "BotDisplayName": client.user.display_name,
        "image": image_request,
    }
    queue_to_process_message.put_nowait(queue_item)
    # Send the typing status to the channel so the user knows we're working on it
    await message.channel.typing()

# Get the reply to a message if it's relevant to the conversation
async def get_reply(message):
    reply = ""
    # If the message reference is not none, meaning someone is replying to a message
    if message.reference is not None:
        # Grab the message that's being replied to
        referenced_message = await message.channel.fetch_message(
            message.reference.message_id
        )
        # Verify that the author of the message is bot and that it has a reply
        if (
            referenced_message.reference is not None
            and referenced_message.author == client.user
        ):
            # Grab that other reply as well
            referenced_user_message = await message.channel.fetch_message(
                referenced_message.reference.message_id
            )
            # If the author of the reply is not the same person as the initial user, we need this data
            if referenced_user_message.author != message.author:
                reply = (
                    referenced_user_message.author.name
                    + ": "
                    + referenced_user_message.clean_content
                    + "\n"
                )
                reply = (
                    reply
                    + referenced_message.author.name
                    + ": "
                    + referenced_message.clean_content
                    + "\n"
                )
                reply = functions.clean_user_message(client,reply)
                return reply
        # If the referenced message isn't from the bot, use it in the reply
        if referenced_message.author != client.user:
            reply = (
                referenced_message.author.name
                + ": "
                + referenced_message.clean_content
                + "\n"
            )
            return reply
    return reply

async def handle_llm_response(content, response):
    try:
        llm_response = response
        data = extract_data_from_response(llm_response)
        llm_message = await functions.clean_llm_reply(
            data, content["UserName"], character_card["name"]
        )
        queue_item = {"response": llm_message, "content": content}

        if content["image"]:
            queue_to_process_image.put_nowait(queue_item)
        else:
            queue_to_send_message.put_nowait(queue_item)
    except json.JSONDecodeError:
        await functions.write_to_log(
            "Invalid JSON response from LLM model: " + str(response)
        )


def extract_data_from_response(llm_response):
    try:
        return llm_response["results"][0]["text"]
    except (KeyError, IndexError):
        try:
            return llm_response["choices"][0]["text"]
        except (KeyError, IndexError):
            return ""  # Return an empty string if data extraction fails

async def send_to_model_queue():
    global text_api
    while True:
        # Get the queue item that's next in the list
        content = await queue_to_process_message.get()
        # Add the message to the user's history
        await functions.add_to_user_history(
            content["user_input"],
            content["UserName"],
            content["UserName"],
            content["user"],
        )
        # Log the API request
        await functions.write_to_log(
            f"Sending API request to LLM model: {content['prompt']}"
        )
        async with aiohttp.ClientSession() as session:
            retry_count = 0
            while retry_count < 5:
                await content["message"].channel.typing()
                async with session.post(
                    text_api["address"] + text_api["generation"],
                    headers=text_api["headers"],
                    data=content["prompt"],
                ) as response:
                    response_data = await response.json()
                    # Log the API response
                    await functions.write_to_log(
                        f"Received API response from LLM model: {response_data}"
                    )
                    response_text = response_data["results"][0]["text"]
                    if BadResponseSafeGuards:
                        # Define the pattern to search for
                        Pattern_EmptyMessage = r'[@<>\[\]]'
                        Pattern_PossibleUsername = r'^@'+re.escape(character_card['name'])+r'$'
                        Pattern_CharacterName = r'^@'+re.escape(content['UserName'])+r'$'
                        Pattern_DisplayName = r'^@'+re.escape(content['BotDisplayName'])+r'$'

                        # Check if the response text matches the pattern
                        if (
                            response_text.strip() is None or response_text.strip() == ""
                            or re.search(Pattern_EmptyMessage, response_text[:16], re.IGNORECASE)
                            or re.match(Pattern_PossibleUsername, response_text[:16], re.IGNORECASE)
                            or re.match(Pattern_CharacterName, response_text[:16], re.IGNORECASE)
                            or re.match(Pattern_DisplayName, response_text[:16], re.IGNORECASE)
                            or re.search(r'(?i)chat log for channel', response_text, re.IGNORECASE)
                        ):
                            # Print the reason for catching the response
                            if response_text.strip() is None or response_text.strip() == "":
                                print("Empty message caught")
                            elif re.search(Pattern_EmptyMessage, response_text[:16]):
                                print("Possible username caught:", response_text)
                            elif re.match(Pattern_PossibleUsername, response_text[:16], re.IGNORECASE):
                                print("Character name caught:", response_text)
                            elif re.match(Pattern_CharacterName, response_text[:16], re.IGNORECASE):
                                print("User name caught:", response_text)
                            elif re.match(Pattern_DisplayName, response_text[:16], re.IGNORECASE):
                                print("Bot display name caught:", response_text)
                            elif re.search(r'(?i)chat log for channel', response_text, re.IGNORECASE):
                                print("Chat log caught:", response_text)
                            # Retry by continuing the loop
                            retry_count += 1
                            continue
                        if DenyProfanityOutput and profanity_check.predict([response_text])[0] >= ProfanityRating:
                            # Retry by continuing the loop
                            retry_count += 1
                            continue
                        # Send the response to the next step
                        await handle_llm_response(content, response_data)
                        queue_to_process_message.task_done()
                        break
                    # If the response fails the if statement, the bot will generate a new response, repeat until it's caught in the if statement
                    await asyncio.sleep(
                        0
                    )  # Add a delay to avoid excessive API requests (in seconds)
                retry_count += 1
            if retry_count == 5:
                response_text = '||Could not generate a response correctly after several attempts||'
                print('text: ' + response_text)
                await content['message'].reply(response_text)
                queue_to_process_message.task_done()

async def send_to_stable_diffusion_queue():
    global image_api
    while True:
        image_prompt = await queue_to_process_image.get()
        data = image_api["parameters"]
        data["prompt"] += image_prompt["response"]
        data_json = json.dumps(data)
        await functions.write_to_log(
            "Sending prompt from "
            + image_prompt["content"]["UserName"]
            + " to Stable Diffusion model."
        )
        async with ClientSession() as session:
            async with session.post(
                image_api["link"], headers=image_api["headers"], data=data_json
            ) as response:
                response = await response.read()
                sd_response = json.loads(response)
                image = functions.image_from_string(sd_response["images"][0])
                queue_item = {
                    "response": image_prompt["response"],
                    "image": image,
                    "content": image_prompt["content"],
                }
                queue_to_send_message.put_nowait(queue_item)
                queue_to_process_image.task_done()

# All messages are checked to not be over Discord's 2000 characters limit - They are split at the last new line and sent concurrently if they are
async def send_large_message(original_message, reply_content, file=None):
    max_chars = 2000
    chunks = []
    while len(reply_content) > max_chars:
        last_newline_index = reply_content.rfind("\n", 0, max_chars)
        if last_newline_index == -1:
            last_newline_index = max_chars
        chunk = reply_content[:last_newline_index]
        chunks.append(chunk)
        reply_content = reply_content[last_newline_index:].lstrip()
    chunks.append(reply_content)
    for chunk in chunks:
        if file:
            await original_message.reply(chunk, file=file)
        else:
            await original_message.reply(chunk)

# Reply queue that's used to allow the bot to reply even while other stuff is processing
async def send_to_user_queue():
    while True:
        reply = await queue_to_send_message.get()
        if reply["content"]["image"]:
            image_file = discord.File(reply["image"])
            await send_large_message(
                reply["content"]["message"], reply["response"], image_file
            )
            os.remove(reply["image"])
        else:
            await send_large_message(reply["content"]["message"], reply["response"])
        # Update reactions after message has been sent
        # Add the message to user's history
        await functions.add_to_user_history(
            reply["response"],
            character_card["name"],
            reply["content"]["UserName"],
            reply["content"]["user"],
        )
        queue_to_send_message.task_done()
        await reply["content"]["message"].remove_reaction(ReactionEmoji, client.user)

@client.event
async def on_ready():
    # Let owner known in the console that the bot is now running!
    print(
        f"Discord Bot is up and running on the bot: "+client.user.name+"#"+client.user.discriminator+" ("+str(client.user.id)+")"
    )
    global text_api
    global image_api
    global character_card
    text_api = await functions.set_api("text-default.json")
    text_api["parameters"]["max_length"] = ResponseMaxLength
    image_api = await functions.set_api("image-default.json")
    api_check = await functions.api_status_check(
        text_api["address"] + text_api["model"], headers=text_api["headers"]
    )
    character_card = await functions.get_character_card("default.json")
    # AsynchIO Tasks
    asyncio.create_task(send_to_model_queue())
    asyncio.create_task(send_to_stable_diffusion_queue())
    asyncio.create_task(send_to_user_queue())
    client.tree.add_command(history)
    client.tree.add_command(configuration)
    # client.tree.add_command(personality)
    # client.tree.add_command(character)
    # client.tree.add_command(parameters)

    # Sync current slash commands (commented out unless we have new commands)
    await client.tree.sync()

UserContextLocation = "context\\users"

@client.event
async def on_message(message):
    # Bot will now either do or not do something!
    await bot_behavior(message)

try:
    client.run(discord_api_key)
    
except Exception as e:
    client.close()
    asyncio.sleep(10)  # Add a 10 second delay
    client.run(discord_api_key)
    print("Bot restarted successfully.")
