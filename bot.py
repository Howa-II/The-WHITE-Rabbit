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
        messages=[{"role": "user", "content": f"Détecte la langue du texte suivant. Réponds UNIQUEMENT avec le nom exact parmi : {supported}. Si absente, réponds INCONNU.\n\nTexte : {text}"}]
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
        messages=[{"role": "user", "content": f"Traduis ce texte en {target_lang}. Réponds UNIQUEMENT avec la traduction.\n\nTexte : {text}"}]
    )
    return response.content[0].text.strip()


def get_truth(text: str, target_lang: str | None = None) -> str:
    lang_instruction = f"en {target_lang}" if target_lang else "dans la même langue que le message"
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": f"Tu es un bot Discord humoristique. Révèle la vraie signification cachée de ce message (clichés Discord/gaming). Réponds {lang_instruction}, court et drôle, UNIQUEMENT la vérité.\n\nMessage : {text}"}]
    )
    return response.content[0].text.strip()


class TranslateView(discord.ui.View):
    def __init__(self, original_text: str, message_ref: discord.Message, invoker_id: int):
        super().__init__(timeout=120)
        self.original_text = original_text
        self.message_ref = message_ref
        self.invoker_id = invoker_id
        self.selected_values = []

        # Menu déroulant
        options = [discord.SelectOption(label="🔎 Back Thought", value="TRUTH", description="Reveals the hidden truth")]
        for emoji, lang in LANG_EMOJIS.items():
            options.append(discord.SelectOption(label=f"{emoji} {lang.capitalize()}", value=emoji))

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
            await interaction.response.send_message("❌ Ce panneau ne t'appartient pas.", ephemeral=True)
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
            display.append(f"{v} {LANG_EMOJIS[v].capitalize()}")

        await interaction.response.edit_message(
            content=f"## Translater\n**Message :** *{self.original_text[:80]}*\n\n**Selection :** {' + '.join(display)}\n\nConfirme avec ✅",
            view=self
        )

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.success, row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ Ce panneau ne t'appartient pas.", ephemeral=True)
            return

        if not self.selected_values:
            await interaction.response.send_message("⚠️ Select a language or Back Thought first!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        self.stop()

        values = self.selected_values
        has_truth = "TRUTH" in values
        lang_values = [v for v in values if v != "TRUTH"]
        translator = interaction.user.mention

        source_lang = detect_language(self.original_text)
        if source_lang is None:
            await interaction.followup.send(
                f"❌ **Langue non enregistrée.**\n**Supportées :** {', '.join(LANG_EMOJIS.values())}",
                ephemeral=True
            )
            return

        source_emoji = LANG_TO_EMOJI.get(source_lang, "🏳️")

        if not has_truth and len(lang_values) == 1:
            target_lang = LANG_EMOJIS[lang_values[0]]
            if target_lang == source_lang:
                result = f"{source_emoji} *(Already in {source_lang}.)*\n*(par {translator})*"
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

        await interaction.followup.send("✅ Fait !", ephemeral=True)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ Ce panneau ne t'appartient pas.", ephemeral=True)
            return
        await interaction.response.edit_message(content="❌ Annulé.", view=None)
        self.stop()


@bot.tree.context_menu(name="Translater")
async def translate_context_menu(interaction: discord.Interaction, message: discord.Message):
    if not message.content.strip():
        await interaction.response.send_message("❌ Ce message ne contient pas de texte.", ephemeral=True)
        return

    view = TranslateView(
        original_text=message.content,
        message_ref=message,
        invoker_id=interaction.user.id
    )

    await interaction.response.send_message(
        f"## Translater\n**Message :** *{message.content[:80]}{'...' if len(message.content) > 80 else ''}*\n\nChoose a language or Back Thought, then confirm with ✅",
        view=view,
        ephemeral=True
    )


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commande(s) synchronisée(s)")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")
    print(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
        
