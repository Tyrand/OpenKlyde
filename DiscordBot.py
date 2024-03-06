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

global BotReady
BotReady = False
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
wikipedia.set_rate_limiting(True)
# Save the original print function
original_print = builtins.print

def custom_print(*args, **kwargs):
    original_print("["+datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]+"] | ", end='')
    original_print(*args, **kwargs)
    
builtins.print = custom_print

async def bot_behavior(message):
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
    if LogAllMessagesToChannelHistory:
        # Log the message to the channel history
        if message.guild:
            await functions.add_to_channel_history(
                message.guild, message.channel, message.author, message.content
            )
            print(f"Added message to '{ContextFolderLocation}\\guilds\\{message.guild.name}\\{message.channel.name}.txt'")
    if LogAllMessagesToUserHistory:
        # Log the message to the channel history
        if message.guild:
            await functions.add_to_user_history(
                message.content, message.author, message.author
            )
            print(f"Added message to '{ContextFolderLocation}\\users\\{message.author.name}.txt")

    # Check if the bot is ready
    if BotReady == False:
        if MessageDebug:
            print("No Response: Bot is not ready")
        return False
    # Check if the author is blocked
    if (message.author.id in BlockedUsers or message.author.name in BlockedUsers):
        if MessageDebug:
            print("No Response: Blocked user")
        return False

    # Don't respond to yourself
    if (message.author == client.user):
        if MessageDebug:
            print("No Response: Self")
        return False
    
    # Don't respond to other bots
    if (message.author.bot and not ReplyToBots):
        if MessageDebug:
            print("No Response: Bot")
        return False
    
    # If the message is empty, don't respond
    if not message.content or message.content == "":
        if MessageDebug:
            print("No Response: Empty message")
        return False

    # If the message starts with a symbol, don't respond - mainly used for MentionOrReplyRequired = False
    if IgnoreSymbols and message.content.startswith((".", ",", "!", "?", ":", "'", "\"", "/", "<", ">", "(", ")", "[", "]", ":", "http")):
        if MessageDebug:
            print("No Response: IgnoreSymbols is True and message starts with a symbol")
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
            await asyncio.sleep(10)
            await message.remove_reaction(RateLimitedEmoji, client.user)
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
    global text_api
    Memory = ""
    History = ""
    DDGSearchResultsString = ""
    WebResults = f"Internal System: the current UTC Unix time is '{int(time.time())}' which in date and time format is '{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'\n"
    WebResults = WebResults + "Internal System: [Results of a quick Internet Search] "
    user_input = functions.clean_user_message(client,message.clean_content)
    # Log the received message
    await functions.write_to_log(LogFileLocation,LogFileName,f"Received message from {UserName}: {user_input}")
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
            History = History + f"[#'{message.channel.name}' begins] " + ChannelHistory + f" [#'{message.channel.name}' ends]"
        if isinstance(message.channel, discord.DMChannel) and UserHistoryAmountifDM:
            UserHistory = str(await functions.get_user_history(user, UserHistoryAmountifDM))
            History = History + UserHistory
        if PullUserHistoryFromID:
            MentionedHistory = str(await get_mentioned_history(message))
            History = History + MentionedHistory
        if UserHistoryToggle and not isinstance(message.channel, discord.DMChannel):
            UserHistory = str(await functions.get_user_history(user, UserHistoryAmount))
            History = History + UserHistory
        if DuckDuckGoSearch:
            max_results = 0
            if not TriggerWordRequiredForSearch or TriggerCharacterRequiredForSearch:
                max_results = DuckDuckGoMaxSearchResults
            elif TriggerWordRequiredForSearch:
                if any(word in message.content.lower() for word in ["search", "google", "bing", "ddg", "duckduckgo", "internet"]):
                    if MessageDebug:
                        print(f"Web Search Trigger Word found")
                    max_results = DuckDuckGoMaxSearchResults
                else:
                    max_results = 0
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
        WebResults = WebResults + "Internal System: [End of Internet Search]\n"
        Memory = "" if Memory is None else Memory
        History = "" if History is None else History
        WebResults = "" if WebResults is None else WebResults
        DDGSearchResultsString = "" if DDGSearchResultsString is None else DDGSearchResultsString
        image_request = functions.check_for_image_request(user_input)
        # If WebResults has at least 1 http link in it, then we have a web result, react with the 🌐 emoji to indicate a websearch was done
        if WebResults and "http" in WebResults:
            await message.add_reaction("🌐")
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
            print("Embed:", embed[:50])
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

# Function to grab all information from any embeds inside the message
async def get_embed(message):
    embed = ""
    if message.embeds:
        for i, e in enumerate(message.embeds, 1):
            if e.fields:
                for field in e.fields:
                    embed += f"[Embed {i} - Field: {field.name}, Value: {field.value}] "
    return str(embed)

