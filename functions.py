import json
import requests
import os
import asyncio
import re
import base64
from PIL import Image
from io import BytesIO
import datetime
from datetime import datetime
from config import *
from bs4 import BeautifulSoup
import wikipedia
from collections import deque
import logging
from pathlib import Path
import nltk
import aiohttp
from nltk.metrics import edit_distance

async def set_api(config_file):
    # Set API struct from JSON file
    file = get_file_name("configurations", config_file)
    api = {}  # Initialize the api variable
    
    try:
        with open(file, "r", encoding='utf-8') as json_file:
            api.update(json.load(json_file))
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"File {file} not found.")
    except json.JSONDecodeError:
        write_to_log(LogFileLocation, LogFileName, f"Unable to parse {file} as JSON.")
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred: {e}")

    return api

async def api_status_check(link, headers):
    # Check if any API is running
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(link, headers=headers) as response:
                status = response.status == 200
        except aiohttp.ClientError as e:
            write_to_log(
                LogFileLocation,
                LogFileName,
                f"Error occurred: {type(e).__name__}, {e.args}. Language model not currently running."
            )
            status = False
    return status

def get_file_name(directory, file_name):
    # Create file path from name and directory
    return Path(directory) / file_name

async def get_json_file(filename):
    # Read JSON file, return content or None
    try:
        with open(filename, "r", encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"File {filename} not found.")
    except json.JSONDecodeError:
        write_to_log(LogFileLocation, LogFileName, f"Unable to parse {filename} as JSON.")
    except PermissionError:
        write_to_log(LogFileLocation, LogFileName, f"Lack of permissions to read {filename}.")
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred: {str(e)}")

    return None

def write_to_log(LogFileLocation, LogFileName, information):
    # Write a line to the log file
    file = get_file_name(LogFileLocation, LogFileName)
    current_time = datetime.now().replace(microsecond=0)
    text = str(current_time) + " " + information + "\n"
    with open(file, 'a', encoding='utf-8') as f:
        f.write(text)

def check_for_image_request(user_message):
    # Check if user is looking for an image to be generated
    return bool(re.search(r'~(create|generate|draw|show)', user_message, re.IGNORECASE))

async def create_text_prompt(user_input, user, character, bot, memory, history, WebResults, reply, text_api):
    # Create a text prompt for text generation
    prompt = f"{character}{memory}{history}{WebResults}{reply}{user.name}: {user_input}\n{bot}: "
    stop_sequence_key = "stop" if text_api["name"] == "openai" else "stop_sequence"
    stop_sequence = ["You:", f"\n{user.name}:", f"\n{bot}:", f"\n@{bot}"]

    update_dict = {
        "prompt": prompt,
        stop_sequence_key: stop_sequence
    }

    data = text_api["parameters"].copy()
    data.update(update_dict)

    return json.dumps(data)

async def create_image_prompt(user_input, character, text_api):
    # Create an image prompt for image generation
    user_input = user_input.lower()
    subject = f"{character} Please describe yourself in vivid detail." if "of" not in user_input else user_input.split("of", 1)[1]
    
    prompt = (
        f"Below is an instruction that describes a task. Write a response that appropriately completes the request.\n\n"
        f"### Instruction:\nPlease describe the following in vivid detail:{subject}\n\n### Response:\n"
    )
    
    stop_sequence = ["### Instruction:", "### Response:", "You:"]
    data = text_api["parameters"].copy()
    data.update({"prompt": prompt, "stop_sequence": stop_sequence})

    return json.dumps(data)

async def get_user_memory(user, characters):
    # Get user's conversation memory
    file_path = get_file_name("memory\\users", f"{user.name}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            total_lines = contents.count('\n')
            print(f"Accessed: {file_path}")
            print(
                f"Total user_memory characters: {len(contents)}",
                f" | Total user_memory lines: {total_lines}"
            )
            if characters == 0:
                print(
                    "Trimmed user_memory characters: 0",
                    " | Trimmed user_memory lines: 0"
                )
                return ""
            elif len(contents) > characters:
                contents = contents[-characters:]
                trimmed_contents = contents.strip()
                print(
                    f"Trimmed user_memory characters: {len(trimmed_contents)}",
                    f" | Trimmed user_memory lines: {total_lines}",
                )
                return trimmed_contents
            return contents.strip()
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"File {file_path} not found. Where did you lose it?")
        return ""
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred while accessing {file_path}: {e}")
        return ""

