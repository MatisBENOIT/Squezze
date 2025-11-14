import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime

# -------------------- CONFIG --------------------
GUILD_ID = 1309118091766009856
SCORES_FILE = "scores.json"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

print(">>> FICHIER ACTUEL CHARGÉ <<<")

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

# -------------------- UI (PERSISTANTE) --------------------
class QuizSelect(discord.ui.Select):
    def __init__(self, quiz_id, options):
        self.quiz_id = quiz_id

        super().__init__(
            custom_id=f"select_{quiz_id}",
            placeholder="Réponses",
            min_values=1,
            max_values=len(options),
            options=[
                discord.SelectOption(label=f"{l} — {t}", value=l)
                for l, t in options
            ]
        )

    async def callback(self, interaction):
        quiz = quizzes.get(self.quiz_id)
        if not quiz:
            await interaction.response.send_message("❌ Quiz terminé.", ephemeral=True)
            return

        quiz["answers_temp"][interaction.user.id] = self.values
        await interaction.response.defer()

class ValidateButton(discord.ui.Button):
    def __init__(self, quiz_id):
        super().__init__(
            label="Valider",
            style=discord.ButtonStyle.success,
            custom_id=f"validate_{quiz_id}"
        )
        self.quiz_id = quiz_id

    async def callback(self, interaction):
        await interaction.response.send_message("⏳ Traitement…", ephemeral=True)
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
        p = quiz["points"]

        bonnes = sum(1 for r in selected if r in correct)
        mauvaises = sum(1 for r in selected if r not in correct)

        gained = (bonnes * p) - (mauvaises * 0.5)

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

        await interaction.followup.send("✅ Réponse enregistrée !", ephemeral=True)

class QuizView(discord.ui.View):
    def __init__(self, quiz_id, options):
        super().__init__(timeout=None)
        self.add_item(QuizSelect(quiz_id, options))
        self.add_item(ValidateButton(quiz_id))

# -------------------- /QUIZ2 --------------------
@bot.tree.command(name="quiz2", description="Créer un quiz multi-choix")
async def quiz2(interaction, quiz_id: str, question: str, choix: str, bonne_reponse: str, points: int):

    if quiz_id in quizzes:
        await interaction.response.send_message("❌ Cet ID existe déjà.", ephemeral=True)
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
        "author_id": interaction.user.id
    }

    embed = discord.Embed(
        title=f"🧠 Quiz `{quiz_id}`",
        description=f"{question}\n\n**{points} pt / bonne réponse, -0.5 / mauvaise**",
        color=0x00B0F4
    )
    for l, t in opts:
        embed.add_field(name=l, value=t, inline=False)

    view = QuizView(quiz_id, opts)
    bot.add_view(view)

    await interaction.response.send_message(embed=embed, view=view)

# -------------------- /REVEAL --------------------
@bot.tree.command(name="reveal", description="Révèle un quiz")
async def reveal(interaction, quiz_id: str):

    quiz = quizzes.get(quiz_id)
    if not quiz:
        await interaction.response.send_message("❌ Quiz introuvable.", ephemeral=True)
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
    for uid, rep in answers.items():
        bonnes = sum(1 for r in rep if r in correct)
        mauvaises = sum(1 for r in rep if r not in correct)
        gained = (bonnes * p) - (mauvaises * 0.5)
        user = await bot.fetch_user(uid)
        pts_lines.append(f"**{user.name}** : {gained:.1f} pts")

    pts_text = "\n".join(pts_lines) or "Personne."

    rank_lines = []
    for uid, new_rank in quiz["rankups"].items():
        user = await bot.fetch_user(uid)
        member = interaction.guild.get_member(int(uid))

        old_pts = scores["all_time"][uid]["points"]
        old_rank = get_rank(old_pts - 0.0001)

        if member:
            await update_user_rank_role(member, old_rank, new_rank)

        rank_lines.append(f"🔥 {user.name} → {new_rank}")

    rank_text = "\n".join(rank_lines) or "Aucun."

    await interaction.response.send_message(
        f"### 🧠 Quiz `{quiz_id}`\n"
        f"❓ {q}\n\n"
        f"🃏 Bonnes réponses : {', '.join(correct)}\n"
        f"📌 {p} pt / bonne, -0.5 / mauvaise\n\n"
        f"{opt_text}\n\n"
        f"### 🏅 Points :\n{pts_text}\n\n"
        f"### 🎖 Rank-ups :\n{rank_text}"
    )

    del quizzes[quiz_id]