# Function to resolve users in the message i.e. <@77921824876269568> -> Algy
# Also include 18 digit user IDs
async def resolve_users(message):
    for user in message.mentions:
        if MessageDebug:
            print(f"Resolving user {user.name} ({user.id})")
        if ResolveMentionsToDisplayNames: # Note: if they have no nickname, this will return their username
            message.content = message.content.replace(f"<@!{user.id}>", user.display_name)
            message.content = message.content.replace(f"<@{user.id}>", user.display_name)
            message.content = message.content.replace(f"<{user.id}>", user.display_name)
            message.content = message.content.replace(f"{user.id}", user.display_name)
        elif ResolveMentionsToUserNames:
            message.content = message.content.replace(f"<@!{user.id}>", user.name)
            message.content = message.content.replace(f"<@{user.id}>", user.name)
            message.content = message.content.replace(f"<{user.id}>", user.name)
            message.content = message.content.replace(f"{user.id}", user.name)
    ids = re.findall(r'(?<!:)\b\d{18}\b', message.content)
    for id in ids:
        if message.guild is None:
            print("Cannot fetch members in a DM")
            continue
        try:
            User = await message.guild.fetch_member(int(id))
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
        if ResolveMentionsToDisplayNames: # Note: if they have no nickname, this will return their username
            message.content = message.content.replace(f"<!@{id}>", User.display_name)
            message.content = message.content.replace(f"<@{id}>", User.display_name)
            message.content = message.content.replace(f"<{id}>", User.display_name)
            message.content = message.content.replace(f"{id}", User.display_name)
        elif ResolveMentionsToUserNames:
            message.content = message.content.replace(f"<!@{id}>", User.name)
            message.content = message.content.replace(f"<@{id}>", User.name)
            message.content = message.content.replace(f"<{id}>", User.name)
            message.content = message.content.replace(f"{id}", User.name)
    return message.content

# Gets any mentioned user and pulls their history
# Also catch 18 digit user IDs
async def get_mentioned_history(message):
    Mentioned_History = []
    for user in message.mentions:
        User_History = await functions.get_user_history(user, UserHistoryAmount)
        Mentioned_History.append(User_History)
    MentionedHistory = ' '.join(Mentioned_History)
    ids = re.findall(r'\b\d{18}\b', message.content)
    for id in ids:
        if message.guild is None:
            print("Cannot fetch members in a DM")
            continue
        try:
            User = await message.guild.fetch_member(int(id))
        except discord.NotFound:
            print(f"No member found with ID {id}")
            continue
        except discord.HTTPException as e:
            print(f"Failed to fetch member with ID {id}: {e}")
            continue
        if User is None:
            print(f"Failed to fetch member with ID {id}")
            continue
        User_History = await functions.get_user_history(User, UserHistoryAmount)
        Mentioned_History.append(User_History)
    MentionedHistory = ' '.join(Mentioned_History)
    return MentionedHistory
async def get_mentioned_memory(message):
    Mentioned_Memory = []
    for user in message.mentions:
        User_Memory = await functions.get_user_memory(user, UserMemoryAmount)
        Mentioned_Memory.append(User_Memory)
    MentionedMemory = ' '.join(Mentioned_Memory)
    ids = re.findall(r'\b\d{18}\b', message.content)
    for id in ids:
        if message.guild is None:
            print("Cannot fetch members in a DM")
            continue
        try:
            User = await message.guild.fetch_member(int(id))
        except discord.NotFound:
            print(f"No member found with ID {id}")
            continue
        except discord.HTTPException as e:
            print(f"Failed to fetch member with ID {id}: {e}")
            continue
        if User is None:
            print(f"Failed to fetch member with ID {id}")
            continue
        User_Memory = await functions.get_user_memory(User, UserMemoryAmount)
        Mentioned_Memory.append(User_Memory)
    return MentionedMemory
        

