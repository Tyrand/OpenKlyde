BotReady = False
import aiohttp
import asyncio
import config
import datetime
import discord
import duckduckgo_search
import functions
import httpx
from urllib.parse import unquote
import importlib
import json
import os
import logging
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
from profanity_check import predict, predict_prob
import time
import threading
import builtins
from difflib import SequenceMatcher


# Set up Discord client and intents
intents = discord.Intents.all()
client = commands.Bot(command_prefix="$", intents=intents)
intents.message_content = True

# Create queues for message processing
queue_to_process_message = asyncio.Queue()  # Process messages and send to LLM
queue_to_process_image = asyncio.Queue()  # Process images from SD API
queue_to_send_message = asyncio.Queue()  # Send messages to chat and the user

# Character Card (current character personality)
character_card = {}

# Global variables for API information
text_api = {}
image_api = {}
status_last_update = None

# Dictionary to keep track of the last message time for each user
last_message_time = {}

# Enable rate limiting for Wikipedia API
wikipedia.set_rate_limiting(True)

# Save the original print function
original_print = builtins.print

# Set up logging
#logging.basicConfig(level=logging.INFO)

def custom_print(*args, **kwargs):
    original_print("["+datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]+"] | ", end='')
    original_print(*args, **kwargs)
    
builtins.print = custom_print

async def bot_behavior(message):
    """
    This function represents the behavior of the bot when it receives a message.
    It processes the message, checks various conditions, and determines whether or not to respond.
    If the bot decides to respond, it calls the `bot_answer` function.
    
    Args:
        message (discord.Message): The message received by the bot.
    """
    embed = await get_embed(message)
    message.content = message.content + embed
    if ResolveMentionsToUserNames or ResolveMentionsToDisplayNames:
        message.content = await resolve_users(message)
    if MessageDebug:
        print('_________v_CHAT MESSAGE_v_________')
        if message.channel:
            if isinstance(message.channel, discord.DMChannel):
                MessageChannel = "DM"
                MessageGuild = ""
            else:
                MessageChannel = message.channel.name
                MessageGuild = message.guild.name
        print(MessageGuild + " | " + MessageChannel + " | " + message.author.name + ": " + message.content)

    conditions = {
        (message.author.id in BlockedUsers or message.author.name in BlockedUsers): "No Response: Blocked user",
        (message.author == client.user): "No Response: Self",
        (message.author.bot and not ReplyToBots): "No Response: Bot",
        (not message.content or message.content == ""): "No Response: Empty message",
        (BotReady == False): "No Response: Bot is not ready",
        (IgnoreSymbols and message.content.startswith((".", ",", "!", "?", ":", "'", "\"", "/", "<", ">", "(", ")", "[", "]", ":", "http"))): "No Response: IgnoreSymbols is True and message starts with a symbol",
    }
    for condition, condition_message in conditions.items():
        if condition:
            if MessageDebug:
                print(condition_message)
            return False

    # Authorized users can bypass the channel/guild/DM restrictions but must mention the bot to do so
    if (message.author.id in DiscordAccounts or message.author.name in DiscordAccounts) and client.user.mentioned_in(message):
        if MessageDebug:
            print("Will Respond: User is in DiscordAccounts")
        await bot_answer(message)
        return True

    if message.guild is None:
        if AllowDirectMessages:
            await bot_answer(message)
            return True
        else:
            if MessageDebug:
                print("No Response: AllowDirectMessages is False")
            return False

    # Check if the bot is in specific guild mode - if it is, check if the message is from the correct guild
    if SpecificGuildMode and not (message.guild.id in SpecificGuildModeIDs or message.guild.name in SpecificGuildModeNames):
        if MessageDebug:
            print(f"No Response: Guild ({message.guild.id})/({message.guild.name}) no in ({SpecificGuildModeIDs})/({SpecificGuildModeNames})")
        return False

    # Check if the bot is in specific channel mode - if it is, check if the message is from the correct channel
    if SpecificChannelMode and not (message.channel.id in SpecificChannelModeIDs or message.channel.name in SpecificChannelModeNames):
        if MessageDebug:
            print(f"No Response: Channel ({message.channel.id})/({message.channel.name}) not in ({SpecificChannelModeIDs})/({SpecificChannelModeNames})")
        return False

    # Check if mentions are required to trigger the bot    
    if MentionOrReplyRequired and not (client.user.mentioned_in(message) or (message.reference and message.reference.resolved.author == client.user)):
        if MessageDebug:
            print("No Response: MentionOrReplyRequired is True and bot was not mentioned or replied to")
        return False

    # If the message has not yet been returned False, the bot will respond
    if MessageDebug:
        print("Will Respond: Bot will respond")

    await bot_answer(message)
    return True

