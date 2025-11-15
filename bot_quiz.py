import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime

# -------------------- CONFIG --------------------
GUILD_ID = 1069968737580613752
SCORES_FILE = "scores.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Stockage des quiz actifs
quizzes = {}

# -------------------- SCORE STORAGE --------------------
scores = {}

# -------------------- RANK SYSTEM --------------------
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
    (0, "ABI 0€")
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
    "ADRIAN MATHEOS": 0xE91E63
}

def get_rank(points: float):
    for thr, r in RANKS:
        if points >= thr:
            return r
    return "ABI 0€"

def get_next_rank_info(points: float):
    for thr, r in reversed(RANKS):
        if points < thr:
            return thr, r, thr - points
    return None, None, None

# -------------------- SAVE / LOAD --------------------
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

# -------------------- COMBO → EMOJI --------------------
suit_map = {"h": "♥️", "s": "♠️", "d": "♦️", "c": "♣️"}

def convert_combo_to_emojis(text: str):
    t = text.strip()
    if len(t) >= 2 and len(t) % 2 == 0:
        r = ""
        ok = True
        for i in range(0, len(t), 2):
            rank = t[i].upper()
            suit = t[i+1].lower()
            if rank not in "AKQJT98765432" or suit not in suit_map:
                ok = False
                break
            r += f"{rank}{suit_map[suit]} "
        if ok:
            return r.strip()
    return text

# -------------------- ROLE MANAGEMENT --------------------
async def update_user_rank_role(member, old_rank, new_rank):
    guild = member.guild

    def find(name):
        return discord.utils.get(guild.roles, name=name)

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

    try:
        await member.add_roles(new_role)
    except:
        pass

# -------------------- UI : BOUTONS --------------------
class QuizButton(discord.ui.Button):
    def __init__(self, quiz_id, label, value):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id=f"{quiz_id}_{value}")
        self.quiz_id = quiz_id
        self.value = value

    async def callback(self, interaction: discord.Interaction):

        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            return await interaction.response.send_message("❌ Ce quiz est terminé.", ephemeral=True)

        user = interaction.user
        uid = user.id

        if uid not in quiz["temp"]:
            quiz["temp"][uid] = set()

        if self.value in quiz["temp"][uid]:
            quiz["temp"][uid].remove(self.value)
            self.style = discord.ButtonStyle.secondary
        else:
            quiz["temp"][uid].add(self.value)
            self.style = discord.ButtonStyle.success

        await interaction.response.edit_message(view=interaction.message.components[0])

class ValidateButton(discord.ui.Button):
    def __init__(self, quiz_id):
        super().__init__(label="Valider", style=discord.ButtonStyle.green, custom_id=f"validate_{quiz_id}")
        self.quiz_id = quiz_id

    async def callback(self, interaction: discord.Interaction):

        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            return await interaction.response.send_message("❌ Ce quiz est terminé.", ephemeral=True)

        user = interaction.user
        uid = str(user.id)

        if user.id not in quiz["temp"] or len(quiz["temp"][user.id]) == 0:
            return await interaction.response.send_message("❌ Tu n'as sélectionné aucune réponse.", ephemeral=True)

        if user.id in quiz["answers"]:
            return await interaction.response.send_message("❌ Tu as déjà validé.", ephemeral=True)

        selected = quiz["temp"][user.id]
        quiz["answers"][user.id] = selected

        p = quiz["points"]
        correct = quiz["correct"]

        bonnes = len([x for x in selected if x in correct])
        mauvaises = len([x for x in selected if x not in correct])

        gained = (bonnes * p) - (mauvaises * 0.5)

        old_pts = scores["all_time"].get(uid, {"points": 0})["points"]
        old_rank = get_rank(old_pts)

        scores["all_time"].setdefault(uid, {"points": 0.0, "questions": 0})
        scores["monthly"].setdefault(uid, {"points": 0.0, "questions": 0})

        scores["all_time"][uid]["points"] += gained
        scores["all_time"][uid]["questions"] += 1

        scores["monthly"][uid]["points"] += gained
        scores["monthly"][uid]["questions"] += 1

        save_scores()

        new_pts = scores["all_time"][uid]["points"]
        new_rank = get_rank(new_pts)

        if new_rank != old_rank:
            quiz["rankups"][uid] = new_rank

        await interaction.response.send_message("✅ Réponse enregistrée !", ephemeral=True)


class QuizView(discord.ui.View):
    def __init__(self, quiz_id, options):
        super().__init__(timeout=None)

        row = []
        for l, t in options:
            row.append(QuizButton(quiz_id, f"{l} — {t}", l))

        for btn in row:
            self.add_item(btn)

        self.add_item(ValidateButton(quiz_id))

# -------------------- /QUIZ2 --------------------
@bot.tree.command(name="quiz2", description="Créer un quiz")
async def quiz2(interaction, quiz_id: str, question: str, choix: str, bonne_reponse: str, points: int):

    if quiz_id in quizzes:
        return await interaction.response.send_message("❌ Cet ID existe déjà.", ephemeral=True)

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
        "temp": {},
        "rankups": {},
        "author_id": interaction.user.id
    }

    emb = discord.Embed(
        title=f"🧠 Quiz `{quiz_id}`",
        description=f"**{question}**\n\n**{points} pt / bonne, -0.5 / mauvaise**",
        color=0x00B0F4
    )

    for l, t in opts:
        emb.add_field(name=l, value=t, inline=False)

    view = QuizView(quiz_id, opts)
    bot.add_view(view)

    await interaction.response.send_message(embed=emb, view=view)

