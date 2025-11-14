import os
import json
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

print(">>> BOT QUIZ POKER — VERSION OPTIMISÉE RAILWAY (2025) <<<")

# =====================================================================
# CONFIG
# =====================================================================

GUILD_ID = int(os.getenv("GUILD_ID", "1309118091766009856"))
SCORES_FILE = "scores.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Quiz actifs
quizzes = {}

# Scores
scores = {}

# =====================================================================
# RANK SYSTEM
# =====================================================================

RANKS = [
    (500, "ADRIAN MATHEOS"),
    (490, "ABI 1000€"),
    (450, "ABI 500€"),
    (380, "ABI 200€"),
    (300, "ABI 100€"),
    (230, "ABI 75€"),
    (170, "ABI 50€"),
    (120, "ABI 35€"),
    (80, "ABI 20€"),
    (50, "ABI 10€"),
    (25, "ABI 5€"),
    (10, "ABI 2€"),
    (0, "ABI 0€"),
]

RANK_COLORS = {
    "ABI 0€": 0x656565,
    "ABI 2€": 0x22A6B3,
    "ABI 5€": 0x27AE60,
    "ABI 10€": 0x2ECC71,
    "ABI 20€": 0xF1C40F,
    "ABI 35€": 0xF39C12,
    "ABI 50€": 0xE67E22,
    "ABI 75€": 0xD35400,
    "ABI 100€": 0xC0392B,
    "ABI 200€": 0x9B59B6,
    "ABI 500€": 0x8E44AD,
    "ABI 1000€": 0x3498DB,
    "ADRIAN MATHEOS": 0xE91E63,
}

def get_rank(points):
    for thr, rank in RANKS:
        if points >= thr:
            return rank
    return "ABI 0€"

def get_next_rank_info(points):
    for thr, rank in reversed(RANKS):
        if points < thr:
            return thr, rank, thr - points
    return None, None, None

# =====================================================================
# SCORES SYSTEM
# =====================================================================

def save_scores():
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=4, ensure_ascii=False)

def load_scores():
    global scores

    if os.path.exists(SCORES_FILE):
        try:
            with open(SCORES_FILE, "r", encoding="utf-8") as f:
                scores = json.load(f)
        except:
            scores = {}
    else:
        scores = {}

    scores.setdefault("all_time", {})
    scores.setdefault("monthly", {})
    scores.setdefault("last_month", datetime.now().month)

    now = datetime.now().month
    if scores["last_month"] != now:
        scores["monthly"] = {}
        scores["last_month"] = now
        save_scores()

load_scores()

# =====================================================================
# CARD COMBOS → EMOJI
# =====================================================================

suit_map = {"h": "♥️", "s": "♠️", "d": "♦️", "c": "♣️"}

def convert_combo_to_emojis(text):
    t = text.strip()
    if len(t) % 2 != 0:
        return text

    result = ""
    for i in range(0, len(t), 2):
        rank = t[i].upper()
        suit = t[i+1].lower()
        if rank not in "AKQJT98765432" or suit not in suit_map:
            return text
        result += f"{rank}{suit_map[suit]} "

    return result.strip()

# =====================================================================
# ROLE SYSTEM
# =====================================================================

async def update_user_rank_role(member, old_rank, new_rank):
    guild = member.guild

    def find(role_name):
        return discord.utils.get(guild.roles, name=role_name)

    # Création auto du rôle si manquant
    new_role = find(new_rank)
    if new_role is None:
        new_role = await guild.create_role(
            name=new_rank,
            colour=discord.Colour(RANK_COLORS[new_rank]),
            mentionable=True
        )

    if old_rank:
        old_role = find(old_rank)
        if old_role:
            try:
                await member.remove_roles(old_role)
            except:
                pass

    await member.add_roles(new_role)

# =====================================================================
# UI (SELECT + BUTTON) — FIX TOTAL
# =====================================================================

class QuizSelect(discord.ui.Select):
    def __init__(self, quiz_id, options):
        self.quiz_id = quiz_id

        super().__init__(
            custom_id=f"select_{quiz_id}",
            placeholder="Sélectionne tes réponses",
            min_values=1,
            max_values=len(options),
            options=[
                discord.SelectOption(label=l, value=l, description=t)
                for l, t in options
            ]
        )

    async def callback(self, interaction):
        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            return

        quiz["answers_temp"][interaction.user.id] = self.values

        print(f"[VOTE-SELECTION] {interaction.user} ({interaction.user.id}) → {self.values}")

        return  # IMPORTANT : AUCUNE RÉPONSE AU SELECT


