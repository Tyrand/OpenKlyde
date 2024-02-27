import os
import discord
import requests
import json
import asyncio
import httpx
import aiohttp
import random
import functions
import datetime
import time
from aiohttp import ClientSession
from discord.ext import commands
from discord import app_commands
from discord import Interaction
import asyncio
import json

# API Keys and Information
# Your API keys and tokens go here. Do not commit with these in place!
discord_api_key = "INSERT_YOUR_DISCORD_BOT_API_KEY_HERE"
ReactionEmoji = "⏲"
PromptDebug = False; # Set to True to print prompt debug information to the console
UserMemoryAmount = 1000
GuildMemoryAmount = 1000
UserContextAmount = 4000
ChannelContextAmount = 4000 # To be implemented
directMessages = False # set to True to allow the bot to respond to direct messages
SingleChannelMode = False # set to True to only track and reply messages from a single channel
SingleChannelModeID = "" # set to the desired channel ID if singleChannelMode is True
SingleChannelModeName = "" # set to the desired channel name if singleChannelMode is True
LogAllMessages = False # set to True to log all messages to a file
IgnoreSymbols = False # set to True to ignore messages which start with common symbols / emojis / URLs

intents = discord.Intents.all()
intents.message_content = True
client = commands.Bot(command_prefix="$", intents=intents)
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


async def bot_behavior(message):
    # If the bot, or another bot, wrote the message, don't respond.
    if (
        message.author == client.user
        or message.author.bot
    ):
        # if message.author == client.user or message.author.bot:
        return False
    
    # If the message is empty, or starts with a symbol, don't respond.
    if IgnoreSymbols:
        if (
            message.content.startswith(
                (".", ",", "!", "?", "'", "\"", "/", "<", ">", "(", ")", "[", "]", ":", "http")
            )
            or message.content is None
        ):
            return False
        
    if SingleChannelMode:
        # If the message is in singleChannelModeID , reply to the message
        if message.channel.id == SingleChannelModeName:
            await bot_answer(message)
            return True
        
    if LogAllMessages:
        # log all messages into seperate channel files
        if message.guild:
            await functions.add_to_channel_history(
                message.guild, message.channel, message.author, message.content
            )

    # If the bot is mentioned in a message, reply to the message
    if client.user.mentioned_in(message):
        await bot_answer(message)
        return True
    
    if directMessages:
        #If someone DMs the bot, reply to them in the same DM
        if message.guild is None and not message.author.bot:
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
    return False


async def bot_answer(message):
    # React to the message so the user knows we're working on it
    await message.add_reaction(ReactionEmoji)
    # Send the typing status to the channel so the user knows we're working on it
    await message.channel.typing()
    user = message.author
    userID = message.author.id
    userName = message.author.name
    # Clean the user's message to make it easy to read
    user_input = functions.clean_user_message(message.clean_content)
    if isinstance(message.channel, discord.TextChannel):
        print(f"{message.channel.name} | {userName}: {user_input}")
    else:
        print(f"DM | {userName}: {user_input}")
    # Log the received message
    await functions.write_to_log(f"Received message from {userName}: {user_input}")
    # Is this an image request?
    image_request = functions.check_for_image_request(user_input)
    character = functions.get_character(character_card)
    global text_api
    if image_request:
        prompt = await functions.create_image_prompt(user_input, character, text_api)
    else:
        reply = await get_reply(message)
        userMemory = str(await functions.get_user_memory(user, UserMemoryAmount))
        if userMemory == "(None, 0)":
            userMemory = ""
        if message.guild:
            guildMemory = str(await functions.get_guild_memory(user, GuildMemoryAmount))
        if guildMemory == "(None, 0)":
            guildMemory = ""
        userMemory = guildMemory + userMemory
        user_history = str(await functions.get_user_history(user, UserContextAmount))
        if user_history == "(None, 0)":
            user_history = ""
        prompt = await functions.create_text_prompt(
            f"\n{user_input}",
            user,
            character,
            character_card["name"],
            userMemory,
            user_history,
            reply,
            text_api,
        )
        if PromptDebug:
            print("User Input:", user_input)
            print("User:", user)
            print("Character:", character)
            print("Character Card Name:", character_card['name'])
            print("User Memory:", userMemory[:50])
            print("User History:", user_history[:50])
            print("Reply:", reply)
            print("Text API:", text_api)
    queue_item = {
        "prompt": prompt,
        "message": message,
        "user_input": user_input,
        "userName": userName,
        "user": user,
        "image": image_request,
    }
    queue_to_process_message.put_nowait(queue_item)


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
                reply = functions.clean_user_message(reply)
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
        llm_response = json.loads(response.decode("utf-8"))
        data = extract_data_from_response(llm_response)
        llm_message = await functions.clean_llm_reply(
            data, content["userName"], character_card["name"]
        )
        queue_item = {"response": llm_message, "content": content}

        if content["image"]:
            queue_to_process_image.put_nowait(queue_item)
        else:
            queue_to_send_message.put_nowait(queue_item)
    except json.JSONDecodeError:
        await functions.write_to_log(
            "Invalid JSON response from LLM model: " + response.decode("utf-8")
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
            content["userName"],
            content["userName"],
            content["user"],
        )
        # Log the API request
        await functions.write_to_log(
            f"Sending API request to LLM model: {content['prompt']}"
        )
        async with aiohttp.ClientSession() as session:
            while True:
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
                    if response_data["results"][0][
                        "text"
                    ].strip() != "" or response_data["results"][0]["text"].startswith(
                        "\n"
                    ):
                        # Send the response to get cleaned of any stop sequences
                        await handle_llm_response(content, response_data)
                        queue_to_process_message.task_done()
                        break
                    # Repeat the loop if response_data["text"] is empty
                    await asyncio.sleep(
                        1
                    )  # Add a delay to avoid excessive API requests


async def send_to_stable_diffusion_queue():
    global image_api
    while True:
        image_prompt = await queue_to_process_image.get()
        data = image_api["parameters"]
        data["prompt"] += image_prompt["response"]
        data_json = json.dumps(data)
        await functions.write_to_log(
            "Sending prompt from "
            + image_prompt["content"]["userName"]
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
            reply["content"]["userName"],
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


UserContextLocation = "context/users"


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
    userName = str(interaction.user.name)
    userName = userName.replace(" ", "")

    file_name = functions.get_file_name(UserContextLocation, str(user.name) + ".txt")

    # Attempt to remove the file and let the user know what happened.
    try:
        os.remove(file_name)
        await interaction.response.send_message(
            "Your conversation history was deleted."
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
    userName = interaction.user.name
    userName = userName.replace(" ", "")

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
    client.run(discord_api_key)
