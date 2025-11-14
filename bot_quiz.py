import os
import json
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

print(">>> BOT QUIZ POKER — VERSION BOUTONS ON/OFF (RAILWAY) <<<")

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

# Quiz actifs en mémoire
quizzes = {}
# Scores persos
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


def get_rank(points: float) -> str:
    for thr, rank in RANKS:
        if points >= thr:
            return rank
    return "ABI 0€"


def get_next_rank_info(points: float):
    for thr, rank in reversed(RANKS):
        if points < thr:
            return thr, rank, thr - points
    return None, None, None


# =====================================================================
# SCORES SAVE / LOAD
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
        except Exception:
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
print(">>> SCORES CHARGÉS :", scores.keys())


# =====================================================================
# CARD COMBOS → EMOJI
# =====================================================================

suit_map = {"h": "♥️", "s": "♠️", "d": "♦️", "c": "♣️"}


def convert_combo_to_emojis(text: str) -> str:
    t = text.strip()
    if len(t) % 2 != 0:
        return text

    res = ""
    for i in range(0, len(t), 2):
        rank = t[i].upper()
        suit = t[i + 1].lower()
        if rank not in "AKQJT98765432" or suit not in suit_map:
            return text
        res += f"{rank}{suit_map[suit]} "
    return res.strip()


# =====================================================================
# ROLE SYSTEM
# =====================================================================

async def update_user_rank_role(member: discord.Member, old_rank: str, new_rank: str):
    guild = member.guild

    def find(name: str):
        return discord.utils.get(guild.roles, name=name)

    new_role = find(new_rank)
    if new_role is None:
        new_role = await guild.create_role(
            name=new_rank,
            colour=discord.Colour(RANK_COLORS[new_rank]),
            mentionable=True,
        )

    if old_rank:
        old_role = find(old_rank)
        if old_role:
            try:
                await member.remove_roles(old_role)
            except Exception:
                pass

    try:
        await member.add_roles(new_role)
    except Exception:
        pass


# =====================================================================
# UI : BOUTONS ON/OFF PAR LETTRE
# =====================================================================

class OptionButton(discord.ui.Button):
    def __init__(self, quiz_id: str, letter: str, text: str):
        self.quiz_id = quiz_id
        self.letter = letter
        self.text = text
        super().__init__(
            label=letter,
            style=discord.ButtonStyle.secondary,
            custom_id=f"opt_{quiz_id}_{letter}",
        )

    async def callback(self, interaction: discord.Interaction):
        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            return

        user_id = interaction.user.id
        temp = quiz["answers_temp"].setdefault(user_id, set())

        # Toggle ON/OFF
        if self.letter in temp:
            temp.remove(self.letter)
            state = "OFF"
        else:
            temp.add(self.letter)
            state = "ON"

        print(
            f"[VOTE-CLICK] {interaction.user} ({interaction.user.id}) "
            f"Quiz={self.quiz_id} Button={self.letter} State={state}"
        )

        # On ne répond pas (déjà cliqué, pas besoin de message)
        await interaction.response.defer(ephemeral=True)