async def bot_answer(message):
    """
    This function represents the behavior of the bot when it decides to respond to a message.
    It processes the message, generates a response, and sends it back to the user.
    
    Args:
        message (discord.Message): The message to which the bot will respond.
    """
    # Check if the user has sent a message within the last UserRateLimitSeconds seconds
    if message.author.id in last_message_time:
        current_time = time.time()
        last_time = last_message_time[message.author.id]
        if current_time - last_time < UserRateLimitSeconds:
            # Ignore rate limit if user is admin
            if (message.guild and message.author.guild_permissions.administrator) or (message.author.id in DiscordAccounts or message.author.name in DiscordAccounts):
                return True
            await message.add_reaction(RateLimitedEmoji)
            if MessageDebug:
                print(f"No Response: User's last message was {last_time - current_time} seconds ago. UserRateLimitSeconds is {UserRateLimitSeconds}")
            await asyncio.sleep(current_time - last_time)
            await message.remove_reaction(RateLimitedEmoji, client.user)
            return False
    else:
        last_message_time[message.author.id] = time.time()
    if DenyProfanityInput:
        # Deny the prompt if it doesn't pass the profanity filter
        if (profanity_check.predict_prob([message.content])>=ProfanityRating):
            await message.add_reaction(ProfanityEmoji)
            return False
    await message.add_reaction(ReactionEmoji)
    asyncio.create_task(functions.RateLimitNotice(message,client))
    user = message.author
    userID = message.author.id
    UserName = message.author.name
    global text_api
    Memory = ""
    History = ""
    DDGSearchResultsString = ""
    WebResults = ""
    #WebResults = f"\nTyrandBot: current UTC Unix time is '{int(time.time())}' which in date and time format is '{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'\n"
    WebResults = WebResults + "\nTyrandBot: [Results of a quick Internet Search]"
    # Clean the user's message to make it easy to read
    user_input = functions.clean_user_message(client,message.content)
    # Log the received message
    functions.write_to_log(LogFileLocation,LogFileName,f"Received message from {UserName}: {user_input}")
    # Is this an image request?
    image_request = functions.check_for_image_request(user_input)
    character = functions.get_character(character_card)
    if image_request and (message.author.id in DiscordAccounts or message.author.name in DiscordAccounts):
        prompt = await functions.create_image_prompt(user_input, character, text_api)
    else:
        reply = await get_reply(message)
        if GuildMemoryToggle and message.guild:
            GuildMemory = str(await functions.get_guild_memory(message.guild, GuildMemoryAmount))
            Memory =  Memory + GuildMemory
        if ChannelMemoryToggle and message.guild:
            if ChannelHistoryOverride: ChannelName = ChannelHistoryOverride
            else: ChannelName = message.channel.name
            ChannelMemory = str(await functions.get_channel_memory(message.guild.name, ChannelName, ChannelMemoryAmount))
            Memory = Memory + ChannelMemory
        if PullUserMemoryFromID:
            MentionedMemory = str(await get_mentioned_memory(message))
            Memory = Memory + MentionedMemory
        if UserMemoryToggle:
            UserMemory = str(await functions.get_user_memory(user, UserMemoryAmount))
            Memory = Memory + UserMemory
        if ChannelHistoryToggle and message.guild:
            if ChannelHistoryOverride:
                ChannelName = ChannelHistoryOverride
            else:
                ChannelName = message.channel.name
            ChannelHistory = str(await functions.get_channel_history(message.guild.name, ChannelName, ChannelHistoryAmount))
            History = History + ChannelHistory
        if isinstance(message.channel, discord.DMChannel) and UserHistoryAmountifDM:
            UserHistory = str(await functions.get_user_history(user, UserHistoryAmountifDM))
            History = History + UserHistory
        if PullUserHistoryFromID:
            MentionedHistory = str(await get_mentioned_history(message))
            History = History + MentionedHistory
        if UserHistoryToggleifDM and not isinstance(message.channel, discord.DMChannel):
            UserHistory = str(await functions.get_user_history(user, UserHistoryAmount))
            History = History + UserHistory
        if DuckDuckGoSearch:
            max_results = 0
            if not TriggerWordRequiredForSearch and not TriggerCharacterRequiredForSearch:
                max_results = DuckDuckGoMaxSearchResults
            elif TriggerWordRequiredForSearch:
                if any(word in message.content.lower() for word in ["search", "google", "bing", "ddg", "duckduckgo", "internet"]):
                    if MessageDebug:
                        print(f"Web Search Trigger Word found")
                    max_results = DuckDuckGoMaxSearchResults
            elif TriggerCharacterRequiredForSearch:
                # Check if the message starts or ends with a trigger character
                if message.content.startswith(TriggerCharacterRequiredForSearch) or message.content.endswith(TriggerCharacterRequiredForSearch):
                    if MessageDebug:
                        print(f"Search Trigger {TriggerCharacterRequiredForSearch} found at start or end of message")
                    max_results = DuckDuckGoMaxSearchResults
            else:
                max_results = 0
            if DuckDuckGoMaxSearchResultsWithParams and ("inurl:" in message.content or "intitle:" in message.content):
                if MessageDebug:
                    print(f"inurl: or intitle: found")
                max_results = DuckDuckGoMaxSearchResultsWithParams
            if message.content.startswith("!"):
                    max_results = 0
            if max_results > 0:
                DDQSearchQuery = "inurl:wiki inurl:news inurl:guide" + message.content.split('\n')[0] + " " + reply[:50] + " " + datetime.datetime.now().strftime('%Y/%m/%d')
                try:
                    DDGSearchResults = DDGS().text(DDQSearchQuery, 
                                max_results=max_results, safesearch='off', region='us-en', backend='api')
                    DDGSearchResultsList = [
                        f"[{result['href']} | {result['body']}]"
                        for i, result in enumerate(DDGSearchResults)
                    ]
                    DDGSearchResultsString = ' '.join(DDGSearchResultsList)
                    WebResults = WebResults + DDGSearchResultsString
                    if MessageDebug:
                        print(f"DuckDuckGo Search Results:\n{DDGSearchResultsString}")
                except DuckDuckGoSearchException as e:
                    print(f"An error occurred while searching: {e}")
                    pass
        if AllowWebpageScraping:
            WebLinks = [link.rstrip('>') for link in re.findall(r'(https?://\S+)', message.content + " " + DDGSearchResultsString)]
            WebScrapeHeaders = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:123.0) Gecko/20100101 Firefox/123.0'
            }
            for WebLink in WebLinks:
                WebLinkDecoded = unquote(WebLink)
                if "wikipedia.org" not in WebLinkDecoded:
                    try:
                        RelevantSentences = []
                        response = requests.get(WebLinkDecoded, headers=WebScrapeHeaders)
                        soup = BeautifulSoup(response.text, 'html.parser')
                        # Find all <p> tags
                        paragraphs = soup.find_all('p')
                        # Filter paragraphs based on conditions
                        paragraphs = [p for p in paragraphs if len(p.get_text().strip()) > 10 and 'cookie' not in p.get_text().lower()]
                        # Calculate similarity for each sentence
                        similarity_scores = []
                        for p in paragraphs:
                            p_text = p.get_text().strip()
                            sentences = p_text.split('. ')
                            for sentence in sentences:
                                similarity = SequenceMatcher(None, sentence, message.content).ratio()
                                if similarity > WebpageSimilarity or any(year in sentence for year in ["2022", "2023", "2024", "2025"]):
                                    if MessageDebug:
                                        print(f"Similarity: {round(similarity, 2)} | {sentence}")
                                    similarity_scores.append((sentence, similarity))
                        # Sort sentences based on similarity scores
                        similarity_scores.sort(key=lambda x: x[1], reverse=True)
                        # Include sentences in RelevantSentences until WebpageScrapeLength is reached
                        for sentence, similarity in similarity_scores:
                            if sum(len(s) for s in RelevantSentences) >= WebpageScrapeLength:
                                RelevantSentences.append(sentence)
                                break
                        WebResults = WebResults + f"[Webpage: {WebLinkDecoded} | {RelevantSentences}]"
                        if MessageDebug:
                            print(f"Webpage scraped: {WebLinkDecoded} | {str(RelevantSentences)}")
                    except (requests.exceptions.RequestException, Exception) as e:
                        print(f"An error occurred while scraping webpage: {e}")
            pass
        if AllowWikipediaExtracts:
            Links = re.findall(r'wikipedia.org/wiki/([^\s>]+)', message.content + " " + DDGSearchResultsString)
            if Links:
                RelevantSentencesTrimmed = ""
                for Link in Links:
                    LinkDecoded = unquote(Link)
                    try:
                        LinkPage = wikipedia.page(Link)
                        LinkPageSentences = LinkPage.content.split('. ')
                        LinkPageSentencesArray = [sentence.strip() for sentence in LinkPageSentences]
                        RelevantSentences = []
                        for sentence in LinkPageSentencesArray:
                            similarity = SequenceMatcher(None, sentence, message.content).ratio()
                            if similarity >= WikipediaSimilarity or any(year in sentence for year in ["2022", "2023", "2024", "2025"]):  # Adjust the threshold and years as needed
                                if MessageDebug:
                                    print(f"Similarity: {round(similarity, 2)} | {sentence}")
                            RelevantSentences.append(sentence)
                        RelevantSentences.sort(key=lambda x: SequenceMatcher(None, x, message.content).ratio(), reverse=True)
                        RelevantSentencesTrimmed = ' '.join(RelevantSentences)[:WikipediaExtractLength]
                        if MessageDebug:
                            print(f"[Wikipedia article scraped: {LinkDecoded} | {str(RelevantSentencesTrimmed)}]")
                        WebResults = WebResults + f"[Wikipedia: {LinkDecoded} | {str(RelevantSentencesTrimmed)}]"
                    except Exception as e:
                        print(f"An error occurred while extracting from Wikipedia: {e}")
            pass
        WebResults = WebResults + "\nTyrandBot: [End of Internet Search]\n"
        Memory = "" if Memory is None else Memory
        History = "" if History is None else History
        WebResults = "" if WebResults is None else WebResults
        DDGSearchResultsString = "" if DDGSearchResultsString is None else DDGSearchResultsString
        image_request = functions.check_for_image_request(user_input)
        # If WebResults has at least 1 http link in it, then we have a web result, react with the 🌐 emoji to indicate a websearch was done
        if WebResults and "http" in WebResults:
            await message.add_reaction(WebSearchEmoji)
        if GenerateImageOnly and image_request:
            character = ""
            character_card["name"] = ""
            character_card["persona"] = ""
            character_card["instructions"] = ""
            WebResults = ""
            Memory = ""
            History = ""
            reply = ""
        prompt = await functions.create_text_prompt(
            f"\n{user_input}",
            user,
            character,
            character_card["name"],
            WebResults,
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
            print("Web Results:", WebResults[:50])
            print("User Memory:", Memory[:50])
            print("User History:", History[:50])
            print("Reply:", reply)
            print("Text API:", text_api)
    queue_item = {
        "prompt": prompt,
        "message": message,
        "user_input": user_input,
        "user": user,
        "bot": client.user,
        "image": image_request,
    }
    if LogAllMessagesToChannelHistory:
        # Log the message to the channel's context file
        if message.guild:
            await functions.add_to_channel_history(
                message.guild, message.channel, message.author, message.content
            )
            print(f"Added message to '{ContextFolderLocation}\\guilds\\{message.guild.name}\\{message.channel.name}.txt'")
    if LogAllMessagesToUserHistory:
    # Log the message to the user's context file
        await functions.add_to_user_history(
            message.content, message.author, message.author
        )
        print(f"Added message to '{ContextFolderLocation}\\users\\{message.author.name}.txt")
    queue_to_process_message.put_nowait(queue_item)

# If the message is a part of a reply chain, get any messages that are being replied to up to a maximum of 4
async def get_reply(message):
    reply = ""
    counter = 0
    max_messages = 4  # Maximum number of messages to fetch for context

    # If the message reference is not none, meaning someone is replying to a message
    while message.reference is not None and counter < max_messages:
        # Grab the message that's being replied to
        referenced_message = await message.channel.fetch_message(
            message.reference.message_id
        )

        # Add the referenced message to the reply
        reply += (
            referenced_message.author.name
            + ": "
            + referenced_message.clean_content
            + "\n"
        )

        # Set the current message to the referenced message for the next iteration
        message = referenced_message
        counter += 1

    reply = functions.clean_user_message(client, reply)
    return reply

async def get_embed(message):
    if message.embeds:
        embeds = [
            f"[Embed {i} - Field: {field.name}, Value: {field.value}]"
            for i, e in enumerate(message.embeds, 1)
            for field in e.fields
        ]
        return ' '.join(embeds)
    return ""

async def replace_mentions_with_name(MessageContent, user, name):
    MessageContent = MessageContent.replace(f"<@!{user.id}>", name)
    MessageContent = MessageContent.replace(f"<@{user.id}>", name)
    MessageContent = MessageContent.replace(f"<{user.id}>", name)
    MessageContent = MessageContent.replace(f"{user.id}", name)
    return MessageContent

async def resolve_users(FullMessage):
    for user in FullMessage.mentions:
        if MessageDebug:
            print(f"Resolving user {user.name} ({user.id})")
        if ResolveMentionsToDisplayNames:
            FullMessage.content = await replace_mentions_with_name(FullMessage.content, user, user.display_name)
        elif ResolveMentionsToUserNames:
            FullMessage.content = await replace_mentions_with_name(FullMessage.content, user, user.name)

    ids = re.findall(r'(?<!:)\b\d{18}\b', FullMessage.content)
    for id in ids:
        if FullMessage.guild is None:
            print("Cannot fetch members in a DM")
            continue
        try:
            User = await FullMessage.guild.fetch_member(int(id))
        except discord.NotFound:
            print(f"No member found with ID {id}")
            continue
        except discord.HTTPException as e:
            print(f"Failed to fetch member with ID {id}: {e}")
            continue
        if User is None:
            print(f"Failed to fetch member with ID {id}")
            continue
        if MessageDebug:
            print(f"Resolving user {User.name} ({User.id})")
        if ResolveMentionsToDisplayNames:
            FullMessage.content = await replace_mentions_with_name(FullMessage.content, User, User.display_name)
        elif ResolveMentionsToUserNames:
            FullMessage.content = await replace_mentions_with_name(FullMessage.content, User, User.name)

    return FullMessage.content

async def get_mentioned_data(message, data_fetcher, data_amount):
    mentioned_data = []
    for user in message.mentions:
        user_data = await data_fetcher(user, data_amount)
        mentioned_data.append(user_data)
    ids = re.findall(r'\b\d{18}\b', message.content)
    for id in ids:
        if message.guild is None:
            logging.warning("Cannot fetch members in a DM")
            continue
        try:
            user = await message.guild.fetch_member(int(id))
        except discord.NotFound:
            logging.warning(f"No member found with ID {id}")
            continue
        except discord.HTTPException as e:
            logging.error(f"Failed to fetch member with ID {id}: {e}")
            continue
        if user is None:
            logging.error(f"Failed to fetch member with ID {id}")
            continue
        user_data = await data_fetcher(user, data_amount)
        mentioned_data.append(user_data)
    return ' '.join(mentioned_data)

async def get_mentioned_history(message):
    return await get_mentioned_data(message, functions.get_user_history, UserHistoryAmount)

async def get_mentioned_memory(message):
    return await get_mentioned_data(message, functions.get_user_memory, UserMemoryAmount)
        

async def handle_llm_response(content, response):
    try:
        if ResponseDebug:
            logging.debug("Received response from LLM model. Length: %s", len(response))
        llm_response = response
        extracted_data = extract_data_from_response(llm_response)
        llm_message = await functions.clean_llm_reply(
            extracted_data, content['user'], client.user
        )
        queue_item = {"response": llm_message, "content": content}

        if content["image"]:
            queue_to_process_image.put_nowait(queue_item)
        else:
            queue_to_send_message.put_nowait(queue_item)
    except json.JSONDecodeError:
        functions.write_to_log(LogFileLocation,LogFileName,
            "Invalid JSON response from LLM model: " + str(response)
        )
    except Exception as e:
        functions.write_to_log(LogFileLocation,LogFileName,
            "Unexpected error: " + str(e)
        )

def extract_data_from_response(llm_response):
    """
    Extracts text data from the API response.

    Parameters:
    llm_response: The API response.

    Returns:
    The extracted text data, or an empty string if data extraction fails.
    """
    try:
        return llm_response["results"][0]["text"]
    except (KeyError, IndexError):
        try:
            return llm_response["choices"][0]["text"]
        except (KeyError, IndexError):
            return ""  # Return an empty string if data extraction fails

async def send_api_request(session, url, headers, data):
    """
    Sends an API request and returns the response.

    Parameters:
    session: The aiohttp client session.
    url: The URL to send the request to.
    headers: The headers to include in the request.
    data: The data to include in the request.

    Returns:
    The response from the API, parsed as JSON.
    """
    async with session.post(url, headers=headers, data=data) as response:
        try:
            return await response.json()
        except Exception as e:
            print(f"An error occurred while parsing the response: {e}")
            return None

RESPONSE_TEXT_LENGTH = 16

async def is_valid_response(content, response_text):
    if ResponseDebug:
        print("Checking if response is valid")

    patterns = [
        r'\n' + re.escape(str(character_card['name'])) + r':$',
        r'\n' + re.escape(str(content['user'].name)) + r':$',
        r'\n' + re.escape(str(content['bot'].name)) + r':$',
        r'\n' + re.escape(str(content['user'].display_name)) + r':$',
        r'\n' + re.escape(str(content['bot'].display_name)) + r':$',
        r'\n@' + re.escape(str(content['user'].id)) + r'$',
        r'\n@' + re.escape(str(content['bot'].id)) + r'$',
    ]

    stripped_response = response_text.strip()

    if (
        not stripped_response
        or "[chat log" in stripped_response.lower()
        or any(re.match(pattern, stripped_response[:RESPONSE_TEXT_LENGTH], re.IGNORECASE) for pattern in patterns)
    ):
        return False

    if DenyProfanityOutput and profanity_check.predict([response_text])[0] >= ProfanityRating:
        return False

    if ResponseDebug:
        print("Response is valid")

    return True

# Function to send the prompt to the LLM model and return the response_data
async def send_to_model(content):
    global text_api
    async with aiohttp.ClientSession() as session:
        response_data = await send_api_request(
            session,
            text_api["address"] + text_api["generation"],
            text_api["headers"],
            content["prompt"],
        )
        return response_data

# Function to send the prompt to the LLM model and handle the response as a reply to a message
async def send_to_model_queue():
    global text_api
    while True:
        # Get the queue item that's next in the list
        content = await queue_to_process_message.get()
        # Add the message to the user's history - But check if LogAllMessagesToUserHistory is enabled first so we don't save it twice.
        if not LogAllMessagesToUserHistory:
            await functions.add_to_user_history(
                content["user_input"],
                content["user"],
                content["user"]
            )
        # Log the API request
        functions.write_to_log(LogFileLocation,LogFileName,
            f"Sending API request to LLM model: {content['prompt']}"
        )
        
        if ResponseDebug:
            print("Sending API request to LLM model")
        async with aiohttp.ClientSession() as session:
            retry_count = 0
            while retry_count < 3:
                try:
                    # Create the prompts folder if it doesn't exist
                    if not os.path.exists("prompts"):
                        os.makedirs("prompts")

                    # Generate the file path
                    file_path = f"prompts/{content['user'].name}.json"

                    # Store the data in JSON format
                    with open(file_path, "w") as file:
                        json.dump(content["prompt"], file)

                    # Send the API request
                    response_data = await send_api_request(
                        session,
                        text_api["address"] + text_api["generation"],
                        text_api["headers"],
                        content["prompt"],
                    )
                    # Log the API response
                    functions.write_to_log(LogFileLocation,LogFileName,
                        f"Received API response from LLM model: {response_data}"
                    )
                    response_text = response_data["results"][0]["text"]
                    # If the response is short and ends with a colon, it's probably triggered it's stop_sequence instantly
                    if len(response_text) < 20 and (response_text[-1] == ":" or response_text[-2] == ":"):
                        retry_count += 0.1 # Only increase the retry count by 0.1 because hasn't been a full attempt and costs very little to keep trying
                        continue
                    elif await is_valid_response(content, response_text):
                        await handle_llm_response(content, response_data)
                        queue_to_process_message.task_done()
                        break
                    # If the response fails the if statement, the bot will generate a new response, repeat until it's caught in the if statement
                    await asyncio.sleep(
                        1
                    )  # Add a delay to avoid excessive API requests (in seconds)
                except Exception as e:
                    print(f"Error occurred: {e}")
                    retry_count += 1
            if retry_count >= 3:
                response_text = 'Failed to generate a response correctly after multiple attempts. Please try again or use a different prompt.'
                await content["message"].remove_reaction(ReactionEmoji, client.user)
                print('text: ' + response_text)
                await content['message'].reply(response_text)
                queue_to_process_message.task_done()

async def send_to_stable_diffusion_queue(image_api):
    while True:
        try:
            image_prompt = await queue_to_process_image.get()
            data = image_api["parameters"]
            data["prompt"] += image_prompt["response"]
            data_json = json.dumps(data)
            functions.write_to_log(LogFileLocation,LogFileName,
                f"Sending prompt from {image_prompt['content']['username']} to Stable Diffusion model."
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
        except Exception as e:
            functions.write_to_log(LogFileLocation, LogFileName, f"Error processing image: {str(e)}")
            # Handle the error here
            pass

async def send_large_message(original_message, reply_content, file=None):
    """
    Sends a large message by splitting it into chunks if it exceeds Discord's character limit.

    Parameters:
    original_message: The original message to reply to.
    reply_content: The content of the reply.
    file: An optional file to attach to the message.
    """
    if ResolveMentionsToUserNames:
        ids = re.compile(r'\b\d{18}\b').findall(reply_content)
        for id in ids:
            if original_message.guild is None:
                user = await client.fetch_user(id)
            else:
                user = original_message.guild.get_member(int(id))
            if user is not None:
                logging.info(f"Resolved {id} to {user.name}")
                for pattern in [f"<!@{id}>", f"<@{id}>", f"<{id}>", f"{id}"]:
                    reply_content = reply_content.replace(pattern, user.name)
                logging.info(f"Replaced '{pattern}' with '{user.name}': {reply_content}")
    chunks = []
    MAX_CHARS = 2000
    while len(reply_content) > MAX_CHARS:
        last_newline_index = reply_content.rfind("\n", 0, MAX_CHARS)
        if last_newline_index == -1:
            last_newline_index = MAX_CHARS
        chunk = reply_content[:last_newline_index]
        chunks.append(chunk)
        reply_content = reply_content[last_newline_index:].lstrip()
    chunks.append(reply_content)
    for chunk in chunks:
        try:
            if file:
                await original_message.reply(chunk, file=file)
            else:
                await original_message.reply(chunk)
        except discord.errors.HTTPException as e:
            print(f"An error occurred while sending the message: {e}")

async def send_to_user_queue():
    """
    Continuously processes the queue of messages to be sent to the user.

    For each message in the queue, if the message contains an image, it sends the image and then removes the image file.
    After sending the message, it removes the bot's reaction from the message and adds the message to the user's history.
    """
    while True:
        reply = await queue_to_send_message.get()
        if reply["content"]["image"]:
            image_file = discord.File(reply["image"])
            await send_large_message(
                reply["content"]["message"], reply["response"], image_file
            )
            try:
                os.remove(reply["image"])
            except Exception as e:
                print(f"An error occurred while removing the image file: {e}")
        else:
            await send_large_message(reply["content"]["message"], reply["response"])
        # Update reactions after message has been sent
        await reply["content"]["message"].remove_reaction(ReactionEmoji, client.user)
        # Add the message to user's history
        await functions.add_to_user_history(
            reply["response"],
            reply["content"]["bot"],
            reply["content"]["user"]
        )
        queue_to_send_message.task_done()

# Global Variables
BotReady = False
text_api = None
image_api = None
character_card = None

@client.event
async def on_ready():
    global BotReady, text_api, image_api, character_card
    BotReady = True
    text_api = await functions.set_api(TextAPIConfig)
    text_api["parameters"]["max_length"] = ResponseMaxLength
    image_api = await functions.set_api("image-default.json")
    api_check = await functions.api_status_check(
        text_api["address"] + text_api["model"], headers=text_api["headers"]
    )
    character_card = await functions.get_character_card(CharacterCardFile)
    tasks = [
        asyncio.create_task(send_to_model_queue()),
        asyncio.create_task(send_to_stable_diffusion_queue(text_api)),
        asyncio.create_task(send_to_user_queue()),
    ]
    client.tree.add_command(history)
    client.tree.add_command(configuration)
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=str(TextAPIConfig).replace(".json", "")))
    await client.tree.sync()

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
    name="history", description="View or change the bot's history."
)