async def get_guild_memory(guild, characters):
    # Get guild conversation history
    file_path = get_file_name("memory\\guilds", f"{guild.name}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            total_lines = contents.count('\n')
            print(f"Accessed: {file_path}")
            print(
                f"Total guild_memory characters: {len(contents)}",
                f" | Total guild_memory lines: {total_lines}",
            )
            if characters == 0:
                print(
                    "Trimmed guild_memory characters: 0",
                    " | Trimmed guild_memory lines: 0"
                )
                return ""
            elif len(contents) > characters:
                contents = contents[-characters:]
                trimmed_contents = contents.strip()
                print(
                    f"Trimmed guild_memory characters: {len(trimmed_contents)}",
                    f" | Trimmed guild_memory lines: {total_lines}",
                )
                return trimmed_contents
            return contents.strip()
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"File {file_path} not found. Where did you lose it?")
        return ""
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred while accessing {file_path}: {e}")
        return ""

async def get_channel_memory(GuildName, ChannelName, characters):
    # Get channel conversation memory
    file_path = get_file_name("memory\\guilds", f"{GuildName}\\{ChannelName}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            total_lines = contents.count('\n')
            print(f"Accessed: {file_path}")
            print(
                f"Total channel_memory characters: {len(contents)}",
                f" | Total channel_memory lines: {total_lines}"
            )
            if characters == 0:
                print(
                    "Trimmed channel_memory characters: 0",
                    " | Trimmed channel_memory lines: 0"
                )
                return ""
            elif len(contents) > characters:
                contents = contents[-characters:]
                trimmed_contents = contents.strip()
                print(
                    f"Trimmed channel_memory characters: {len(trimmed_contents)}",
                    f" | Trimmed channel_memory lines: {total_lines}"
                )
                return trimmed_contents
            return contents.strip()
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"File {file_path} not found. Where did you lose it?")
        return ""
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred while accessing {file_path}: {str(e)}")
        return ""

async def get_channel_history(GuildName, ChannelName, characters):
    # Get channel conversation history
    file_path = get_file_name(f"{ContextFolderLocation}\\guilds\\{GuildName}", f"{ChannelName}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            total_lines = contents.count('\n')
            print(f"Accessed: {file_path}")
            print(
                f"Total channel_history characters: {len(contents)}",
                f" | Total channel_history lines: {total_lines}"
            )
            if characters == 0:
                print(
                    "Trimmed channel_history characters: 0",
                    " | Trimmed channel_history lines: 0"
                )
                return ""
            elif len(contents) > characters:
                contents = contents[-characters:]
                trimmed_contents = contents.strip()
                print(
                    f"Trimmed channel_history characters: {len(trimmed_contents)}",
                    f" | Trimmed channel_history lines: {total_lines}"
                )
                return trimmed_contents
            return contents.strip()
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"File {file_path} not found. Where did you lose it?")
        return ""
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred while accessing {file_path}: {str(e)}")
        return ""

async def get_user_history(user, characters):
    # Get user's conversation history
    file_path = get_file_name(f"{ContextFolderLocation}\\users", f"{user.name}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            total_lines = contents.count('\n')
            print(f"Accessed: {file_path}")
            print(
                f"Total user_history characters: {len(contents)}",
                f" | Total user_history lines: {total_lines}"
            )
            if characters == 0:
                print(
                    "Trimmed user_history characters: 0",
                    " | Trimmed user_history lines: 0"
                )
                return ""
            elif characters > 0:
                if len(contents) > characters:
                    contents = contents[-characters:]
                trimmed_contents = contents.strip()
                print(
                    f"Trimmed user_history characters: {len(trimmed_contents)}",
                    f" | Trimmed user_history lines: {total_lines}"
                )
                return trimmed_contents
            else:
                return contents.strip()
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"File {file_path} not found. Where did you lose it?")
        return ""
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred while accessing {file_path}: {str(e)}")
        return ""

async def add_to_user_history(content, user, file):
    # Add message to user's conversation history
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"{user.name}: {content}\n"
    file_name = get_file_name(f"{ContextFolderLocation}\\users", f"{file.name}.txt")
    stamped_message = f"{timestamp} {user.name}: {content}\n"
    stamped_file_name = get_file_name(f"{ContextFolderLocation}\\users", f"{file.name}-stamped.txt")
    if LogNoTextUploads and not content:
        content = "<image or video>"
    if content is not None:
        if AddTimestamp and TimestampSeperateFile:
            await append_text_file(stamped_file_name, stamped_message)
            await append_text_file(file_name, message)
        elif AddTimestamp:
            await append_text_file(file_name, stamped_message)
        else:
            await append_text_file(file_name, message)