# -------------------- /REVEAL --------------------
@bot.tree.command(name="reveal", description="Révéler un quiz")
async def reveal(interaction, quiz_id: str):

    if quiz_id not in quizzes:
        return await interaction.response.send_message("❌ Aucun quiz trouvé.", ephemeral=True)

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

    opt_text = "\n".join(
        f"{'✅' if l in correct else '❌'} **{l}** — {t} ({counts[l]} votes)"
        for l, t in opts
    )

    pts_lines = []
    for uid, rep in answers.items():
        bonnes = sum(1 for r in rep if r in correct)
        mauvaises = sum(1 for r in rep if r not in correct)
        gained = (bonnes * p) - (mauvaises * 0.5)

        user = await bot.fetch_user(uid)
        pts_lines.append(f"**{user.name}** : {gained:.1f} pts")

    rank_text = ""
    for uid, new_rank in quiz["rankups"].items():
        user = await bot.fetch_user(uid)
        member = interaction.guild.get_member(int(uid))

        old_pts = scores["all_time"][uid]["points"]
        old_rank = get_rank(old_pts - 0.001)

        if member:
            await update_user_rank_role(member, old_rank, new_rank)

        rank_text += f"🔥 **{user.name}** → {new_rank}\n"

    await interaction.response.send_message(
        f"### 🧠 Quiz `{quiz_id}`\n"
        f"❓ {q}\n\n"
        f"{opt_text}\n\n"
        f"### 🏅 Points\n{chr(10).join(pts_lines)}\n\n"
        f"### 🎖 Rank-ups\n{rank_text or 'Aucun.'}"
    )

    del quizzes[quiz_id]

# -------------------- ADMIN POINTS CONTROL --------------------
@bot.tree.command(name="set_points", description="Définir les points d'un joueur (ADMIN)")
async def set_points(interaction: discord.Interaction, user: discord.User, points: float):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin uniquement.", ephemeral=True)

    uid = str(user.id)

    scores["all_time"].setdefault(uid, {"points": 0.0, "questions": 0})
    scores["monthly"].setdefault(uid, {"points": 0.0, "questions": 0})

    scores["all_time"][uid]["points"] = points
    scores["monthly"][uid]["points"] = points
    save_scores()

    await interaction.response.send_message(
        f"✅ Score de **{user.name}** mis à **{points} pts**"
    )


@bot.tree.command(name="add_points", description="Ajouter des points à un joueur (ADMIN)")
async def add_points(interaction: discord.Interaction, user: discord.User, points: float):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin uniquement.", ephemeral=True)

    uid = str(user.id)

    scores["all_time"].setdefault(uid, {"points": 0.0, "questions": 0})
    scores["monthly"].setdefault(uid, {"points": 0.0, "questions": 0})

    scores["all_time"][uid]["points"] += points
    scores["monthly"][uid]["points"] += points
    save_scores()

    await interaction.response.send_message(
        f"➕ {points} pts ajoutés à **{user.name}**."
    )


@bot.tree.command(name="remove_points", description="Retirer des points à un joueur (ADMIN)")
async def remove_points(interaction: discord.Interaction, user: discord.User, points: float):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin uniquement.", ephemeral=True)

    uid = str(user.id)

    scores["all_time"].setdefault(uid, {"points": 0.0, "questions": 0})
    scores["monthly"].setdefault(uid, {"points": 0.0, "questions": 0})

    scores["all_time"][uid]["points"] -= points
    scores["monthly"][uid]["points"] -= points
    save_scores()

    await interaction.response.send_message(
        f"➖ {points} pts retirés à **{user.name}**."
    )

# -------------------- /LEADERBOARD --------------------
@bot.tree.command(name="leaderboard", description="Voir le classement")
async def leaderboard(interaction):

    if not scores["all_time"]:
        return await interaction.response.send_message("Aucun score.", ephemeral=True)

    emb = discord.Embed(title="🏆 Leaderboard Poker", color=0xFFD700)

    ordered = sorted(scores["all_time"].items(), key=lambda x: x[1]["points"], reverse=True)
    txt = ""
    for i, (uid, data) in enumerate(ordered, 1):
        user = await bot.fetch_user(uid)
        r = get_rank(data["points"])
        txt += f"**{i}. {user.name}** — {data['points']:.1f} pts | {r}\n"

    emb.add_field(name="🔥 ALL-TIME", value=txt or "Personne.", inline=False)

    ord_m = sorted(scores["monthly"].items(), key=lambda x: x[1]["points"], reverse=True)
    txt2 = ""
    for i, (uid, data) in enumerate(ord_m, 1):
        user = await bot.fetch_user(uid)
        r = get_rank(data["points"])
        txt2 += f"**{i}. {user.name}** — {data['points']:.1f} pts | {r}\n"

    emb.add_field(name="📅 CE MOIS-CI", value=txt2 or "Personne.", inline=False)

    await interaction.response.send_message(embed=emb)

# -------------------- ON READY --------------------
@bot.event
async def on_ready():
    print("Bot connecté en tant que :", bot.user)

    guild_id = int(os.getenv("GUILD_ID"))
    guild = discord.Object(id=guild_id)

    try:
        cmds = await bot.tree.sync(guild=guild)
        print(">>> SYNC OK :", [c.name for c in cmds])
    except Exception as e:
        print(">>> ERREUR SYNC :", e)

# -------------------- RUN --------------------
bot.run(os.getenv("BOT_TOKEN"))