async def handle_llm_response(content, response):
    try:
        llm_response = response
        data = extract_data_from_response(llm_response)
        llm_message = await functions.clean_llm_reply(
            data, content['user'], character_card["name"]
        )
        queue_item = {"response": llm_message, "content": content}

        if content["image"]:
            queue_to_process_image.put_nowait(queue_item)
        else:
            queue_to_send_message.put_nowait(queue_item)
    except json.JSONDecodeError:
        await functions.write_to_log(LogFileLocation,LogFileName,
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

async def send_api_request(session, url, headers, data):
    async with session.post(url, headers=headers, data=data) as response:
        return await response.json()

async def is_valid_response(content, response_text):
    if MessageDebug:
        print("Checking if response is valid")
    # Define the pattern to search for
    Pattern_BotCardName = r'\n' + re.escape(str(character_card['name'])) + r':$'

    Pattern_UserUsername = r'\n' + re.escape(str(content['user'].name)) + r':$'
    Pattern_BotUsername = r'\n' + re.escape(str(content['bot'].name)) + r':$'

    Pattern_UserDisplayName = r'\n' + re.escape(str(content['user'].display_name)) + r':$'
    Pattern_BotDisplayName = r'\n' + re.escape(str(content['bot'].display_name)) + r':$'

    Pattern_UserID = r'\n@' + re.escape(str(content['user'].id)) + r'$'
    Pattern_BotID = r'\n@' + re.escape(str(content['bot'].id)) + r'$'

    # Check if the response text matches the pattern
    if (
        response_text.strip() is None or response_text.strip() == ""
        or ("[chat log") in response_text.strip().lower()
        or re.match(Pattern_BotCardName, response_text[:16], re.IGNORECASE)
        or re.match(Pattern_UserUsername, response_text[:16], re.IGNORECASE)
        or re.match(Pattern_UserDisplayName, response_text[:16], re.IGNORECASE)
        or re.match(Pattern_BotDisplayName, response_text[:16], re.IGNORECASE)
        or re.match(Pattern_BotUsername, response_text[:16], re.IGNORECASE)
        or re.match(Pattern_UserID, response_text[:16], re.IGNORECASE)
        or re.match(Pattern_BotID, response_text[:16], re.IGNORECASE)
    ):
        return False
    if DenyProfanityOutput and profanity_check.predict([response_text])[0] >= ProfanityRating:
        return False
    if MessageDebug:
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
        await functions.write_to_log(LogFileLocation,LogFileName,
            f"Sending API request to LLM model: {content['prompt']}"
        )
        async with aiohttp.ClientSession() as session:
            retry_count = 0
            while retry_count < 3:
                try:
                    response_data = await send_api_request(
                        session,
                        text_api["address"] + text_api["generation"],
                        text_api["headers"],
                        content["prompt"],
                    )
                    # Log the API response
                    await functions.write_to_log(LogFileLocation,LogFileName,
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

async def send_to_stable_diffusion_queue():
    global image_api
    while True:
        try:
            image_prompt = await queue_to_process_image.get()
            data = image_api["parameters"]
            data["prompt"] += image_prompt["response"]
            data_json = json.dumps(data)
            await functions.write_to_log(LogFileLocation,LogFileName,
                "Sending prompt from "
                + image_prompt["content"]["username"]
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
        except Exception as e:
            await functions.write_to_log(LogFileLocation,LogFileName,f"Error processing image: {str(e)}")
            # Handle the error here
            pass

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
        try:
            if file:
                await original_message.reply(chunk, file=file)
            else:
                await original_message.reply(chunk)
        except discord.errors.HTTPException:
            # Handle the exception here
            pass

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
            reply["content"]["bot"],
            reply["content"]["user"]
        )
        queue_to_send_message.task_done()
        await reply["content"]["message"].remove_reaction(ReactionEmoji, client.user)

@client.event
async def on_ready():
    # Let owner known in the console that the bot is now running!
    print(
        f"Discord Bot is up and running on the bot: "+client.user.name+"#"+client.user.discriminator+" ("+str(client.user.id)+")"
    )
    global BotReady
    BotReady = True
    global text_api
    global image_api
    global character_card
    text_api = await functions.set_api(TextAPIConfig)
    text_api["parameters"]["max_length"] = ResponseMaxLength
    image_api = await functions.set_api("image-default.json")
    api_check = await functions.api_status_check(
        text_api["address"] + text_api["model"], headers=text_api["headers"]
    )
    character_card = await functions.get_character_card(CharacterCardFile)
    # AsynchIO Tasks
    asyncio.create_task(send_to_model_queue())
    asyncio.create_task(send_to_stable_diffusion_queue())
    asyncio.create_task(send_to_user_queue())
    client.tree.add_command(history)
    client.tree.add_command(configuration)
    #client.tree.add_command(personality)
    #client.tree.add_command(character)
    #client.tree.add_command(parameters)
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=str(TextAPIConfig).replace(".json", "")))

    # Sync current slash commands (commented out unless we have new commands)
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

    file_name = functions.get_file_name(ContextFolderLocation+"\\users", str(user.name) + ".txt")

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

try:
    client.run(discord_api_key)
except KeyboardInterrupt:
    interrupt_count += 1
    print("KeyboardInterrupt detected, do it again to exit.")
    if interrupt_count >= 2:
        raise
except BaseException as e:
    client.close()
    asyncio.sleep(1)  # Add a 10 second delay
    client.run(discord_api_key)
    print(f"An error occurred: {e}")
    print("Bot restarted successfully.")