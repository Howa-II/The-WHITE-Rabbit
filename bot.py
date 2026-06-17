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
    "🇬🇧": "anglais",
    "🇫🇷": "français",
    "🇸🇦": "arabe",
    "🇯🇵": "japonais",
    "🇮🇹": "italien",
    "🇩🇪": "allemand",
    "🇪🇸": "espagnol",
    "🇷🇺": "russe",
    "🇲🇦": "dialecte maghrébin",
    "🇵🇹": "portugais",
    "🇳🇱": "néerlandais",
    "🇰🇷": "coréen",
    "🇨🇳": "chinois",
    "🇷🇴": "roumain",
    "🇵🇱": "polonais",
    "🇨🇿": "tchèque",
    "🇧🇬": "bulgare",
    "🇭🇺": "hongrois",
    "🇭🇷": "croate",
    "🇻🇳": "vietnamien",
    "🇹🇭": "thaïlandais",
}

LANG_TO_EMOJI = {v: k for k, v in LANG_EMOJIS.items()}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_sessions: dict[int, dict] = {}


def detect_language(text: str) -> str | None:
    supported = ", ".join(LANG_EMOJIS.values())
    prompt = (
        f"Détecte la langue du texte suivant. "
        f"Réponds UNIQUEMENT avec le nom exact de la langue parmi cette liste : {supported}. "
        f"Si la langue n'est PAS dans cette liste, réponds uniquement avec le mot : INCONNU.\n\n"
        f"Texte : {text}"
    )
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}]
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
    lang_instruction = f"en {target_lang}" if target_lang else "dans la même langue que le message original"
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": f"Tu es un bot Discord humoristique. Révèle la vraie signification cachée de ce message en te basant sur les clichés Discord/gaming. Réponds {lang_instruction}, court et drôle, UNIQUEMENT la vérité cachée.\n\nMessage : {text}"}]
    )
    return response.content[0].text.strip()


# ─── Menu déroulant langue ────────────────────────────────────────────────────

class LanguageSelect(discord.ui.Select):
    def __init__(self, message_id: int, invoker_id: int):
        self.message_id = message_id
        self.invoker_id = invoker_id

        options = [
            discord.SelectOption(label="🔎 Vérité cachée", value="TRUTH", description="Révèle la vraie signification"),
        ]
        for emoji, lang in LANG_EMOJIS.items():
            options.append(discord.SelectOption(label=f"{emoji} {lang.capitalize()}", value=emoji))

        super().__init__(
            placeholder="Choisis une langue ou la Vérité...",
            min_values=1,
            max_values=2,
            options=options[:25],
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ Ce panneau ne t'appartient pas.", ephemeral=True)
            return

        session = active_sessions.get(self.message_id)
        if not session:
            await interaction.response.send_message("❌ Session expirée.", ephemeral=True)
            return

        values = self.values
        has_truth = "TRUTH" in values
        lang_values = [v for v in values if v != "TRUTH"]

        # Validation
        if len(lang_values) > 1:
            await interaction.response.send_message(
                "❌ **Combinaison incompatible** : choisis une seule langue.",
                ephemeral=True
            )
            return

        session["selected_values"] = values
        selected_display = []
        if has_truth:
            selected_display.append("🔎 Vérité")
        for v in lang_values:
            selected_display.append(f"{v} {LANG_EMOJIS[v].capitalize()}")

        await interaction.response.edit_message(
            content=f"## Translater\n**Message :** *{session['original_text'][:80]}*\n\n**Sélection :** {' + '.join(selected_display)}\n\nConfirme avec ✅",
            view=self.view
        )


class TranslateView(discord.ui.View):
    def __init__(self, message_id: int, invoker_id: int):
        super().__init__(timeout=60)
        self.message_id = message_id
        self.invoker_id = invoker_id
        self.add_item(LanguageSelect(message_id=message_id, invoker_id=invoker_id))

    async def on_timeout(self):
        active_sessions.pop(self.message_id, None)

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.success, row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ Ce panneau ne t'appartient pas.", ephemeral=True)
            return

        session = active_sessions.pop(self.message_id, None)
        if not session:
            await interaction.response.send_message("❌ Session expirée.", ephemeral=True)
            return

        if "selected_values" not in session:
            await interaction.response.send_message("⚠️ Sélectionne d'abord une langue ou la Vérité !", ephemeral=True)
            active_sessions[self.message_id] = session
            return

        await interaction.response.defer(ephemeral=True)

        values = session["selected_values"]
        text = session["original_text"]
        original_message = session["message_ref"]
        translator = interaction.user.mention

        has_truth = "TRUTH" in values
        lang_values = [v for v in values if v != "TRUTH"]

        source_lang = detect_language(text)
        if source_lang is None:
            await interaction.followup.send(
                f"❌ **Langue non enregistrée** : cette langue n'est pas dans ma liste.\n"
                f"**Langues supportées :** {', '.join(LANG_EMOJIS.values())}",
                ephemeral=True
            )
            return

        source_emoji = LANG_TO_EMOJI.get(source_lang, "🏳️")

        # Cas 1 : traduction simple
        if not has_truth and len(lang_values) == 1:
            target_lang = LANG_EMOJIS[lang_values[0]]
            if target_lang == source_lang:
                result = f"{source_emoji} *(Le message est déjà en {source_lang}.)*\n*(par {translator})*"
            else:
                translated = translate_text(text, target_lang)
                result = f"{source_emoji} {translated}\n*(traduit par {translator})*"
            await original_message.reply(result)

        # Cas 2 : vérité seule
        elif has_truth and len(lang_values) == 0:
            truth = get_truth(text)
            result = f"{source_emoji} 🔎 {truth}\n*(révélé par {translator})*"
            await original_message.reply(result)

        # Cas 3 : vérité + langue
        elif has_truth and len(lang_values) == 1:
            target_lang = LANG_EMOJIS[lang_values[0]]
            truth = get_truth(text, target_lang)
            result = f"{source_emoji} 🔎 {truth}\n*(révélé par {translator})*"
            await original_message.reply(result)

        await interaction.followup.send("✅ Fait !", ephemeral=True)
        self.stop()

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ Ce panneau ne t'appartient pas.", ephemeral=True)
            return
        active_sessions.pop(self.message_id, None)
        await interaction.response.edit_message(content="❌ Session annulée.", view=None)
        self.stop()


@bot.tree.context_menu(name="Translater")
async def translate_context_menu(interaction: discord.Interaction, message: discord.Message):
    if message.id in active_sessions:
        await interaction.response.send_message("⏳ Une session est déjà en cours sur ce message.", ephemeral=True)
        return

    if not message.content.strip():
        await interaction.response.send_message("❌ Ce message ne contient pas de texte.", ephemeral=True)
        return

    active_sessions[message.id] = {
        "author_id": interaction.user.id,
        "original_text": message.content,
        "channel_id": interaction.channel_id,
        "message_ref": message,
    }

    view = TranslateView(message_id=message.id, invoker_id=interaction.user.id)
    await interaction.response.send_message(
        f"## Translater\n**Message :** *{message.content[:80]}{'...' if len(message.content) > 80 else ''}*\n\nChoisis une langue dans le menu puis confirme avec ✅",
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
    