class ValidateButton(discord.ui.Button):
    def __init__(self, quiz_id):
        super().__init__(
            label="Valider",
            style=discord.ButtonStyle.success,
            custom_id=f"validate_{quiz_id}"
        )
        self.quiz_id = quiz_id

    async def callback(self, interaction):
        # Toujours deférer immédiatement → zéro timeout
        await interaction.response.defer(ephemeral=True)
        await self.process(interaction)

    async def process(self, interaction):
        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            await interaction.followup.send("❌ Quiz terminé.", ephemeral=True)
            return

        user = interaction.user
        uid = str(user.id)

        if user.id not in quiz["answers_temp"]:
            await interaction.followup.send("❌ Tu dois sélectionner une réponse.", ephemeral=True)
            return

        if user.id in quiz["answers"]:
            await interaction.followup.send("❌ Tu as déjà répondu.", ephemeral=True)
            return

        selected = quiz["answers_temp"][user.id]
        quiz["answers"][user.id] = selected

        correct = quiz["correct"]
        pts = quiz["points"]

        bonnes = sum(1 for r in selected if r in correct)
        mauvaises = sum(1 for r in selected if r not in correct)
        gained = (bonnes * pts) - (mauvaises * 0.5)

        old_points = scores["all_time"].get(uid, {"points": 0})["points"]
        old_rank = get_rank(old_points)

        # Update scores
        scores["all_time"].setdefault(uid, {"points": 0.0, "questions": 0})
        scores["all_time"][uid]["points"] += gained
        scores["all_time"][uid]["questions"] += 1

        scores["monthly"].setdefault(uid, {"points": 0.0, "questions": 0})
        scores["monthly"][uid]["points"] += gained
        scores["monthly"][uid]["questions"] += 1

        save_scores()

        new_points = scores["all_time"][uid]["points"]
        new_rank = get_rank(new_points)

        if new_rank != old_rank:
            quiz["rankups"][uid] = new_rank

        print(f"[VOTE-VALIDATION] {interaction.user} ({interaction.user.id}) "
              f"→ {selected} | {gained} pts (Good={bonnes}, Bad={mauvaises})")

        await interaction.followup.send("✅ Réponse enregistrée !", ephemeral=True)


class QuizView(discord.ui.View):
    def __init__(self, quiz_id, options):
        super().__init__(timeout=None)
        self.add_item(QuizSelect(quiz_id, options))
        self.add_item(ValidateButton(quiz_id))

# =====================================================================
# COMMANDES
# =====================================================================

@bot.tree.command(name="quiz2", description="Créer un quiz multi-choix")
async def quiz2(interaction, quiz_id: str, question: str, choix: str, bonne_reponse: str, points: int):

    if quiz_id in quizzes:
        await interaction.response.send_message("❌ ID déjà utilisé.", ephemeral=True)
        return

    raw = [convert_combo_to_emojis(c.strip()) for c in choix.split("|")]
    letters = [chr(ord("A") + i) for i in range(len(raw))]
    opts = list(zip(letters, raw))

    correct = [x.strip().upper() for x in bonne_reponse.split(",")]

    quizzes[quiz_id] = {
        "question": question,
        "options": opts,
        "correct": correct,
        "points": points,
        "answers": {},
        "answers_temp": {},
        "rankups": {},
        "author_id": interaction.user.id,
    }

    embed = discord.Embed(
        title=f"🧠 Quiz `{quiz_id}`",
        description=f"{question}\n\n**{points} pt / bonne ; -0.5 par mauvaise**",
        color=0x00B0F4
    )
    for l, t in opts:
        embed.add_field(name=l, value=t, inline=False)

    view = QuizView(quiz_id, opts)
    bot.add_view(view)

    await interaction.response.send_message(embed=embed, view=view)


# =====================================================================
# REVEAL
# =====================================================================

@bot.tree.command(name="reveal", description="Révèle un quiz")
async def reveal(interaction, quiz_id: str):

    if quiz_id not in quizzes:
        await interaction.response.send_message("❌ Quiz introuvable.", ephemeral=True)
        return

    quiz = quizzes[quiz_id]
    q = quiz["question"]
    opts = quiz["options"]
    correct = quiz["correct"]
    answers = quiz["answers"]
    p = quiz["points"]

    counts = {l: 0 for l, _ in opts}
    for rep in answers.values():
        for r in rep:
            counts[r] += 1

    rep_text = "\n".join(
        f"{'✅' if l in correct else '❌'} **{l}** — {t} ({counts[l]} votes)"
        for l, t in opts
    )

    pts_text = []
    for uid_int, rep in answers.items():
        bonnes = sum(1 for r in rep if r in correct)
        mauvaises = sum(1 for r in rep if r not in correct)
        gained = (bonnes * p) - (mauvaises * 0.5)
        user = await bot.fetch_user(uid_int)
        pts_text.append(f"**{user.name}** : {gained:.1f} pts")

    pts_text = "\n".join(pts_text) or "Personne"

    rank_lines = []
    for uid, new_rank in quiz["rankups"].items():
        user = await bot.fetch_user(int(uid))
        rank_lines.append(f"🔥 {user.name} → {new_rank}")

    rank_text = "\n".join(rank_lines) or "Aucun"

    await interaction.response.send_message(
        f"### 🧠 Quiz `{quiz_id}`\n"
        f"❓ {q}\n"
        f"{rep_text}\n\n"
        f"### 🏅 Points :\n{pts_text}\n\n"
        f"### 🎖 Rank-ups :\n{rank_text}"
    )

    del quizzes[quiz_id]