# -------------------- /VOTES --------------------
@bot.tree.command(name="votes", description="Voir en privé qui a voté quoi (uniquement pour l'auteur du quiz)")
async def votes(interaction: discord.Interaction, quiz_id: str):

    quiz = quizzes.get(quiz_id)
    if not quiz:
        await interaction.response.send_message("❌ Aucun quiz trouvé avec cet ID.", ephemeral=True)
        return

    if quiz["author_id"] != interaction.user.id:
        await interaction.response.send_message("❌ Tu n'es pas l'auteur de ce quiz.", ephemeral=True)
        return

    answers = quiz["answers"]
    if not answers:
        await interaction.response.send_message("Personne n'a encore répondu.", ephemeral=True)
        return

    lines = []
    for uid, rep in sorted(answers.items()):
        user = await bot.fetch_user(uid)
        lines.append(f"**{user.name}** : {', '.join(rep)}")

    await interaction.response.send_message(
        "👀 **Votes enregistrés :**\n\n" + "\n".join(lines),
        ephemeral=True
    )

# -------------------- /REVEAL_ALL --------------------
@bot.tree.command(name="reveal_all", description="Révèle tous les quiz")
async def reveal_all(interaction):

    if not quizzes:
        await interaction.response.send_message("❌ Aucun quiz actif.", ephemeral=True)
        return

    blocks = []

    for quiz_id, quiz in list(quizzes.items()):
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

        pts = []
        for uid, rep in answers.items():
            bonnes = sum(1 for r in rep if r in correct)
            mauvaises = sum(1 for r in rep if r not in correct)
            gained = (bonnes * p) - (mauvaises * 0.5)
            user = await bot.fetch_user(uid)
            pts.append(f"{user.name} : {gained:.1f} pts")
        pts_text = "\n".join(pts) or "Personne."

        ru = []
        for uid, new_rank in quiz["rankups"].items():
            user = await bot.fetch_user(uid)
            member = interaction.guild.get_member(int(uid))
            old_pts = scores["all_time"][uid]["points"]
            old_rank = get_rank(old_pts - 0.0001)

            if member:
                await update_user_rank_role(member, old_rank, new_rank)

            ru.append(f"{user.name} → {new_rank}")

        rank_text = "\n".join(ru) or "Aucun."

        blocks.append(
            f"## 🔹 Quiz `{quiz_id}`\n"
            f"❓ {q}\n"
            f"🃏 Bonnes réponses : {', '.join(correct)}\n"
            f"{opt_text}\n\n"
            f"### 🏅 Points :\n{pts_text}\n\n"
            f"### 🎖 Rank-ups :\n{rank_text}\n---"
        )

        del quizzes[quiz_id]

    await interaction.response.send_message("\n\n".join(blocks))

# -------------------- /MYRANK --------------------
@bot.tree.command(name="myrank", description="Voir ton rang")
async def myrank(interaction):
    uid = str(interaction.user.id)

    if uid not in scores["all_time"]:
        await interaction.response.send_message("Aucun score.", ephemeral=True)
        return

    pts = scores["all_time"][uid]["points"]
    r = get_rank(pts)
    nxt_thr, nxt_rank, diff = get_next_rank_info(pts)

    emb = discord.Embed(title=f"🎖 {interaction.user.name}", color=0xFFD700)
    emb.add_field(name="Rang", value=r, inline=False)
    emb.add_field(name="Points", value=f"{pts:.1f}", inline=True)
    emb.add_field(name="Questions", value=scores["all_time"][uid]["questions"], inline=True)

    if nxt_rank:
        emb.add_field(name="Prochain rang", value=nxt_rank, inline=False)
        emb.add_field(name="Manque", value=f"{diff:.1f} pts", inline=True)

    await interaction.response.send_message(embed=emb)

