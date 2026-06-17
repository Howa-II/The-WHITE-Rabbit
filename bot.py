import discord
from discord.ext import commands
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

LANG_EMOJIS = {
    "🇬🇧": "English",
    "🇫🇷": "French",
    "🇸🇦": "Arabic",
    "🇯🇵": "Japanese",
    "🇮🇹": "Italian",
    "🇩🇪": "German",
    "🇪🇸": "Spanish",
    "🇷🇺": "Russian",
    "🇲🇦": "Maghrebi dialect",
    "🇵🇹": "Portuguese",
    "🇳🇱": "Dutch",
    "🇰🇷": "Korean",
    "🇨🇳": "Chinese",
    "🇷🇴": "Romanian",
    "🇵🇱": "Polish",
    "🇨🇿": "Czech",
    "🇧🇬": "Bulgarian",
    "🇭🇺": "Hungarian",
    "🇭🇷": "Croatian",
    "🇻🇳": "Vietnamese",
    "🇹🇭": "Thai",
}

LANG_TO_EMOJI = {v: k for k, v in LANG_EMOJIS.items()}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def detect_language(text: str) -> str | None:
    supported = ", ".join(LANG_EMOJIS.values())
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20,
        messages=[{"role": "user", "content": f"Detect the language of the following text. Reply ONLY with the exact name from this list: {supported}. If not in the list, reply UNKNOWN.\n\nText: {text}"}]
    )
    result = response.content[0].text.strip().lower()
    for lang in LANG_EMOJIS.values():
        if lang.lower() == result:
            return lang
    return None


def translate_text(text: str, target_lang: str) -> str:
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": f"Translate this text to {target_lang}. Reply ONLY with the translation.\n\nText: {text}"}]
    )
    return response.content[0].text.strip()


def get_truth(text: str, target_lang: str | None = None) -> str:
    lang_instruction = f"in {target_lang}" if target_lang else "in the same language as the original message"
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": f"You are a humorous Discord bot. Reveal the hidden true meaning behind this message based on Discord/gaming clichés. Reply {lang_instruction}, short and funny, ONLY the hidden truth.\n\nMessage: {text}"}]
    )
    return response.content[0].text.strip()


class TranslateView(discord.ui.View):
    def __init__(self, original_text: str, message_ref: discord.Message, invoker_id: int):
        super().__init__(timeout=120)
        self.original_text = original_text
        self.message_ref = message_ref
        self.invoker_id = invoker_id
        self.selected_values = []

        options = [discord.SelectOption(label="🔎 Back Thought", value="TRUTH", description="Reveals the hidden truth")]
        for emoji, lang in LANG_EMOJIS.items():
            options.append(discord.SelectOption(label=f"{emoji} {lang}", value=emoji))

        select = discord.ui.Select(
            placeholder="Choose a language or Back Thought...",
            min_values=1,
            max_values=2,
            options=options[:25],
            row=0
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ This panel is not yours.", ephemeral=True)
            return

        values = interaction.data["values"]
        lang_values = [v for v in values if v != "TRUTH"]

        if len(lang_values) > 1:
            await interaction.response.send_message("❌ Choose only one language at a time.", ephemeral=True)
            return

        self.selected_values = values

        display = []
        if "TRUTH" in values:
            display.append("🔎 Back Thought")
        for v in lang_values:
            display.append(f"{v} {LANG_EMOJIS[v]}")

        await interaction.response.edit_message(
            content=f"## Translater\n**Message:** *{self.original_text[:80]}*\n\n**Selection:** {' + '.join(display)}\n\nConfirm with ✅",
            view=self
        )

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success, row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ This panel is not yours.", ephemeral=True)
            return

        if not self.selected_values:
            await interaction.response.send_message("⚠️ Please select a language or Back Thought first!", ephemeral=True)
            return

        # Désactiver les boutons immédiatement
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(content="⏳ Processing...", view=self)

        values = self.selected_values
        has_truth = "TRUTH" in values
        lang_values = [v for v in values if v != "TRUTH"]
        translator = interaction.user.mention

        source_lang = detect_language(self.original_text)
        if source_lang is None:
            await interaction.edit_original_response(
                content=f"❌ **Language not registered.**\n**Supported:** {', '.join(LANG_EMOJIS.values())}"
            )
            self.stop()
            return

        source_emoji = LANG_TO_EMOJI.get(source_lang, "🏳️")

        try:
            if not has_truth and len(lang_values) == 1:
                target_lang = LANG_EMOJIS[lang_values[0]]
                if target_lang == source_lang:
                    result = f"{source_emoji} *(Already in {source_lang}.)*\n*(by {translator})*"
                else:
                    translated = translate_text(self.original_text, target_lang)
                    result = f"{source_emoji} {translated}\n*(translated by {translator})*"
                await self.message_ref.reply(result)

            elif has_truth and len(lang_values) == 0:
                truth = get_truth(self.original_text)
                result = f"{source_emoji} 🔎 {truth}\n*(revealed by {translator})*"
                await self.message_ref.reply(result)

            elif has_truth and len(lang_values) == 1:
                target_lang = LANG_EMOJIS[lang_values[0]]
                truth = get_truth(self.original_text, target_lang)
                result = f"{source_emoji} 🔎 {truth}\n*(revealed by {translator})*"
                await self.message_ref.reply(result)

            await interaction.edit_original_response(content="✅ Done!")

        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Error: {str(e)}")

        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ This panel is not yours.", ephemeral=True)
            return
        await interaction.response.edit_message(content="❌ Cancelled.", view=None)
        self.stop()


@bot.tree.context_menu(name="Translater")
async def translate_context_menu(interaction: discord.Interaction, message: discord.Message):
    if not message.content.strip():
        await interaction.response.send_message("❌ This message contains no text.", ephemeral=True)
        return

    view = TranslateView(
        original_text=message.content,
        message_ref=message,
        invoker_id=interaction.user.id
    )

    await interaction.response.send_message(
        f"## Translater\n**Message:** *{message.content[:80]}{'...' if len(message.content) > 80 else ''}*\n\nChoose a language or Back Thought, then confirm with ✅",
        view=view,
        ephemeral=True
    )


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} command(s) synced")
    except Exception as e:
        print(f"❌ Sync error: {e}")
    print(f"✅ Bot connected: {bot.user} (ID: {bot.user.id})")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
    
