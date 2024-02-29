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
        print(message.author+": "+message.content)
    
    # Check if message content contains a certain racist word (ignoring casing and possible spacing/characters) it also can not be the bot's own message
    if (message.author != client.user and message.author.id == '203129301418246146'): 
        if re.search(r'\b[nN][iI][gG][gG][eE][rR]\b', message.content):
            await message.add_reaction("⚠")

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
    
    # If the message is empty (an uploaded image), or starts with a symbol, don't respond.
    if IgnoreSymbols:
        if (
            message.content is None
            or message.content.startswith(
                (".", ",", "!", "?", "'", "\"", "/", "<", ">", "(", ")", "[", "]", ":", "http")
            )
        ):
            if MessageDebug:
                print("Denied: Empty message or starts with symbol")
            return False

    if message.guild is None:
        if AllowDirectMessages:
            await bot_answer(message)
            return True
        else:
            if MessageDebug:
                print("Denied: Direct messages not allowed")
            return False

    # Check if the bot is in single guild mode - if it is, check if the message is from the correct guild
    if SingleGuildMode and not (message.guild.id == SingleGuildModeID or message.guild.name == SingleGuildModeName):
        if MessageDebug:
            print("Denied: Guild id or name does not match")
        return False

    # Check if the bot is in single channel mode - if it is, check if the message is from the correct channel
    if SingleChannelMode and not (message.channel.id == SingleChannelModeID or message.channel.name == SingleChannelModeName):
        if MessageDebug:
            print("Denied: Channel id or name does not match")
        return False

    # Check if mentions are required to trigger the bot    
    if MentionOrReplyRequired and not (client.user.mentioned_in(message) or (message.reference and message.reference.resolved.author == client.user)):
        if MessageDebug:
            print("Denied: Bot was not mentioned or replied to")
        return False

    # If the message has not yet been returned False, the bot will respond
    if MessageDebug:
        print("Allowed: Bot will respond")

    await bot_answer(message)
    return True

    # If I haven't spoken for 30 minutes, say something in the last channel where I was pinged (not DMs) with a pun or generated image
    # If someone speaks in a channel, there will be a three percent chance of answering (only in chatbots and furbies)
    # If I'm bored, ping someone with a message history
    # If I have a reminder, pop off the reminder in DMs at selected time and date
    # If someone asks me about the weather, look up weather at a given zip code/location
    # If someone asks me about a wikipedia article, provide the first 300 words from the article's page
    # Google wikipedia and add info to context before answering
    # If someone asks for a random number, roll some dice
    # If someone wants me to be chatty, change personality on the fly to chatterbox
    # If someone asks for a meme, generate an image of a meme on the fly
    # If playing a game or telling a story, add an image to the story