@history.command(
    name="reset", description="Reset your conversation history with the bot."
)
async def reset_history(interaction):
    user = interaction.user
    UserName = str(interaction.user.name)
    UserName = UserName.replace(" ", "")

    file_name = functions.get_file_name(str(ContextFolderLocation)+"\\users", f"{str(user.name)}")

    # Attempt to remove or rename the file based on the condition
    try:
        if RenameOldUserHistory:
            new_file_name = f"{file_name}_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
            os.rename(str(file_name)+'.txt', str(new_file_name))
            await interaction.response.send_message(
                "Your conversation history was reset."
            )
            print("Conversation history file '{}' renamed to '{}'.".format(file_name, new_file_name))
        else:
            os.remove(str(file_name)+".txt")
            await interaction.response.send_message(
                "Your conversation history was reset."
            )
            print("Conversation history file '{}' deleted.".format(file_name)+".txt")
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

    file_name = functions.get_file_name(ContextFolderLocation+"\\users", str(user.name) + ".txt")

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
configuration = app_commands.Group(
    name="configuration",
    description="View or change the bot's current configuration.",
)

# Command to view a list of available characters.
@configuration.command(
    name="view", description="View the bot's current configuration."
)
async def view_configuration(interaction):
    # List the current configuration settings
    # Settings listed are: ResponseMaxLength, GuildMemoryAmount, ChannelMemoryAmount, UserMemoryAmount, ChannelHistoryAmount,
    # UserHistoryAmount, AllowDirectMessages, UserRateLimitSeconds, ReplyToBots, MentionOrReplyRequired,
    # SpecificGuildMode, SpecificGuildModeIDs, SpecificGuildModeNames, SpecificChannelMode, SpecificChannelModeIDs, SpecificChannelModeNames
    await interaction.response.send_message(
        "The bot's current configuration is as follows:\n" + 
        "Response Max Length: " + str(ResponseMaxLength) + " tokens (approx "+str(ResponseMaxLength*3)+" ~ "+str(ResponseMaxLength*4)+" characters)"  + "\n" +
        "Channel History (characters): " + str(ChannelHistoryAmount) + "\n" +
        "User History (characters): " + str(UserHistoryAmount) + "\n" +
        "Guild Memory (characters): " + str(GuildMemoryAmount) + "\n" +
        "Channel Memory (characters): " + str(ChannelMemoryAmount) + "\n" +
        "User Memory (characters): " + str(UserMemoryAmount) + "\n" +
        "Allow Direct Messages: " + str(AllowDirectMessages) + "\n" +
        "UserRateLimitSeconds: " + str(UserRateLimitSeconds) + "\n" +
        "Reply to Bots: " + str(ReplyToBots) + "\n" +
        "Mention or Reply Required: " + str(MentionOrReplyRequired) + "\n" +
        "Wikipedia Scraping: " + str(AllowWikipediaExtracts) + "\n" +
        "General Internet Scraping: " + str(AllowWebpageScraping) + "\n" +
        "Specific Guilds: " + str(SpecificGuildMode) + " | " +
        str(SpecificGuildModeIDs) + " " + str(SpecificGuildModeNames) + "\n" +
        "Specific Channels: " + str(SpecificChannelMode) + " | " +
        str(SpecificChannelModeIDs) + " " + str(SpecificChannelModeNames) + "\n"
    )

