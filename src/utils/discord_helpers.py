import json
import discord

class HelpModal(discord.ui.Modal):    
    async def callback(self, interaction):
        pass


async def help_button_callback(self, interaction : discord.Interaction):
    with open(f'data/servers/{interaction.guild_id}/config.json', 'r') as file:
        config = json.load(file)
    with open(f'data/templates/{config["language"]}_lang.json', 'r') as file:
        lang = json.load(file)
        
    help_reason = discord.ui.InputText(
        style=discord.InputTextStyle.long,
        label=lang["help_ticket_label"],
        placeholder=lang["help_ticket_placeholder"],
        required=True
    )
    
    modal = HelpModal(help_reason, title=lang["help_ticket_title"])
    await interaction.response.send_modal(modal)
    await modal.wait()
    
    if help_reason.value is not None:
        help_category_id = config["help_system"]["help_category_id"]
        help_role_id = config["help_system"]["channels_id"][str(interaction.channel_id)]
        
        category = discord.utils.get(interaction.guild.categories, id=int(help_category_id))
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True)
        }
        
        channel = await interaction.guild.create_text_channel(
            name=config["help_system"]['help_channel_name_template'].format_map({"member": interaction.user.name}),
            category=category,
            overwrites=overwrites
        )
        
        await channel.send(f"{discord.utils.get(interaction.guild.roles, id=int(help_role_id)).mention}")
        await channel.send(lang["help_ticket_message"].format_map({"member": interaction.user.mention, "help_reason": help_reason.value}))
        

class HelpButton(discord.ui.Button):
    callback = help_button_callback


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HelpButton(label="🎫", style=discord.ButtonStyle.green, custom_id="help_button"))