class ValidateButton(discord.ui.Button):
    def __init__(self, quiz_id: str):
        self.quiz_id = quiz_id
        super().__init__(
            label="Valider",
            style=discord.ButtonStyle.success,
            custom_id=f"validate_{quiz_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        # On defère tout de suite → évite tous les "interaction failed"
        await interaction.response.defer(ephemeral=True)
        await self.process(interaction)

    async def process(self, interaction: discord.Interaction):
        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            await interaction.followup.send("❌ Ce quiz est terminé.", ephemeral=True)
            return

        user = interaction.user
        uid_str = str(user.id)

        temp = quiz["answers_temp"].get(user.id)
        if not temp:
            await interaction.followup.send(
                "❌ Tu dois sélectionner au moins une réponse.",
                ephemeral=True,
            )
            return

        if user.id in quiz["answers"]:
            await interaction.followup.send(
                "❌ Tu as déjà validé ta réponse.",
                ephemeral=True,
            )
            return

        # Liste triée des lettres sélectionnées
        selected = sorted(temp)
        quiz["answers"][user.id] = selected

        correct = quiz["correct"]
        points_value = quiz["points"]

        bonnes = sum(1 for r in selected if r in correct)
        mauvaises = sum(1 for r in selected if r not in correct)
        gained = (bonnes * points_value) - (mauvaises * 0.5)

        old_points = scores["all_time"].get(uid_str, {"points": 0})["points"]
        old_rank = get_rank(old_points)

        scores["all_time"].setdefault(uid_str, {"points": 0.0, "questions": 0})
        scores["all_time"][uid_str]["points"] += gained
        scores["all_time"][uid_str]["questions"] += 1

        scores["monthly"].setdefault(uid_str, {"points": 0.0, "questions": 0})
        scores["monthly"][uid_str]["points"] += gained
        scores["monthly"][uid_str]["questions"] += 1

        save_scores()

        new_points = scores["all_time"][uid_str]["points"]
        new_rank = get_rank(new_points)

        if new_rank != old_rank:
            quiz["rankups"][uid_str] = new_rank

        print(
            f"[VOTE-VALIDATION] {interaction.user} ({interaction.user.id}) "
            f"Quiz={self.quiz_id} Selected={selected} "
            f"Gagné={gained} pts (Bonnes={bonnes}, Mauvaises={mauvaises})"
        )

        await interaction.followup.send(
            f"✅ Réponse enregistrée : {', '.join(selected)}",
            ephemeral=True,
        )


class QuizView(discord.ui.View):
    def __init__(self, quiz_id: str, options):
        super().__init__(timeout=None)
        # boutons A / B / C ...
        for letter, text in options:
            self.add_item(OptionButton(quiz_id, letter, text))
        # bouton Valider
        self.add_item(ValidateButton(quiz_id))


# =====================================================================
# COMMANDES
# =====================================================================

@bot.tree.command(name="quiz2", description="Créer un quiz multi-choix (boutons)")
@app_commands.describe(
    quiz_id="ID du quiz (ex: probe1)",
    question="La question",
    choix="Choix séparés par |",
    bonne_reponse="Bonne(s) lettre(s) ex: A,C",
    points="Points par bonne réponse",
)
async def quiz2(
    interaction: discord.Interaction,
    quiz_id: str,
    question: str,
    choix: str,
    bonne_reponse: str,
    points: int,
):
    if quiz_id in quizzes:
        await interaction.response.send_message(
            "❌ Cet ID de quiz existe déjà.",
            ephemeral=True,
        )
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
        "answers": {},        # user_id (int) -> list[str]
        "answers_temp": {},   # user_id (int) -> set[str]
        "rankups": {},        # user_id (str) -> new_rank
        "author_id": interaction.user.id,
    }

    embed = discord.Embed(
        title=f"🧠 Quiz `{quiz_id}`",
        description=f"{question}\n\n**{points} pt / bonne, -0.5 / mauvaise**",
        color=0x00B0F4,
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
@app_commands.describe(quiz_id="ID du quiz à révéler")
async def reveal(interaction: discord.Interaction, quiz_id: str):
    quiz = quizzes.get(quiz_id)
    if not quiz:
        await interaction.response.send_message(
            "❌ Aucun quiz avec cet ID.",
            ephemeral=True,
        )
        return

    q = quiz["question"]
    options = quiz["options"]
    correct = quiz["correct"]
    answers = quiz["answers"]
    p = quiz["points"]

    counts = {l: 0 for l, _ in options}
    for rep in answers.values():
        for r in rep:
            if r in counts:
                counts[r] += 1

    opt_text = "\n".join(
        f"{'✅' if l in correct else '❌'} **{l}** — {t} ({counts[l]} votes)"
        for l, t in options
    )

    pts_lines = []
    for uid_int, rep in answers.items():
        bonnes = sum(1 for r in rep if r in correct)
        mauvaises = sum(1 for r in rep if r not in correct)
        gained = (bonnes * p) - (mauvaises * 0.5)
        user = await bot.fetch_user(uid_int)
        pts_lines.append(f"**{user.name}** : {gained:.1f} pts")
    pts_text = "\n".join(pts_lines) or "Personne."

    rank_lines = []
    for uid_str, new_rank in quiz["rankups"].items():
        user = await bot.fetch_user(int(uid_str))
        member = interaction.guild.get_member(int(uid_str))
        old_pts = scores["all_time"][uid_str]["points"]
        old_rank = get_rank(old_pts - 0.0001)
        if member:
            await update_user_rank_role(member, old_rank, new_rank)
        rank_lines.append(f"🔥 {user.name} → {new_rank}")
    rank_text = "\n".join(rank_lines) or "Aucun."

    await interaction.response.send_message(
        f"### 🧠 Quiz `{quiz_id}`\n"
        f"❓ {q}\n\n"
        f"🃏 Bonnes réponses : {', '.join(correct)}\n"
        f"{opt_text}\n\n"
        f"### 🏅 Points :\n{pts_text}\n\n"
        f"### 🎖 Rank-ups :\n{rank_text}"
    )

    del quizzes[quiz_id]


# =====================================================================
# VOTES (privé pour l’auteur)
# =====================================================================

@bot.tree.command(name="votes", description="Voir les votes (auteur uniquement)")
@app_commands.describe(quiz_id="ID du quiz")
async def votes(interaction: discord.Interaction, quiz_id: str):
    quiz = quizzes.get(quiz_id)
    if not quiz:
        await interaction.response.send_message(
            "❌ Aucun quiz avec cet ID.",
            ephemeral=True,
        )
        return

    if quiz["author_id"] != interaction.user.id:
        await interaction.response.send_message(
            "❌ Tu n'es pas l'auteur de ce quiz.",
            ephemeral=True,
        )
        return

    answers = quiz["answers"]
    if not answers:
        await interaction.response.send_message(
            "Personne n'a encore répondu.",
            ephemeral=True,
        )
        return

    lines = []
    for uid_int, rep in answers.items():
        user = await bot.fetch_user(uid_int)
        lines.append(f"**{user.name}** : {', '.join(rep)}")

    await interaction.response.send_message(
        "👀 **Votes enregistrés :**\n\n" + "\n".join(lines),
        ephemeral=True,
    )


# =====================================================================
# LEADERBOARD
# =====================================================================

@bot.tree.command(name="leaderboard", description="Classement all-time + mensuel")
async def leaderboard(interaction: discord.Interaction):
    if not scores["all_time"]:
        await interaction.response.send_message(
            "Aucun score pour l'instant.",
            ephemeral=True,
        )
        return

    emb = discord.Embed(title="🏆 Leaderboard Poker", color=0xFFD700)

    # All-time
    ordered_all = sorted(scores["all_time"].items(), key=lambda x: x[1]["points"], reverse=True)
    txt_all = ""
    for i, (uid, data) in enumerate(ordered_all, 1):
        user = await bot.fetch_user(int(uid))
        r = get_rank(data["points"])
        txt_all += f"**{i}. {user.name}** — {data['points']:.1f} pts | {r}\n"
    emb.add_field(name="🔥 ALL-TIME", value=txt_all or "Personne.", inline=False)

    # Monthly
    ordered_m = sorted(scores["monthly"].items(), key=lambda x: x[1]["points"], reverse=True)
    txt_m = ""
    for i, (uid, data) in enumerate(ordered_m, 1):
        user = await bot.fetch_user(int(uid))
        r = get_rank(data["points"])
        txt_m += f"**{i}. {user.name}** — {data['points']:.1f} pts | {r}\n"
    emb.add_field(name="📅 CE MOIS-CI", value=txt_m or "Personne.", inline=False)

    await interaction.response.send_message(embed=emb)


# =====================================================================
# MYRANK
# =====================================================================

@bot.tree.command(name="myrank", description="Voir ton rang")
async def myrank(interaction: discord.Interaction):
    uid = str(interaction.user.id)

    if uid not in scores["all_time"]:
        await interaction.response.send_message(
            "Tu n'as pas encore de score.",
            ephemeral=True,
        )
        return

    data = scores["all_time"][uid]
    pts = data["points"]
    rank = get_rank(pts)
    nxt_thr, nxt_rank, diff = get_next_rank_info(pts)

    emb = discord.Embed(title=f"🎖 {interaction.user.name}", color=0xFFD700)
    emb.add_field(name="Rang", value=rank, inline=False)
    emb.add_field(name="Points", value=f"{pts:.1f}", inline=True)
    emb.add_field(name="Questions", value=data["questions"], inline=True)

    if nxt_rank:
        emb.add_field(name="Prochain rang", value=nxt_rank, inline=False)
        emb.add_field(name="Manque", value=f"{diff:.1f} pts", inline=True)

    await interaction.response.send_message(embed=emb)


# =====================================================================
# RESET SCORES
# =====================================================================

@bot.tree.command(name="reset_scores", description="Reset tous les scores (admin)")
async def reset_scores(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Réservé aux admins.",
            ephemeral=True,
        )
        return

    scores["all_time"] = {}
    scores["monthly"] = {}
    save_scores()

    await interaction.response.send_message("✅ Scores réinitialisés.")


# =====================================================================
# SYNC_ROLES
# =====================================================================

@bot.tree.command(name="sync_roles", description="Créer les rôles ABI (admin)")
async def sync_roles(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Réservé aux admins.",
            ephemeral=True,
        )
        return

    guild = interaction.guild
    created = []

    for rank_name, color in RANK_COLORS.items():
        if not discord.utils.get(guild.roles, name=rank_name):
            await guild.create_role(
                name=rank_name,
                colour=discord.Colour(color),
                mentionable=True,
            )
            created.append(rank_name)

    if created:
        await interaction.response.send_message(
            "Rôles créés :\n" + "\n".join(created)
        )
    else:
        await interaction.response.send_message("Tous les rôles existent déjà.")


# =====================================================================
# FORCE_SYNC (debug)
# =====================================================================

@bot.tree.command(name="force_sync", description="Forcer la sync des commandes (debug)")
async def force_sync(interaction: discord.Interaction):
    guild = discord.Object(id=GUILD_ID)
    cmds = await bot.tree.sync(guild=guild)
    names = [c.name for c in cmds]
    await interaction.response.send_message(
        f"🔄 Commandes synchronisées : {names}",
        ephemeral=True,
    )


# =====================================================================
# ON_READY
# =====================================================================

@bot.event
async def on_ready():
    print(f"Bot connecté : {bot.user}")
    guild = discord.Object(id=GUILD_ID)
    cmds = await bot.tree.sync(guild=guild)
    print("Commandes SYNC :", [c.name for c in cmds])


# =====================================================================
# RUN
# =====================================================================

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ ERREUR : BOT_TOKEN manquant dans Railway")
else:
    bot.run(TOKEN)