async def bot_answer(message):
    # Check if the user has sent a message within the last UserRateLimitSeconds seconds
    if message.author.id in last_message_time:
        current_time = time.time()
        last_time = last_message_time[message.author.id]
        if current_time - last_time < UserRateLimitSeconds:
            # Ignore rate limit if user is admin
            if (message.guild and message.author.guild_permissions.administrator) or message.author.id == DiscordAccountID:
                return True
            await message.add_reaction(RateLimitedEmoji)
            if MessageDebug:
                print("Denied: Message rate limit exceeded")
            return False
    else:
        last_message_time[message.author.id] = time.time()
    if DenyProfanityInput:
        # Deny the prompt if it doesn't pass the profanity filter
        if profanity_check.predict_prob([message.content])>=ProfanityRating:
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
    if image_request:
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
              if not any(wordnet.synsets(word) for word in nltk.word_tokenize(message.content[:20]) if any(w in wordnet.synsets(word) for w in ["search", "who", "what", "why", "when", "where"])):
               return False
            try:
                DDGSearchResults =  DDGS().text(reply[:100] + " " + message.content[:200] + " " + datetime.datetime.now().strftime('%Y/%m/%d'), 
                               max_results=DuckDuckGoMaxSearchResults, safesearch='off', region='us-en', backend='lite')
                DDGSearchResultsList = list(DDGSearchResults)
                DDGSearchResultsString = "\n".join(str(result) for result in DDGSearchResultsList)
                if MessageDebug:
                    for i, result in enumerate(DDGSearchResultsList):
                        print(f"Result {i+1}: {result}")
            except DuckDuckGoSearchException as e:
                print(f"An error occurred while searching: {e}")
            History = f"[Latest Information: {DDGSearchResultsString}]" + History
        History = f"[Current UTC date and time: " + datetime.datetime.now().strftime('%Y-%m-%d %H-%M')+"]" + History
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
                        if (
                            # Prevent the bot from trying to send empty messages
                            response_text.strip() is None 
                            or response_text.strip() == ""
                            # Common error where the bot immediately says its own name
                            # We don't want to send this to the next step because it would get cleaned and become an empty message
                            or re.search(r'[@^:<>\[\]]', response_text[:16], re.IGNORECASE)
                            or re.match(r'^@' + re.escape(character_card['name']) + r'$', response_text[:16], re.IGNORECASE)
                            or re.match(r'^@' + re.escape(content['UserName']) + r'$', response_text[:16], re.IGNORECASE)
                            or re.match(r'^@' + re.escape(content['BotDisplayName']) + r'$', response_text[:16], re.IGNORECASE)
                            or re.search(r'(?i)chat log for channel', response_text, re.IGNORECASE)
                        ):
                            # Print the reason for catching the response
                            if response_text.strip() is None or response_text.strip() == "":
                                print("Empty message caught")
                            elif re.search(r'[@^:<>\[\]]', response_text[:16]):
                                print("Bot name caught:", response_text)
                            elif re.match(r'^@' + re.escape(character_card['name']) + r'$', response_text[:16], re.IGNORECASE):
                                print("Character name caught:", response_text)
                            elif re.match(r'^@' + re.escape(content['UserName']) + r'$', response_text[:16], re.IGNORECASE):
                                print("User name caught:", response_text)
                            elif re.match(r'^@' + re.escape(content['BotDisplayName']) + r'$', response_text[:16], re.IGNORECASE):
                                print("Bot display name caught:", response_text)
                            elif re.search(r'(?i)chat log for channel', response_text, re.IGNORECASE):
                                print("Chat log caught:", response_text)
                            # Retry by continuing the loop
                                print(retry_count)
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
                        1
                    )  # Add a delay to avoid excessive API requests (in seconds)
                retry_count += 1
            if retry_count == 5:
                response_text = '||Could not generate a response correctly after several attempts||'
                print('results: '+[{'text': response_text}])
                await handle_llm_response(content, response_text)
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
        await reply["content"]["message"].remove_reaction(ReactionEmoji, client.user)
        # Add the message to user's history
        await functions.add_to_user_history(
            reply["response"],
            character_card["name"],
            reply["content"]["UserName"],
            reply["content"]["user"],
        )
        queue_to_send_message.task_done()

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

# Slash command to update the bot's personality
personality = app_commands.Group(
    name="personality", description="View or change the bot's personality."
)

@personality.command(name="view", description="View the bot's personality profile.")
async def view_personality(interaction):
    # Display current personality.
    await interaction.response.send_message(
        "The bot's current personality: **" + character_card["persona"] + "**."
    )

@personality.command(name="set", description="Change the bot's personality.")
@app_commands.describe(persona="Describe the bot's new personality.")
async def edit_personality(interaction, persona: str):
    global character_card
    # Update the global variable
    old_personality = character_card["persona"]
    character_card["persona"] = persona
    # Display new personality, so we know where we're at
    await interaction.response.send_message(
        "Bot's personality has been updated from \""
        + old_personality
        + '" to "'
        + character_card["persona"]
        + '".'
    )

@personality.command(
    name="reset", description="Reset the bot's personality to the default."
)
async def reset_personality(interaction):
    global character_card
    # Update the global variable
    old_personality = character_card["persona"]
    character_card = await functions.get_character_card("default.json")
    # Display new personality, so we know where we're at
    await interaction.response.send_message(
        "Bot's personality has been updated from \""
        + old_personality
        + '" to "'
        + character_card["persona"]
        + '".'
    )

# Slash commands to update the conversation history
history = app_commands.Group(
    name="conversation-history", description="View or change the bot's personality."
)

@history.command(
    name="reset", description="Reset your conversation history with the bot."
)
async def reset_history(interaction):
    user = interaction.user
    UserName = str(interaction.user.name)
    UserName = UserName.replace(" ", "")

    file_name = functions.get_file_name(UserContextLocation, str(user.name) + ".txt")

    # Attempt to remove or rename the file based on the condition
    try:
        if RenameOldUserHistory:
            new_file_name = file_name + "_" + datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            os.rename(file_name, new_file_name)
            await interaction.response.send_message(
                "Your conversation history was reset."
            )
            print("Conversation history file '{}' renamed to '{}'.".format(file_name, new_file_name))
        else:
            os.remove(file_name)
            await interaction.response.send_message(
                "Your conversation history was reset."
            )
            print("Conversation history file '{}' deleted.".format(file_name))
    except FileNotFoundError:
        await interaction.response.send_message("There was no history to delete.")
    except PermissionError:
        await interaction.response.send_message(
            "The bot doesn't have permission to reset your history. Let bot owner know."
        )
    except Exception as e:
        print(e)
        await interaction.response.send_message(
            "Something has gone wrong. Let bot owner know."
        )

