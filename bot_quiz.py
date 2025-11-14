import os
import json
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

print(">>> BOT QUIZ POKER — VERSION MODAL + QUESTION & CHOIX DANS LA FENÊTRE <<<")

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

# STOCKAGE DES QUIZZ
quizzes = {}

# SCORES PERSISTANTS
scores = {}

# =====================================================================
# RANKS
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
    for thr, r in RANKS:
        if points >= thr:
            return r
    return "ABI 0€"


def get_next_rank_info(points: float):
    for thr, r in reversed(RANKS):
        if points < thr:
            return thr, r, thr - points
    return None, None, None

# =====================================================================
# LOAD / SAVE
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
# COMBOS → EMOJI
# =====================================================================

suit_map = {"h": "♥️", "s": "♠️", "d": "♦️", "c": "♣️"}


def convert_combo_to_emojis(text):
    t = text.strip()
    if len(t) % 2 != 0:
        return text

    r = ""
    for i in range(0, len(t), 2):
        rank = t[i].upper()
        suit = t[i+1].lower()
        if rank not in "AKQJT98765432" or suit not in suit_map:
            return text
        r += f"{rank}{suit_map[suit]} "
    return r.strip()

# =====================================================================
# ROLE SYSTEM
# =====================================================================

async def update_user_rank_role(member, old_rank, new_rank):
    guild = member.guild

    def find(name):
        return discord.utils.get(guild.roles, name=name)

    new_role = find(new_rank)
    if new_role is None:
        new_role = await guild.create_role(
            name=new_rank,
            colour=discord.Color(RANK_COLORS[new_rank]),
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

# =====================================================================
# MODAL DE RÉPONSE
# =====================================================================

class AnswerModal(discord.ui.Modal):
    def __init__(self, quiz_id, question, options, valid_letters):
        super().__init__(title=f"Réponse au quiz {quiz_id}")
        self.quiz_id = quiz_id
        self.valid_letters = valid_letters

        txt_options = "\n".join([f"{l} — {t}" for l, t in options])

        self.info = discord.ui.TextInput(
            label="Question & choix (lecture seule)",
            style=discord.TextStyle.paragraph,
            default=f"{question}\n\nCHOIX :\n{txt_options}",
            required=False
        )
        self.info.disabled = True
        self.add_item(self.info)

        self.reponses = discord.ui.TextInput(
            label="Tes réponses (ex : A,C,D ou A C D ou ACD)",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.add_item(self.reponses)

    def parse_answers(self, raw):
        s = raw.upper()
        result = set()
        for ch in s:
            if ch in self.valid_letters:
                result.add(ch)
        return sorted(result)

    async def on_submit(self, interaction):
        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            return await interaction.response.send_message("❌ Quiz terminé.", ephemeral=True)

        uid = str(interaction.user.id)
        if interaction.user.id in quiz["answers"]:
            return await interaction.response.send_message("❌ Tu as déjà répondu.", ephemeral=True)

        selected = self.parse_answers(self.reponses.value)
        if not selected:
            return await interaction.response.send_message("❌ Réponse invalide.", ephemeral=True)

        quiz["answers"][interaction.user.id] = selected

        correct = quiz["correct"]
        pts = quiz["points"]

        bonnes = sum(1 for r in selected if r in correct)
        mauvaises = sum(1 for r in selected if r not in correct)
        gained = (bonnes * pts) - (mauvaises * 0.5)

        old_points = scores["all_time"].get(uid, {"points": 0})["points"]
        old_rank = get_rank(old_points)

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

        print(f"[VOTE] {interaction.user} → {selected} | +{gained}")

        await interaction.response.send_message(
            f"✅ Réponse enregistrée : {', '.join(selected)}",
            ephemeral=True
        )

# =====================================================================
# BOUTON RÉPONDRE
# =====================================================================

class AnswerButton(discord.ui.Button):
    def __init__(self, quiz_id):
        super().__init__(
            label="Répondre",
            style=discord.ButtonStyle.primary,
            custom_id=f"answer_{quiz_id}"
        )
        self.quiz_id = quiz_id

    async def callback(self, interaction):
        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            return await interaction.response.send_message("❌ Quiz expiré.", ephemeral=True)

        q = quiz["question"]
        opts = quiz["options"]
        valid = [l for l, _ in opts]

        modal = AnswerModal(self.quiz_id, q, opts, valid)
        await interaction.response.send_modal(modal)

class QuizView(discord.ui.View):
    def __init__(self, quiz_id):
        super().__init__(timeout=None)
        self.add_item(AnswerButton(quiz_id))

# =====================================================================
# /QUIZ2
# =====================================================================

@bot.tree.command(name="quiz2", description="Créer un quiz multi-choix (modal)")
@app_commands.describe(
    quiz_id="ID unique du quiz",
    question="La question",
    choix="Choix séparés par |",
    bonne_reponse="Lettres correctes (ex : A,C)",
    points="Points par bonne réponse"
)
async def quiz2(interaction, quiz_id: str, question: str, choix: str, bonne_reponse: str, points: int):

    if quiz_id in quizzes:
        return await interaction.response.send_message("❌ Cet ID existe déjà.", ephemeral=True)

    raw = [convert_combo_to_emojis(c.strip()) for c in choix.split("|")]
    letters = [chr(ord("A") + i) for i in range(len(raw))]
    options = list(zip(letters, raw))
    correct = [x.strip().upper() for x in bonne_reponse.split(",")]

    quizzes[quiz_id] = {
        "question": question,
        "options": options,
        "correct": correct,
        "points": points,
        "answers": {},
        "rankups": {},
        "author_id": interaction.user.id
    }

    embed = discord.Embed(
        title=f"🧠 Quiz `{quiz_id}`",
        description=f"{question}\n\n**{points} pt / bonne réponse, -0.5 / mauvaise**",
        color=0x00B0F4
    )
    for l, t in options:
        embed.add_field(name=l, value=t, inline=False)

    view = QuizView(quiz_id)
    bot.add_view(view)

    await interaction.response.send_message(embed=embed, view=view)

# =====================================================================
# /REVEAL
# =====================================================================

@bot.tree.command(name="reveal", description="Révèle un quiz")
@app_commands.describe(quiz_id="ID du quiz à révéler")
async def reveal(interaction, quiz_id: str):

    quiz = quizzes.get(quiz_id)
    if not quiz:
        return await interaction.response.send_message("❌ ID invalide.", ephemeral=True)

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

    opt_lines = "\n".join(
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

    rank_text = []
    for uid_str, new_rank in quiz["rankups"].items():
        user = await bot.fetch_user(int(uid_str))
        member = interaction.guild.get_member(int(uid_str))
        old_pts = scores["all_time"][uid_str]["points"]
        old_rank = get_rank(old_pts - 0.0001)
        if member:
            await update_user_rank_role(member, old_rank, new_rank)
        rank_text.append(f"🔥 {user.name} → {new_rank}")
    rank_text = "\n".join(rank_text) or "Aucun."

    await interaction.response.send_message(
        f"### 🧠 Quiz `{quiz_id}`\n"
        f"❓ {q}\n\n"
        f"{opt_lines}\n\n"
        f"### 🏅 Points :\n{pts_text}\n\n"
        f"### 🎖 Rank-ups :\n{rank_text}"
    )

    del quizzes[quiz_id]

# =====================================================================
# /VOTES (privé)
# =====================================================================

@bot.tree.command(name="votes", description="Voir qui a répondu (auteur uniquement)")
@app_commands.describe(quiz_id="ID du quiz")
async def votes(interaction, quiz_id: str):

    quiz = quizzes.get(quiz_id)
    if not quiz:
        return await interaction.response.send_message("❌ Quiz introuvable.", ephemeral=True)

    if quiz["author_id"] != interaction.user.id:
        return await interaction.response.send_message("❌ Tu n'es pas l'auteur.", ephemeral=True)

    answers = quiz["answers"]
    if not answers:
        return await interaction.response.send_message("Personne n'a répondu.", ephemeral=True)

    lines = []
    for uid_int, rep in answers.items():
        user = await bot.fetch_user(uid_int)
        lines.append(f"**{user.name}** : {', '.join(rep)}")

    await interaction.response.send_message(
        "👀 **Votes enregistrés :**\n" + "\n".join(lines),
        ephemeral=True
    )

# =====================================================================
# /REVEAL_ALL
# =====================================================================

@bot.tree.command(name="reveal_all", description="Révèle tous les quiz actifs")
async def reveal_all(interaction):

    if not quizzes:
        return await interaction.response.send_message("❌ Aucun quiz actif.", ephemeral=True)

    blocks = []

    for qid, quiz in list(quizzes.items()):
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

        opt_txt = "\n".join(
            f"{'✅' if l in correct else '❌'} **{l}** — {t} ({counts[l]} votes)"
            for l, t in options
        )

        pts_txt = ""
        for uid_int, rep in answers.items():
            bonnes = sum(1 for r in rep if r in correct)
            mauvaises = sum(1 for r in rep if r not in correct)
            gained = (bonnes * p) - (mauvaises * 0.5)
            user = await bot.fetch_user(uid_int)
            pts_txt += f"{user.name} : {gained:.1f} pts\n"

        blocks.append(
            f"## 🔹 Quiz `{qid}`\n"
            f"❓ {q}\n"
            f"{opt_txt}\n\n"
            f"🏅 Points :\n{pts_txt or 'Personne.'}\n---"
        )

        del quizzes[qid]

    await interaction.response.send_message("\n".join(blocks))

# =====================================================================
# /MYRANK
# =====================================================================

@bot.tree.command(name="myrank", description="Voir ton rang")
async def myrank(interaction):
    uid = str(interaction.user.id)

    if uid not in scores["all_time"]:
        return await interaction.response.send_message("Tu n'as pas encore de score.", ephemeral=True)

    data = scores["all_time"][uid]
    pts = data["points"]
    rank = get_rank(pts)
    nxt_thr, nxt_rank, diff = get_next_rank_info(pts)

    emb = discord.Embed(title=f"🎖 {interaction.user.name}", color=0xFFD700)
    emb.add_field(name="Rang", value=rank, inline=False)
    emb.add_field(name="Points", value=f"{pts:.1f}")
    emb.add_field(name="Questions", value=data["questions"])

    if nxt_rank:
        emb.add_field(name="Prochain rang", value=nxt_rank, inline=False)
        emb.add_field(name="Manque", value=f"{diff:.1f} pts")

    await interaction.response.send_message(embed=emb)

# =====================================================================
# /LEADERBOARD
# =====================================================================

@bot.tree.command(name="leaderboard", description="Classement complet")
async def leaderboard(interaction):

    if not scores["all_time"]:
        return await interaction.response.send_message("Aucun score.", ephemeral=True)

    emb = discord.Embed(title="🏆 Leaderboard Poker", color=0xFFD700)

    ordered_all = sorted(scores["all_time"].items(), key=lambda x: x[1]["points"], reverse=True)
    txt_all = ""
    for i, (uid_str, data) in enumerate(ordered_all, 1):
        user = await bot.fetch_user(int(uid_str))
        r = get_rank(data["points"])
        txt_all += f"**{i}. {user.name}** — {data['points']:.1f} pts | {r}\n"
    emb.add_field(name="🔥 ALL-TIME", value=txt_all or "Personne.", inline=False)

    ordered_m = sorted(scores["monthly"].items(), key=lambda x: x[1]["points"], reverse=True)
    txt_m = ""
    for i, (uid_str, data) in enumerate(ordered_m, 1):
        user = await bot.fetch_user(int(uid_str))
        r = get_rank(data["points"])
        txt_m += f"**{i}. {user.name}** — {data['points']:.1f} pts | {r}\n"
    emb.add_field(name="📅 CE MOIS-CI", value=txt_m or "Personne.", inline=False)

    await interaction.response.send_message(embed=emb)

# =====================================================================
# /RESET_SCORES
# =====================================================================

@bot.tree.command(name="reset_scores", description="Reset scores (admin)")
async def reset_scores(interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    scores["all_time"] = {}
    scores["monthly"] = {}
    save_scores()

    await interaction.response.send_message("Scores reset.")

# =====================================================================
# /SYNC_ROLES
# =====================================================================

@bot.tree.command(name="sync_roles", description="Créer les rôles ABI (admin)")
async def sync_roles(interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    guild = interaction.guild
    created = []

    for rank, color in RANK_COLORS.items():
        if not discord.utils.get(guild.roles, name=rank):
            await guild.create_role(
                name=rank,
                colour=discord.Color(color),
                mentionable=True
            )
            created.append(rank)

    if created:
        await interaction.response.send_message("Rôles créés :\n" + "\n".join(created))
    else:
        await interaction.response.send_message("Tous les rôles existent déjà.")

# =====================================================================
# /force_sync
# =====================================================================

@bot.tree.command(name="force_sync", description="Forcer la sync (debug)")
async def force_sync(interaction):
    guild = discord.Object(id=GUILD_ID)
    cmds = await bot.tree.sync(guild=guild)
    names = [c.name for c in cmds]
    await interaction.response.send_message(
        f"Commandes synchronisées : {names}",
        ephemeral=True
    )

# =====================================================================
# ON_READY
# =====================================================================

@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")
    guild = discord.Object(id=GUILD_ID)
    cmds = await bot.tree.sync(guild=guild)
    print("Commandes sync :", [c.name for c in cmds])

# =====================================================================
# RUN BOT
# =====================================================================

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ BOT_TOKEN manquant dans Railway")
else:
    bot.run(TOKEN)
