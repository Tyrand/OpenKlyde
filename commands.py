
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
    # UserHistoryAmount, AllowDirectMessages, UserRateLimitSeconds, ReplyToBots, MentionOrReplyRequired, AllowWikipediaExtracts,
    # SpecificGuildMode, SpecificGuildModeIDs, SpecificGuildModeNames, SpecificChannelMode, SpecificChannelModeIDs, SpecificChannelModeNames
    await interaction.response.send_message(
        "The bot's current configuration is as follows:\n" +
        "Response Max Length: " + str(ResponseMaxLength) + "(approx"+str(ResponseMaxLength*3)+"~"+str(ResponseMaxLength*4)+"characters)"  + "\n" +
        "Guild Memory (characters): " + str(GuildMemoryAmount) + "\n" +
        "Channel Memory (characters): " + str(ChannelMemoryAmount) + "\n" +
        "User Memory (characters): " + str(UserMemoryAmount) + "\n" +
        "Channel History (characters): " + str(ChannelHistoryAmount) + "\n" +
        "User History (characters): " + str(UserHistoryAmount) + "\n" +
        "Allow Direct Messages: " + str(AllowDirectMessages) + "\n" +
        "UserRateLimitSeconds: " + str(UserRateLimitSeconds) + "\n" +
        "Reply to Bots: " + str(ReplyToBots) + "\n" +
        "Mention or Reply Required:" + str(MentionOrReplyRequired) + "\n" +
        "Wikipedia Link Extracting?: " + str(AllowWikipediaExtracts) + "\n" +
        "Specific Guilds?: " + str(SpecificGuildMode) + " | " +
        str(SpecificGuildModeIDs) + str(SpecificGuildModeNames) + "\n" +
        "Specific Channels?: " + str(SpecificChannelMode) + " | " +
        str(SpecificChannelModeIDs) + str(SpecificChannelModeNames)
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
