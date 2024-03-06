# API Keys and Configuration
# Your API keys and tokens go here. Do not commit with these in place!
discord_api_key = "INSERT_YOUR_DISCORD_BOT_API_KEY_HERE"
DiscordAccounts = [] # ID/Names of users who can bypass the rate limit and other restrictions
ReactionEmoji = "⏲" # This is the emoji that the bot will react with when it is generating a response, it is removed when the response is sent
PromptDebug = False # True/False: print prompt debug information to the console
MessageDebug = False # True/False: print out how every message is processed
TextAPIConfig = "text-default.json" # set to the name of the text API config file to use located in the configuration folder
CharacterCardFile = "default.json" # set to the name of the text API config file to use located in the configuration folder
AdminCommandTrigger = "¬" # set to the starting character that will trigger admin commands
LogFileName = "log.txt" # set to the name of the log file
LogFileLocation = "logs" # set to the location of the log file

# Context Configuration - It's complicated but assume 3 characters is on average 1 token, make sure to stay within your set context limits.
ContextFolderLocation = "context" # Change only if you want to store user history files in a different location than the default [folder with bot.py]\\context\\users\\{username}.txt
UserHistoryToggle = False # True/False: enable user history - Not recommended to use with ChannelHistoryToggle = True
UserHistoryAmount = 3000 # 0 to disable
UserHistoryToggleifDM = True # True/False: enable user history if the message is a direct message
UserHistoryAmountifDM = 6000 # set to 0 to use the same amount as UserHistoryAmount

ChannelHistoryToggle = False # True/False: enable channel history (Multi-user mode) - Not recommended to use with UserHistoryToggle = True
ChannelHistoryAmount = 3000
ChannelHistoryOverride = "" # Set to the desired channel name to use for ChannelHistory if not using the same channel as the message

# Memory Configuration - This is currently only manually set - it is used to provide extra context / store notable attributes for a user, guild, or channel
GuildMemoryToggle = True # True/False: enable guild memory
GuildMemoryAmount = 3000
ChannelMemoryToggle = True # True/False: enable channel memory
ChannelMemoryAmount = 3000
UserMemoryToggle = True # True/False: enable user memory
UserMemoryAmount = 3000

ResponseMaxLength = 200 # set to the maximum number of tokens the model will generate per response

AllowDirectMessages = True # True/False: True to allow the bot to respond to direct messages
ReplyToBots = False # True/False: True to allow the bot to respond to other bots
MentionOrReplyRequired = True # True/False: False to reply to messages read without needing to be mentioned 
ResolveMentionsToDisplayNames = False # Resolve @s to display_names takes priority over ResolveMentionsToUserNames
ResolveMentionsToUserNames = True # Resolve @s to usernames
AllowBotToMention = False # True/False: True to allow the bot to mention (ping) users in its responses
PullUserHistoryFromID = True # True/False: True to pull user history if mentioned in a message that triggers a response
PullUserMemoryFromID = True # True/False: True to pull user memory if mentioned in a message that triggers a response

LogAllMessagesToUserHistory = True # True/False: to log all messages to a file
LogAllDMsSeparately = True # True/False: to log all DMs to a separate file
LogAllMessagesToChannelHistory = True # True/False: to log all messages to a file
AddTimestamp = False # True/False: add a timestamp to the log file, can cause issues if used for ChannelHistory depending on your model
TimestampSeperateFile = False # True/False: creates a seperate file for timestamped logs
LogNoTextUploads = True # True/False: log messages without text content as <media>

IgnoreSymbols = False # True/False: ignore messages which start with common symbols / emojis / URLs / mentions
RenameOldUserHistory = True # True/False: rename old user history files instead of deleting them
BadResponseSafeGuards = True # True/False: enable safe guards to prevent the bot from sending bad responses, like mimicing users.

BlockedUsers = [] # add user IDs, or names, to this list to block them from using the bot
UserRateLimitSeconds = 10 # set to the number of seconds to wait the same user is allowed to submit a prompt
RateLimitedEmoji = "⏳" # set to the emoji that the bot will react with when a user is rate limited
DenyProfanityInput = False # True/False: deny incoming prompts which don't pass the profanity filter
DenyProfanityOutput = False # True/False: deny outgoing responses which don't pass the profanity filter
ProfanityRating = 0.9 # set the minimum rating for a prompt to pass the profanity filter
ProfanityEmoji = "❌" # set to the emoji that the bot will react with when a prompt is denied for profanity

DuckDuckGoSearch = True # True/False: allow the bot to fetch search results from DuckDuckGo and use them to improve responses
DuckDuckGoMaxSearchResults = 4 # set to the maximum number of search results to fetch from DuckDuckGo
DuckDuckGoMaxSearchResultsWithParams = 8 # set to the maximum number of search results to fetch from DuckDuckGo when using search parameters
AllowWikipediaExtracts = True # True/False: allow the bot to fetch summaries from Wikipedia.org articles
WikipediaExtractLength = 2000 # set to the maximum number of characters to fetch from a Wikipedia.org article
WikipediaSimilarity = 0 # set to the minimum similarity for a webpage to be considered relevant
AllowWebpageScraping = True # True/False: allow the bot to scrape webpages for information
WebpageScrapeLength = 2000 # set to the maximum number of characters to scrape from a webpage
WebpageSimilarity = 0 # set to the minimum similarity for a webpage to be considered relevant

TriggerWordRequiredForSearch = False # True/False: require a synonym of (Who/What/Why/When/Where/Search etc) be in the prompt for a search to be performed
TriggerCharacterRequiredForSearch = "?" # require the message to start, or end, with this trigger character for a search to be performed

SpecificChannelMode = False # True/False: only track and reply messages from a single channel
SpecificChannelModeIDs = [] # set to the desired channel ID if singleChannelMode is True
SpecificChannelModeNames = [] # set to the desired channel name if singleChannelMode is True

SpecificGuildMode = False # True/False: only track and reply messages from a single guild (server)
SpecificGuildModeIDs = [] # set to the desired channel ID if SingleGuildMode is True
SpecificGuildModeNames = [] # set to the desired channel name if SingleGuildMode is True

GenerateImageOnly = True # True/False: if using image genration, set to True to only generate images with no/minimal accompanying text

# Not yet implemented
#KeepLogFilesPruned = False # True/False: keep log files pruned to a certain size
#LogFileLimit = 100 # set to the maximum number of lines to keep in a log file