# Command to view a list of available characters.
@configuration.command(
    name="reload", description="reload the bot's config file."
)
async def view_configuration(interaction):
    #Command only available to users in the DiscordAccounts list
    if interaction.user.id not in DiscordAccounts:
        await interaction.response.send_message(
            "You do not have permission to reload the bot's configuration."
        )
        return
    # Reload the config.py module to get updated values
    importlib.reload(config)
    # Let the user know that their request has been completed
    await interaction.response.send_message(
        "The bot's configuration has been reloaded."
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

@client.event
async def on_message(message):
    global last_message
    last_message = message

    # Bot will now either do or not do something!
    await bot_behavior(message)

interrupt_count = 0
restart_attempts = 0
max_restart_attempts = 5

try:
    client.run(discord_api_key)
except KeyboardInterrupt:
    interrupt_count += 1
    print("KeyboardInterrupt detected, do it again to exit.")
    if interrupt_count >= 2:
        raise
except Exception as e:  # Catch general exceptions
    client.close()
    asyncio.sleep(10)  # Add a 10 second delay
    print(f"An error occurred: {e}")
    restart_attempts += 1
    if restart_attempts <= max_restart_attempts:
        print("Bot restarted successfully.")
        asyncio.create_task(client.start(discord_api_key))
    else:
        print("Max restart attempts reached. Exiting.")
