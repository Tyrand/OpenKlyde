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

def scrape_webpage(WebLink, WebResults):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }
    try:
        response = requests.get(WebLink, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Remove script and style tags
        for script in soup(["script", "style"]):
            script.extract()
        # Get the plain text
        WebLinkText = soup.get_text()
        # Remove leading and trailing white spaces
        WebLinkText = WebLinkText.strip()
        # Remove extra white spaces and newlines
        WebLinkText = re.sub('\s+', ' ', WebLinkText)
        WebLinkTextTrimmed = WebLinkText[:WebpageScrapeLength]
        WebResults += f"[{WebLink} | {WebLinkTextTrimmed}]"
        if MessageDebug:
            print(f"Webpage scraped: {WebLink} | {WebLinkTextTrimmed}\n____________________")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while scraping webpage: {e}")
def extract_wikipedia_page(WikipediaLink, WebResults):
    try:
        search_results = wikipedia.search(WikipediaLink)
        if search_results:
            top_result = search_results[0]
            WikipediaPage = wikipedia.page(top_result).content
            WikipediaPageTrimmed = WikipediaPage[:WikipediaExtractLength]
            WebResults = f"[{WikipediaPageTrimmed}]" + WebResults
            if MessageDebug:
                print(f"Wikipedia Page extracted: {top_result}")
                print(f"Wikipedia Page Content {WikipediaPageTrimmed}\n____________________")
        else:
            print(f"No Wikipedia results found for: {WikipediaLink}")
    except wikipedia.exceptions.PageError as e:
        print(f"Wikipedia Page Error: {e}")
        pass
async def set_api(config_file):
    # Set API struct from JSON file
    file = get_file_name("configurations", config_file)
    contents = await get_json_file(file)
    api = {}  # Initialize the api variable
    if contents is not None:
        api.update(contents)
    return api

async def api_status_check(link, headers):
    # Check if any API is running
    try:
        response = requests.get(link, headers=headers)
        status = response.ok
    except requests.exceptions.RequestException as e:
        await write_to_log(
            "Error occurred: " + e + ". Language model not currently running."
        )
        status = False
    return status

def get_file_name(directory, file_name):
    # Create file path from name and directory
    return os.path.join(directory, file_name)

async def get_json_file(filename):
    # Read JSON file, return content or None
    try:
        with open(filename, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        await write_to_log("File " + filename + " not found. Where did you lose it?")
        return None
    except json.JSONDecodeError:
        await write_to_log("Unable to parse " + filename + " as JSON.")
        return None
    except Exception as e:
        await write_to_log("An unexpected error occurred: " + e)
        return None

async def write_to_log(information):
    # Write a line to the log file
    file = get_file_name("", "log.txt")
    current_time = datetime.now().replace(microsecond=0)
    text = str(current_time) + " " + information + "\n"
    await append_text_file(file, text)

def check_for_image_request(user_message):
    # Check if user is looking for an image to be generated
    user_message = user_message.lower()
    pattern = re.compile('~(create|generate|draw|show)')
    return bool(pattern.search(user_message))

async def create_text_prompt(
    user_input, user, character, bot, memory, history, WebResults, reply, text_api
):
    # Create a text prompt for text generation
    prompt = f"{character}{memory}{history}{WebResults}{reply}{user.name}: {user_input}\n{bot}: "
    # stop_sequence = [f"{user.name}:", f"{bot}:", "You:"]
    stop_sequence = [f"{user.name}:", f"{bot}:", f"@{bot}", "You:"]
    data = text_api["parameters"]
    data.update({"prompt": prompt})
    data.update(
        {"stop": stop_sequence}
        if text_api["name"] == "openai"
        else {"stop_sequence": stop_sequence}
    )
    return json.dumps(data)

async def create_image_prompt(user_input, character, text_api):
    # Create an image prompt for image generation
    user_input = user_input.lower()
    subject = (
        user_input.split("of", 1)[1]
        if "of" in user_input
        else character + "Please describe yourself in vivid detail."
    )
    prompt = f"Below is an instruction that describes a task. Write a response that appropriately completes the request.\n\n### Instruction:\nPlease describe the following in vivid detail:{subject}\n\n### Response:\n"
    stop_sequence = ["### Instruction:", "### Response:", "You:"]
    data = text_api["parameters"]
    data.update({"prompt": prompt})
    data.update(
        {"stop": stop_sequence}
        if text_api["name"] == "openai"
        else {"stop_sequence": stop_sequence}
    )
    return json.dumps(data)

async def get_user_memory(user, characters):
    # Get user's conversation memory
    file_path = get_file_name("memory\\users", f"{user.name}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            print("Accessed:", file_path)
            print(
                "Total user_memory characters:",
                len(contents),
                "Total user_memory lines:",
                contents.count("\n"),
            )
            if len(contents) > characters:
                contents = contents[-characters:]
            trimmed_contents = contents.strip()
            print(
                "Trimmed user_memory characters:",
                len(trimmed_contents),
                "Trimmed user_memory lines:",
                trimmed_contents.count("\n"),
            )
            return trimmed_contents
    except FileNotFoundError:
        await write_to_log(f"File {file_path} not found. Where did you lose it?")
        return None, 0
    except Exception as e:
        await write_to_log(
            f"An unexpected error occurred while accessing {file_path}: {e}"
        )
        return None, 0

async def get_guild_memory(guild, characters):
    # Get guild conversation history
    file_path = get_file_name("memory\\guilds", f"{guild.name}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            print("Accessed:", file_path)
            print(
                "Total guild_memory characters:",
                len(contents),
                "Total guild_memory lines:",
                contents.count("\n"),
            )
            if len(contents) > characters:
                contents = contents[-characters:]
            trimmed_contents = contents.strip()
            print(
                "Trimmed guild_memory characters:",
                len(trimmed_contents),
                "Trimmed guild_memory lines:",
                trimmed_contents.count("\n"),
            )
            return trimmed_contents
    except FileNotFoundError:
        await write_to_log(f"File {file_path} not found. Where did you lose it?")
        return None, 0
    except Exception as e:
        await write_to_log(
            f"An unexpected error occurred while accessing {file_path}: {e}"
        )
        return None, 0

async def get_channel_memory(GuildName, ChannelName, characters):
    # Get channel conversation memory
    file_path = get_file_name(f"memory\\guilds\\{GuildName}", f"{ChannelName}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            print("Accessed:", file_path)
            print(
                "Total channel_memory characters:",
                len(contents),
                "Total channel_memory lines:",
                contents.count("\n"),
            )
            if len(contents) > characters:
                contents = contents[-characters:]
            trimmed_contents = contents.strip()
            print(
                "Trimmed channel_memory characters:",
                len(trimmed_contents),
                "Trimmed channel_memory lines:",
                trimmed_contents.count("\n"),
            )
            return trimmed_contents
    except FileNotFoundError:
        await write_to_log(f"File {file_path} not found. Where did you lose it?")
        return None, 0
    except Exception as e:
        await write_to_log(
            f"An unexpected error occurred while accessing {file_path}: {e}"
        )
        return None, 0

async def get_channel_history(GuildName, ChannelName, characters):
    # Get channel conversation history
    file_path = get_file_name(f"context\\guilds\\{GuildName}", f"{ChannelName}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            print("Accessed:", file_path)
            print(
                "Total channel_history characters:",
                len(contents),
                "Total channel_history lines:",
                contents.count("\n"),
            )
            if len(contents) > characters:
                contents = contents[-characters:]
            trimmed_contents = contents.strip()
            print(
                "Trimmed channel_history characters:",
                len(trimmed_contents),
                "Trimmed channel_history lines:",
                trimmed_contents.count("\n"),
            )
            return trimmed_contents
    except FileNotFoundError:
        await write_to_log(f"File {file_path} not found. Where did you lose it?")
        return None, 0
    except Exception as e:
        await write_to_log(
            f"An unexpected error occurred while accessing {file_path}: {e}"
        )
        return None, 0

async def get_user_history(user, characters):
    # Get user's conversation history
    file_path = get_file_name("context\\users", f"{user.name}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            contents = file.read()
            print("Accessed:", file_path)
            print(
                "Total user_history characters:",
                len(contents),
                "Total user_history lines:",
                contents.count("\n"),
            )
            if len(contents) > characters:
                contents = contents[-characters:]

            trimmed_contents = contents.strip()
            print(
                "Trimmed user_history characters:",
                len(trimmed_contents),
                "Trimmed user_history lines:",
                trimmed_contents.count("\n"),
            )
            return trimmed_contents
    except FileNotFoundError:
        await write_to_log(f"File {file_path} not found. Where did you lose it?")
        return None, 0
    except Exception as e:
        await write_to_log(
            f"An unexpected error occurred while accessing {file_path}: {e}"
        )
        return None, 0

async def add_to_user_history(content, UserName, file, user):
    # Add message to user's conversation history
    file_name = get_file_name("context\\users", f"{user.name}.txt")
    if LogNoTextUploads and not content:
        content = "<image or video>"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if AddTimestamp:
        message = f"{timestamp} {UserName}: {content}\n"
    else:
        message = f"{UserName}: {content}\n"
    if content is not None:
        await append_text_file(file_name, message)

async def add_to_channel_history(guild, channel, user, content):
    # Add message to channel's conversation history
    file_name = get_file_name("context\\guilds\\" + guild.name, f"{channel.name}.txt")
    if LogNoTextUploads and not content:
        content = "<image or video>"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if AddTimestamp:
        message = f"{timestamp} {user.name}: {content}\n"
    else:
        message = f"{user.name}: {content}\n"
    if content is not None:
        await append_text_file(file_name, message)

async def get_txt_file(filename, characters):
    # Get contents of a text file
    try:
        with open(filename, "r", encoding="utf-8") as file:
            contents = file.read()[-characters:]
            last_newline_index = contents.rfind("\n")
            if last_newline_index != -1:
                contents = contents[last_newline_index + 1 :]
            print("Accessed: ", filename)
            return contents, len(contents)
    except FileNotFoundError:
        await write_to_log(f"File {filename} not found. Where did you lose it?")
        return None, 0
    except Exception as e:
        await write_to_log(f"An unexpected error occurred: {e}")
        return None, 0

async def prune_text_file(file, trim_to):
    # Prune lines from a text file
    try:
        with open(file, "r", encoding="utf-8") as f:
            contents = f.readlines()[-trim_to:]
        with open(file, "w", encoding="utf-8") as f:
            f.writelines(contents)
    except FileNotFoundError:
        await write_to_log(f"Could not prune file {file} because it doesn't exist.")

async def append_text_file(file, text):
    # Append text to a file
    directory = os.path.dirname(file)
    absolute_directory = os.path.abspath(directory)
    if not os.path.exists(absolute_directory):
        os.makedirs(absolute_directory)
    with open(file, "a+", encoding="utf-8") as context:
        context.write(text)

def clean_user_message(client,user_input):
    # Clean user input to the bot
    bot_tags = [re.escape(f"@{client.user.name}#{client.user.discriminator}").lower(), re.escape(f"@{client.user.name}").lower()]
    pattern = re.compile("|".join(bot_tags), re.IGNORECASE)
    cleaned_input = pattern.sub("", user_input)
    return cleaned_input.strip()

async def clean_llm_reply(message, UserName, bot):
    # Clean generated reply
    bot_lower, UserName_lower = bot.lower(), UserName.lower()
    pattern = re.compile(
        re.escape(bot_lower) + r":|" + re.escape(UserName_lower) + r":|You:",
        re.IGNORECASE,
    )
    cleaned_message = pattern.sub("", message)
    if not AllowBotToMention:
        cleaned_message = re.sub(r"<@", "<", cleaned_message)
    cleaned_message = re.sub(r"\n{2,}", "\n", cleaned_message)  # Replace consecutive line breaks with a single line break
    return cleaned_message.strip()

def get_character(character_card):
    # Get current bot character in prompt-friendly format
    # character = f"Your name is {character_card['name']}. You are {character_card['persona']}. {character_card['instructions']}Here is how you speak: \n{', '.join(character_card['examples'])}\n"
    character = f"Your name is {character_card['name']}. You are {character_card['persona']}. {character_card['instructions']}\n"
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

def image_from_string(image_string):
    # Create an image from a base64-encoded string
    img = base64.b64decode(image_string)
    name = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    with open(name, "wb") as f:
        f.write(img)
    return name