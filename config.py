# API Keys and Configuration
# Your API keys and tokens go here. Do not commit with these in place!
discord_api_key = "INSERT_YOUR_DISCORD_BOT_API_KEY_HERE"
ReactionEmoji = "⏲"
PromptDebug = False; # Set to True to print prompt debug information to the console

# Memory Configuration - It's complicated but assume 3 characters is on average 1 token, make sure to stay within your set context limits.
UserHistoryAmount = 6000

UseChannelHistory = False; # Set to True to enable channel history (Multi-user mode)
ChannelHistoryAmount = 6000

UserMemoryAmount = 3000
UseUserMemory = True; # Set to False to disable user memory

GuildMemoryAmount = 3000
UseGuildMemory = True; # Set to False to disable guild memory

ChannelMemoryAmount = 3000
UseChannelMemory = True; # Set to False to disable channel memory

AllowDirectMessages = False # set to True to allow the bot to respond to direct messages
ReplyToBots = False # set to True to allow the bot to respond to other bots
LogAllMessages = False # set to True to log all messages to a file
IgnoreSymbols = False # set to True to ignore messages which start with common symbols / emojis / URLs

BlockedUsers = [] # add user IDs, or names, to this list to block them from using the bot

SingleChannelMode = False # set to True to only track and reply messages from a single channel
SingleChannelModeID = "" # set to the desired channel ID if singleChannelMode is True
SingleChannelModeName = "" # set to the desired channel name if singleChannelMode is True
SingleChannelModeMentionNotRequired = False # set to True to reply to all messages in the channel without needing to be mentioned

SingleGuildMode = False # set to True to only track and reply messages from a single guild (server)
SingleGuildModeID = "" # set to the desired channel ID if SingleGuildMode is True
SingleGuildModeName = "" # set to the desired channel name if SingleGuildMode is True

# Not yet implemented
#ChannelContextAmount = 4000
#KeepLogFilesPruned = False # set to True to keep log files pruned to a certain size
#LogFileLimit = 100 # set to the maximum number of lines to keep in a log file