# -------------------- /RESET_SCORES --------------------
@bot.tree.command(name="reset_scores", description="Reset scores (admin only)")
async def reset_scores(interaction):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    scores["all_time"] = {}
    scores["monthly"] = {}
    save_scores()

    await interaction.response.send_message("Scores reset.")

# -------------------- /SYNC_ROLES --------------------
@bot.tree.command(name="sync_roles", description="Créer tous les rôles ABI")
async def sync_roles(interaction):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

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
        await interaction.followup.send(
            "Rôles créés :\n" + "\n".join(created),
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "Tous les rôles existent déjà.",
            ephemeral=True
        )

# -------------------- /LEADERBOARD --------------------
@bot.tree.command(name="leaderboard", description="Voir le classement")
async def leaderboard(interaction):

    if not scores["all_time"]:
        await interaction.response.send_message("Aucun score.", ephemeral=True)
        return

    emb = discord.Embed(title="🏆 Leaderboard", color=0xFFD700)

    # All-time
    ordered = sorted(scores["all_time"].items(), key=lambda x: x[1]["points"], reverse=True)
    txt = ""
    for i, (uid, data) in enumerate(ordered, 1):
        user = await bot.fetch_user(uid)
        r = get_rank(data["points"])
        txt += f"**{i}. {user.name}** — {data['points']:.1f} pts | {r}\n"

    emb.add_field(name="🔥 ALL-TIME", value=txt or "Personne.", inline=False)

    # Monthly
    ord_m = sorted(scores["monthly"].items(), key=lambda x: x[1]["points"], reverse=True)
    txt2 = ""
    for i, (uid, data) in enumerate(ord_m, 1):
        user = await bot.fetch_user(uid)
        r = get_rank(data["points"])
        txt2 += f"**{i}. {user.name}** — {data['points']:.1f} pts | {r}\n"

    emb.add_field(name="📅 CE MOIS-CI", value=txt2 or "Personne.", inline=False)

    await interaction.response.send_message(embed=emb)

# -------------------- /DEBUG_COMMANDS --------------------
@bot.tree.command(name="debug_commands", description="Voir les commandes chargées")
async def debug_commands(interaction: discord.Interaction):
    cmds = bot.tree.get_commands()
    names = [c.name for c in cmds]
    await interaction.response.send_message(
        "Commandes chargées par le bot :\n" + "\n".join(names),
        ephemeral=True
    )

# -------------------- /FORCE_SYNC --------------------
@bot.tree.command(name="force_sync", description="Forcer la synchronisation des commandes (debug)")
async def force_sync(interaction: discord.Interaction):
    guild = discord.Object(id=GUILD_ID)
    cmds = await bot.tree.sync(guild=guild)
    names = [c.name for c in cmds]
    await interaction.response.send_message(
        f"🔄 Sync forcée : {names}",
        ephemeral=True
    )
    
print(">>> COMMANDES CHARGÉES PAR PYTHON :", len(bot.tree.get_commands()))
for cmd in bot.tree.get_commands():
    print(" -", cmd.name)

# -------------------- ON READY --------------------
@bot.event
async def on_ready():
    print("Bot connecté :", bot.user)

    guild = discord.Object(id=GUILD_ID)

    # 🔥 Sync forcée au démarrage, sans commande
    synced = await bot.tree.sync(guild=guild)

    print("Commandes SYNC au serveur :", [c.name for c in synced])

# -------------------- RUN --------------------
bot.run("BOT_TOKEN")

