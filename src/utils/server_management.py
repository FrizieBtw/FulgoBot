import json
import os
import shutil

from discord import PartialEmoji
import discord

def add_server(server_id: int) -> None:
    """Adds a server to the list of servers.

    Args:
        server_id (int): Server's ID.
    """
    if not os.path.exists('data/servers'):
        print('Creating servers folder...')
        os.makedirs('data/servers')
    servers_list: list = os.listdir('data/servers')
    if str(server_id) not in servers_list:
        server_folder: str = f'data/servers/{server_id}'
        os.makedirs(server_folder)
        shutil.copy('data/templates/server_config.json', f'{server_folder}/config.json')
        with open(f'{server_folder}/temp_voice_channels.txt', 'w', encoding='utf-8') as file:
            file.write('')         

def remove_from_server_list(server_id) -> None:
    """Removes a server from the list of servers.

    Args:
        server_id (int):  Server's ID.
    """
    shutil.rmtree(f'data/servers/{server_id}')
            
def remove_associated_processes(element_id: int, element_type : type, server_id: int) -> None:
    """Removes all associated processes to an element.

    Args:
        element_id (int): Element's ID.
        server_id (int): Server's ID.

    Returns:
        None: Modifie directement le fichier config.json du serveur.
    """
    config_path = f'data/servers/{server_id}/config.json'
    with open(config_path, 'r', encoding='utf-8') as file:
        config = json.load(file)
        
    if element_type is discord.Message:
        
        if str(element_id) in config["role_react"]:
            del config["role_react"][str(element_id)]
            with open(config_path, 'w', encoding='utf-8') as file:
                json.dump(config, file, indent=4)
            
def get_associated_role_for_emoji(server_id : int, message_id : int, emoji : PartialEmoji) -> int:
    """Get the role associated with an emoji.
    
    Args:
        emoji (PartialEmoji): Emoji to check.
        message_id (int): Id of the message associated with the emoji.
        server_id (int): Id of the server.
        
    Returns:
        int: Id of the role associated with the emoji.
    """
    with open(f'data/servers/{server_id}/config.json', 'r', encoding='utf-8') as file:
        config : dict[str, any] = json.load(file)
        if str(message_id) not in config["role_react"].keys():
            return None
    with open(f'data/servers/{server_id}/config.json', 'r', encoding='utf-8') as file:
        config : dict[str, any] = json.load(file)
        role_id : int = config["role_react"][str(message_id)][str(emoji)]
    
    return int(role_id)
