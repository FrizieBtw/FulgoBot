import io
import json
import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps

async def generate_welcome_card(member : discord.Member, background_image : Image.Image) -> io.BytesIO:
    """Generates a welcome card for a member.

    Args:
        member (discord.Member): The member to generate the welcome card for.
        avatar_image (PIL.Image): The avatar image of the member.
    """
    if not background_image or not member:
        return
    
    avatar_url = member.avatar.with_format('png').with_size(1024)
    avatar_data = await avatar_url.read()
    avatar_image = Image.open(io.BytesIO(avatar_data))
    avatar_image = avatar_image.resize((250, 250), Image.Resampling.BILINEAR)
    
    mask = Image.new('L', avatar_image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([(0, 0), avatar_image.size], fill=255)
    
    avatar_image = ImageOps.fit(avatar_image, mask.size)
    avatar_image.putalpha(mask)

    new_image : Image.Image = Image.new("RGBA", background_image.size)
    new_image.paste(background_image, (0, 0))
    draw = ImageDraw.Draw(new_image)

    border_color : tuple[int, int, int, int] = (255, 255, 255, 200)
    border_width : int = 15
    overlay_rect : tuple[int, int, int, int] = (
        (int((background_image.width - avatar_image.width) / 2) - border_width,
         int((background_image.height - avatar_image.height) / 3) - border_width),
        (int((background_image.width + avatar_image.width) / 2) + border_width,
         int((background_image.height - avatar_image.height) / 3 + avatar_image.height) + border_width)
    )
    draw.pieslice(overlay_rect, 0, 360, fill=border_color)

    new_image.paste(avatar_image, (int((background_image.width - avatar_image.width) / 2), int((background_image.height - avatar_image.height) / 3)), mask)

    font : ImageFont.FreeTypeFont = ImageFont.truetype('data/assets/Geologica-Regular.ttf', 30)
    
    with open(f"data/servers/{member.guild.id}/config.json", "r") as file:
        config = json.load(file)
        text : str = config["welcome_system"]["welcome_message_template"]
    text = text.format_map({"member": member.name, "server": member.guild})

    text_bbox : tuple[float, float, float, float] = draw.textbbox((0, 0), text, font=font)
    text_width : float = text_bbox[2] - text_bbox[0]

    draw.text(
        (int((background_image.width - text_width) / 2), int((background_image.height - avatar_image.height) / 2) + avatar_image.height + 10),
        text,
        font=font,
        fill=(255, 255, 255)
    )
    
    img_byte_arr : io.BytesIO = io.BytesIO()
    new_image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0) 
    
    return img_byte_arr
    