# @history.command(name="view", description=" View the last 20 lines of your conversation history.")
async def view_history(interaction):
    # Get the user who started the interaction and find their file.

    user = interaction.user
    UserName = interaction.user.name
    UserName = UserName.replace(" ", "")

    file_name = functions.get_file_name(UserContextLocation, str(user.name) + ".txt")

    try:
        with open(
            file_name, "r", encoding="utf-8"
        ) as file:  # Open the file in read mode
            contents = file.readlines()
            contents = contents[-20:]
            history_string = "".join(contents)
            await interaction.response.send_message(history_string)
    except FileNotFoundError:
        await interaction.response.send_message("You have no history to display.")
    except Exception as e:
        print(e)
        await interaction.response.send_message(
            "Message history is more than 2000 characters and can't be displayed."
        )

# Slash commands for character card presets (if not interested in manually updating)
character = app_commands.Group(
    name="character-cards",
    description="View or changs the bot's current character card, including name and image.",
)

# Command to view a list of available characters.
@character.command(
    name="change", description="View a list of current character presets."
)
async def change_character(interaction):

    # Get a list of available character cards
    character_cards = functions.get_file_list("characters")
    options = []

    # Verify the list is not currently empty
    if not character_cards:
        await interaction.response.send_message(
            "No character cards are currently available."
        )
        return

    # Create the selector list with all the available options.
    for card in character_cards:
        options.append(discord.SelectOption(label=card, value=card))

    select = discord.ui.Select(placeholder="Select a character card.", options=options)
    select.callback = character_select_callback
    view = discord.ui.View()
    view.add_item(select)

    # Show the dropdown menu to the user
    await interaction.response.send_message(
        "Select a character card", view=view, ephemeral=True
    )

async def character_select_callback(interaction):

    await interaction.response.defer()

    # Get the value selected by the user via the dropdown.
    selection = interaction.data.get("values", [])[0]

    # Adjust the character card for the bot to match what the user selected.
    global character_card

    character_card = await functions.get_character_card(selection)

    # Change bot's nickname without changing its name
    guild = interaction.guild
    me = guild.me
    await me.edit(nick=character_card["name"])

    # Let the user know that their request has been completed
    await interaction.followup.send(
        interaction.user.name
        + " updated the bot's personality to "
        + character_card["persona"]
        + "."
    )

# Slash commands for character card presets (if not interested in manually updating)
parameters = app_commands.Group(
    name="model-parameters",
    description="View or changs the bot's current LLM generation parameters.",
)

# Command to view a list of available characters.
@parameters.command(
    name="change", description="View a list of available generation parameters."
)
async def change_parameters(interaction):

    # Get a list of available character cards
    presets = functions.get_file_list("configurations")
    options = []

    # Verify the list is not currently empty
    if not presets:
        await interaction.response.send_message(
            "No configurations are currently available. Please contact the bot owner."
        )
        return

    # Create the selector list with all the available options.
    for preset in presets:
        if preset.startswith("text"):
            options.append(
                discord.SelectOption(label=character_card, value=character_card)
            )

    select = discord.ui.Select(placeholder="Select a character card.", options=options)
    select.callback = parameter_select_callback
    view = discord.ui.View()
    view.add_item(select)

    # Show the dropdown menu to the user
    await interaction.response.send_message(
        "Select a character card", view=view, ephemeral=True
    )

async def parameter_select_callback(interaction):

    await interaction.response.defer()

    # Get the value selected by the user via the dropdown.
    selection = interaction.data.get("values", [])[0]

    # Adjust the character card for the bot to match what the user selected.
    global text_api
    text_api = await functions.set_api(selection)
    api_check = await functions.api_status_check(
        text_api["address"] + text_api["model"], headers=text_api["headers"]
    )

    # Let the user know that their request has been completed
    await interaction.followup.send(
        interaction.user.name + " updated the bot's sampler parameters. " + api_check
    )

try:
    client.run(discord_api_key)
except Exception as e:
    client.close()
    asyncio.sleep(10)  # Add a 10 second delay
    client.run(discord_api_key)
    print("Bot restarted successfully.")