import discord
from discord.ext import commands
from discord.ui import View, Button
import sqlite3
import os
from datetime import datetime

# ================== CONFIGURACIÓN ==================

CANAL_TURNOS = 1472964421201428571
ID_DIRECTOR = 1381740630291775519
ID_ADMIN = 1381740760717852702
ID_MEDICO = 1471976001767473212
ID_ENFERMERO = 1472663349174206751

# ===================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================== BASE DE DATOS ==================

conn = sqlite3.connect("hospital.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS departamentos (
    nombre TEXT PRIMARY KEY
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS medicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    departamento TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS turnos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT,
    departamento TEXT,
    descripcion TEXT,
    estado TEXT,
    medico_asignado TEXT,
    fecha TEXT
)
""")

conn.commit()

# ================== SISTEMA DE PERMISOS ==================

def tiene_permiso(usuario, nivel):
    roles_usuario = [r.id for r in usuario.roles]

    jerarquia = {
        "director": [1381740630291775519], 
        "admin": [1381740630291775519,1381740760717852702],
        "medico": [1381740630291775519,1381740760717852702,1471976001767473212],
        "enfermero": [1381740630291775519,1381740760717852702,1471976001767473212,1472663349174206751]
    }

    return any(r in roles_usuario for r in jerarquia[nivel])

# ================== EVENTO READY ==================

@bot.event
async def on_ready():
    print(f"Sistema hospitalario activo como {bot.user}")

# ================== CREAR DEPARTAMENTO ==================

@bot.command()
async def crear_departamento(ctx, *, nombre):
    if not tiene_permiso(ctx.author, "director"):
        return await ctx.send("❌ Solo Director puede crear departamentos.")

    cursor.execute("INSERT OR IGNORE INTO departamentos (nombre) VALUES (?)", (nombre,))
    conn.commit()
    await ctx.send(f"✅ Departamento '{nombre}' creado.")

# ================== CREAR MÉDICO ==================

@bot.command()
async def crear_medico(ctx, nombre, *, departamento):
    if not tiene_permiso(ctx.author, "admin"):
        return await ctx.send("❌ Permiso insuficiente.")

    cursor.execute("INSERT INTO medicos (nombre, departamento) VALUES (?, ?)", (nombre, departamento))
    conn.commit()
    await ctx.send(f"✅ Médico '{nombre}' agregado a {departamento}.")

# ================== SOLICITAR TURNO ==================

@bot.command()
async def solicitar_turno(ctx, departamento, *, descripcion):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("""
        INSERT INTO turnos (usuario, departamento, descripcion, estado, medico_asignado, fecha)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (str(ctx.author), departamento, descripcion, "Pendiente", "No asignado", fecha))

    conn.commit()
    turno_id = cursor.lastrowid

    canal = bot.get_channel(CANAL_TURNOS)

    embed = discord.Embed(
        title=f"Turno #{turno_id}",
        description=f"Paciente: {ctx.author}\nDepartamento: {departamento}\nMotivo: {descripcion}\nEstado: Pendiente",
        color=discord.Color.blue()
    )

    view = PanelTurno(turno_id)

    await canal.send(embed=embed, view=view)
    await ctx.send("✅ Turno enviado correctamente.")

# ================== PANEL DE BOTONES ==================

class PanelTurno(View):
    def __init__(self, turno_id):
        super().__init__(timeout=None)
        self.turno_id = turno_id

    @discord.ui.button(label="Aprobar", style=discord.ButtonStyle.green)
    async def aprobar(self, interaction: discord.Interaction, button: Button):
        if not tiene_permiso(interaction.user, "admin"):
            return await interaction.response.send_message("❌ No tienes permiso.", ephemeral=True)

        cursor.execute("UPDATE turnos SET estado=? WHERE id=?", ("Aprobado", self.turno_id))
        conn.commit()
        await interaction.response.send_message(f"✅ Turno #{self.turno_id} aprobado.")

    @discord.ui.button(label="Asignar Médico", style=discord.ButtonStyle.blurple)
    async def asignar(self, interaction: discord.Interaction, button: Button):
        if not tiene_permiso(interaction.user, "admin"):
            return await interaction.response.send_message("❌ No tienes permiso.", ephemeral=True)

        cursor.execute("SELECT nombre FROM medicos LIMIT 1")
        medico = cursor.fetchone()

        if not medico:
            return await interaction.response.send_message("⚠️ No hay médicos registrados.")

        cursor.execute("UPDATE turnos SET medico_asignado=?, estado=? WHERE id=?",
                       (medico[0], "Asignado", self.turno_id))
        conn.commit()

        await interaction.response.send_message(f"👨‍⚕️ Médico {medico[0]} asignado al turno #{self.turno_id}.")

    @discord.ui.button(label="Finalizar", style=discord.ButtonStyle.red)
    async def finalizar(self, interaction: discord.Interaction, button: Button):
        if not tiene_permiso(interaction.user, "medico"):
            return await interaction.response.send_message("❌ Solo médicos pueden finalizar.", ephemeral=True)

        cursor.execute("UPDATE turnos SET estado=? WHERE id=?", ("Finalizado", self.turno_id))
        conn.commit()
        await interaction.response.send_message(f"🏁 Turno #{self.turno_id} finalizado.")

# ================== ESTADÍSTICAS ==================

@bot.command()
async def estadisticas(ctx):
    if not tiene_permiso(ctx.author, "admin"):
        return await ctx.send("❌ Permiso insuficiente.")

    cursor.execute("SELECT COUNT(*) FROM turnos")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM turnos WHERE estado='Pendiente'")
    pendientes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM turnos WHERE estado='Finalizado'")
    finalizados = cursor.fetchone()[0]

    embed = discord.Embed(title="📊 Estadísticas Hospitalarias", color=discord.Color.gold())
    embed.add_field(name="Total turnos", value=total)
    embed.add_field(name="Pendientes", value=pendientes)
    embed.add_field(name="Finalizados", value=finalizados)

    await ctx.send(embed=embed)

# ================== EJECUCIÓN ==================

bot.run(os.getenv("TOKEN"))