async def add_to_channel_history(guild, channel, user, content):
    # Add message to channel's conversation history
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"{user.name}: {content}\n"
    file_name = get_file_name(f"{ContextFolderLocation}\\guilds\\{guild.name}", f"{channel.name}.txt")
    stamped_message = f"{timestamp} {user.name}: {content}\n"
    stamped_file_name = get_file_name(f"{ContextFolderLocation}\\guilds\\{guild.name}", f"{channel.name}-stamped.txt")
    if LogNoTextUploads and not content:
        content = "<image or video>"
    if content is not None:
        if AddTimestamp and TimestampSeperateFile:
            await append_text_file(stamped_file_name, stamped_message)
            await append_text_file(file_name, message)
        elif AddTimestamp:
            await append_text_file(file_name, stamped_message)
        else:
            await append_text_file(file_name, message)

async def get_txt_file(filename, characters):
    # Get contents of a text file
    try:
        with open(filename, "r", encoding="utf-8") as file:
            contents = file.read()[-characters:]
            last_newline_index = contents.rfind("\n")
            if last_newline_index != -1:
                contents = contents[last_newline_index + 1 :]
            print(f"Accessed: {filename}")
            return contents
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"File {filename} not found. Where did you lose it?")
        return ""
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred: {str(e)}")
        return ""

async def prune_text_file(file, trim_to):
    # Prune lines from a text file
    try:
        with open(file, "r", encoding="utf-8") as f:
            lines = deque(f, maxlen=trim_to)
        with open(file, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except FileNotFoundError:
        write_to_log(LogFileLocation, LogFileName, f"Could not prune file {file} because it doesn't exist.")
    except PermissionError:
        write_to_log(LogFileLocation, LogFileName, f"Could not prune file {file} due to lack of permissions.")
    except Exception as e:
        write_to_log(LogFileLocation, LogFileName, f"An unexpected error occurred while pruning {file}: {str(e)}")

async def append_text_file(file, text):
    # Append text to a file
    file_path = Path(file)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(file_path, "a+", encoding="utf-8") as context:
            context.write(text)
    except Exception as e:
        print(f"Failed to write to file {file_path}: {e}")


def clean_user_message(client, user_input):
    # Clean user input to the bot
    global bot_tags_pattern
    bot_tags = [f"@{client.user.name}#{client.user.discriminator}".lower(), f"@{client.user.name}".lower()]
    bot_tags_pattern = re.compile("|".join(map(re.escape, bot_tags)), re.IGNORECASE)
    return bot_tags_pattern.sub("", user_input).strip()

async def clean_llm_reply(MessageContent, user, bot):
    logging.info(f"Starting to clean message for {user.name}")
    
    bot_name_lower = bot.name.lower()
    
    # check the last line of the message, if it contains the bot's name - remove the whole line
    if bot_name_lower in MessageContent.lower().split("\n")[-1]:
        MessageContent = "\n".join(MessageContent.split("\n")[:-1])

    # remove the user's name from the message, including all variations of the name like capitalization and nicknames
    MessageContent = re.sub(rf"\b{user.name}\b:", "", MessageContent, flags=re.IGNORECASE)

    if not AllowBotToMention:
        MessageContent = MessageContent.replace("<@", "<")
        logging.info(f"Replaced '<@' with '<': {MessageContent}")

    MessageContent = re.compile(r"\n{2,}").sub("\n", MessageContent)  # Replace consecutive line breaks with a single line break

    logging.info("Finished cleaning message.")
    return MessageContent.strip()

def get_character(character_card):
    # Get current bot character in prompt-friendly format
    character = f"Your name is {character_card['name']}. You are {character_card['persona']}. {character_card['instructions']}Here is how you speak: \n{', '.join(character_card['examples'])}\n"
    return character

async def get_character_card(name):
    # Get contents of a character file
    file = get_file_name("characters", name)
    contents = await get_json_file(file)
    return contents if contents is not None else {}

def get_file_list(directory):
    # Get list of all available characters
    try:
        dir_path, files = directory + "\\", os.listdir(dir_path)
    except FileNotFoundError:
        files = []
    except OSError:
        files = []
    return files

# Script to add an ratelimit reaction emoji then remove it when the ratelimit is over
async def RateLimitNotice(message,client):
    await message.add_reaction(RateLimitedEmoji)
    await asyncio.sleep(UserRateLimitSeconds)
    await message.remove_reaction(RateLimitedEmoji, client.user)

def image_from_string(image_string):
    # Create an image from a base64-encoded string
    img_data = base64.b64decode(image_string)
    with Image.open(BytesIO(img_data)) as img_obj:
        # Save the image to a temporary file
        temp_file = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        img_obj.save(temp_file)
        return temp_file