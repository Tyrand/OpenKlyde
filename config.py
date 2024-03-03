# API Keys and Configuration
# Your API keys and tokens go here. Do not commit with these in place!
discord_api_key = "INSERT_YOUR_DISCORD_BOT_API_KEY_HERE"
DiscordAccountID = "INSERT_YOUR_DISCORD_ACCOUNT_ID_HERE" # To bypass the rate limit for your own bot, insert your account ID here
ReactionEmoji = "⏲" # This is the emoji that the bot will react with when it is generating a response, it is removed when the response is sent
PromptDebug = False # Set to True to print prompt debug information to the console
MessageDebug = False # Set to True to print out how every message is processed

# Context Configuration - It's complicated but assume 3 characters is on average 1 token, make sure to stay within your set context limits.
UseUserHistory = True # Set to True to enable user history
UserHistoryAmount = 6000

UseChannelHistory = False # Set to True to enable channel history (Multi-user mode)
ChannelHistoryAmount = 6000
ChannelHistoryOverride = "" # Set to the desired channel name to use for ChannelHistory if not using the same channel as the message

# Memory Configuration - This is currently only manually set by you - it is used to provide permanent memory to the bot for a user, guild, or channel
UserMemoryAmount = 3000
UseUserMemory = True # Set to False to disable user memory

GuildMemoryAmount = 3000
UseGuildMemory = True # Set to False to disable guild memory

ChannelMemoryAmount = 3000
UseChannelMemory = True # Set to False to disable channel memory

ResponseMaxLength = 800 # set to the maximum number of tokens the model will generateR

AllowDirectMessages = True # set to True to allow the bot to respond to direct message
ReplyToBots = False # set to True to allow the bot to respond to other bots
MentionOrReplyRequired = True # set to True to reply to all messages without needing to be mentioned
AllowBotToMention = False # set to True to allow the bot to mention (ping) users in its responses
UserRateLimitSeconds = 10 # set to the number of seconds to wait the same user is allowed to submit a prompt
RateLimitedEmoji = "⏳" # set to the emoji that the bot will react with when a user is rate limited

LogMessagesToChannelHistory = False # set to True to log all messages to a file
AddTimestamp = False # set to True to add a timestamp to the log file, can cause issues if used for ChannelHistory depending on your model
LogNoTextUploads = False # set to True to log messages without text content as <media>

IgnoreSymbols = False # set to True to ignore messages which start with common symbols / emojis / URLs
RenameOldUserHistory = False # set to True to rename old user history files instead of deleting them
BadResponseSafeGuards = True # set to True to enable safe guards to prevent the bot from sending bad responses, like mimicing users.

BlockedUsers = [] # add user IDs, or names, to this list to block them from using the bot
DenyProfanityInput = True # set to True to deny incoming prompts which don't pass the profanity filter
DenyProfanityOutput = True # set to True to deny outgoing responses which don't pass the profanity filter
ProfanityRating = 1 # set the minimum rating for a prompt to pass the profanity filter
ProfanityEmoji = "🤬" # set to the emoji that the bot will react with when a prompt is denied for profanity

DuckDuckGoSearch = True # set to True to allow the bot to fetch search results from DuckDuckGo and use them to improve responses
DuckDuckGoMaxSearchResults = 4 # set to the maximum number of search results to fetch from DuckDuckGo
DuckDuckGoMaxSearchResultsWithParams = 9 # set to the maximum number of search results to fetch from DuckDuckGo when using search parameters
AllowWikipediaExtracts = True # set to True to allow the bot to fetch summaries from Wikipedia articles
WikipediaExtractLength = 500 # set to the maximum number of characters to fetch from a Wikipedia article
AllowWebpageScraping = True # set to True to allow the bot to scrape webpages for information
WebpageScrapeLength = 500 # set to the maximum number of characters to scrape from a webpage

TriggerWordRequiredForSearch = True # set to True to require a synonym of (Who/What/Why/When/Where/Search) be in the prompt for a search to be performed

SpecificChannelMode = False # set to True to only track and reply messages from a single channel
SpecificChannelModeIDs = [] # set to the desired channel ID if singleChannelMode is True
SpecificChannelModeNames = [] # set to the desired channel name if singleChannelMode is True

SpecificGuildMode = False # set to True to only track and reply messages from a single guild (server)
SpecificGuildModeIDs = [] # set to the desired channel ID if SingleGuildMode is True
SpecificGuildModeNames = [] # set to the desired channel name if SingleGuildMode is True

GenerateImageOnly = True # set to True to only generate images, not text

# Not yet implemented
#KeepLogFilesPruned = False # set to True to keep log files pruned to a certain size
#LogFileLimit = 100 # set to the maximum number of lines to keep in a log file