# =====================================================================
# VOTES (privé)
# =====================================================================

@bot.tree.command(name="votes", description="Voir les votes d’un quiz (privé pour l’auteur)")
async def votes(interaction, quiz_id: str):

    if quiz_id not in quizzes:
        await interaction.response.send_message("❌ Quiz introuvable.", ephemeral=True)
        return

    quiz = quizzes[quiz_id]

    if interaction.user.id != quiz["author_id"]:
        await interaction.response.send_message("❌ Tu n'es pas l'auteur.", ephemeral=True)
        return

    answers = quiz["answers"]
    if not answers:
        await interaction.response.send_message("Personne n'a répondu.", ephemeral=True)
        return

    lines = []
    for uid, rep in answers.items():
        user = await bot.fetch_user(uid)
        lines.append(f"**{user.name}** : {', '.join(rep)}")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# =====================================================================
# LEADERBOARD
# =====================================================================

@bot.tree.command(name="leaderboard", description="Classement global + mensuel")
async def leaderboard(interaction):

    if not scores["all_time"]:
        await interaction.response.send_message("Aucun score.", ephemeral=True)
        return

    emb = discord.Embed(title="🏆 Leaderboard Poker", color=0xFFD700)

    # All-time
    ranking = sorted(scores["all_time"].items(), key=lambda x: x[1]["points"], reverse=True)
    text = ""
    for i, (uid, data) in enumerate(ranking, start=1):
        user = await bot.fetch_user(int(uid))
        text += f"**{i}. {user.name}** — {data['points']:.1f} pts\n"
    emb.add_field(name="🔥 ALL TIME", value=text, inline=False)

    # Monthly
    ranking_m = sorted(scores["monthly"].items(), key=lambda x: x[1]["points"], reverse=True)
    text_m = ""
    for i, (uid, data) in enumerate(ranking_m, start=1):
        user = await bot.fetch_user(int(uid))
        text_m += f"**{i}. {user.name}** — {data['points']:.1f} pts\n"
    emb.add_field(name="📅 CE MOIS-CI", value=text_m or "Personne", inline=False)

    await interaction.response.send_message(embed=emb)


# =====================================================================
# MYRANK
# =====================================================================

@bot.tree.command(name="myrank", description="Voir ton rang + stats")
async def myrank(interaction):

    uid = str(interaction.user.id)
    if uid not in scores["all_time"]:
        await interaction.response.send_message("Aucun score.", ephemeral=True)
        return

    pts = scores["all_time"][uid]["points"]
    rank = get_rank(pts)
    nxt_thr, nxt_rank, diff = get_next_rank_info(pts)

    emb = discord.Embed(title=f"🎖 {interaction.user.name}", color=0xFFD700)
    emb.add_field(name="Rang", value=rank, inline=False)
    emb.add_field(name="Points", value=f"{pts:.1f}", inline=True)
    emb.add_field(name="Questions", value=scores["all_time"][uid]["questions"], inline=True)

    if nxt_rank:
        emb.add_field(name="Prochain rang", value=nxt_rank, inline=False)
        emb.add_field(name="Manque", value=f"{diff:.1f} pts", inline=True)

    await interaction.response.send_message(embed=emb)


# =====================================================================
# RESET SCORES
# =====================================================================

@bot.tree.command(name="reset_scores", description="Reset scores (admin)")
async def reset_scores(interaction):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin uniquement.", ephemeral=True)
        return

    scores["all_time"] = {}
    scores["monthly"] = {}
    save_scores()

    await interaction.response.send_message("Scores reset !")


# =====================================================================
# SYNC_ROLES
# =====================================================================

@bot.tree.command(name="sync_roles", description="Créer les rôles ABI")
async def sync_roles(interaction):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin uniquement.", ephemeral=True)
        return

    guild = interaction.guild
    created = []

    for rank, color in RANK_COLORS.items():
        if not discord.utils.get(guild.roles, name=rank):
            await guild.create_role(
                name=rank,
                colour=discord.Colour(color),
                mentionable=True
            )
            created.append(rank)

    if created:
        await interaction.response.send_message("Rôles créés :\n" + "\n".join(created))
    else:
        await interaction.response.send_message("Tous les rôles existent déjà.")


# =====================================================================
# FORCE SYNC
# =====================================================================

@bot.tree.command(name="force_sync", description="Forcer la synchro des commandes")
async def force_sync(interaction):

    guild = discord.Object(id=GUILD_ID)
    cmds = await bot.tree.sync(guild=guild)

    await interaction.response.send_message(
        f"Commandes synchronisées : {[c.name for c in cmds]}",
        ephemeral=True
    )


# =====================================================================
# ON READY
# =====================================================================

@bot.event
async def on_ready():
    print(f"Bot connecté : {bot.user}")
    guild = discord.Object(id=GUILD_ID)
    synced = await bot.tree.sync(guild=guild)
    print("Commandes SYNC :", [c.name for c in synced])


# =====================================================================
# RUN BOT
# =====================================================================

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ ERREUR : BOT_TOKEN manquant dans Railway")
else:
    bot.run(TOKEN)
