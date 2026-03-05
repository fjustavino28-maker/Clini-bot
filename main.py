import discord
from discord.ext import commands, tasks
import sqlite3
from datetime import datetime

# ---------------------------
# Configura aquí los IDs de los roles
# ---------------------------
ROLE_IDS = {
    "presidente": 1476456408122921112,       # Reemplaza con el ID real del rol Presidente
    "director_general": 1472649840583381189,  # Reemplaza con el ID real del rol Director Médico
    "medico": 1471976001767473212,           # Reemplaza con el ID real del rol Médico
}

# ---------------------------
# Comando para asignar rol por ID
# ---------------------------
@bot.command()
async def asignar_rol_id(ctx, miembro: discord.Member, rol: str):
    # Solo presidente puede asignar roles
    if ROLE_IDS[1476456408122921112] not in [r.id for r in ctx.author.roles]:
        await ctx.send("Solo el Presidente puede asignar roles.")
        return

    if rol not in ROLE_IDS:
        await ctx.send("Rol inválido. Usa: presidente, director_general")
        return

    role_obj = ctx.guild.get_role(ROLE_IDS[rol])
    if role_obj in miembro.roles:
        await ctx.send(f"{miembro.name} ya tiene el rol {rol}.")
        return

    await miembro.add_roles(role_obj)
    await ctx.send(f"Rol **{rol}** asignado a {miembro.name}.")

# ---------------------------
# Comando para quitar rol por ID
# ---------------------------
@bot.command()
async def quitar_rol_id(ctx, miembro: discord.Member, rol: str):
    # Solo presidente puede quitar roles
    if ROLE_IDS["presidente"] not in [r.id for r in ctx.author.roles]:
        await ctx.send("Solo el Presidente puede quitar roles.")
        return

    if rol not in ROLE_IDS:
        await ctx.send("Rol inválido. Usa: presidente, director_medico, medico")
        return

    role_obj = ctx.guild.get_role(ROLE_IDS[rol])
    if role_obj not in miembro.roles:
        await ctx.send(f"{miembro.name} no tiene el rol {rol}.")
        return

    await miembro.remove_roles(role_obj)
    await ctx.send(f"Rol **{rol}** quitado a {miembro.name}.")

# ---------------------------
# Comando para listar roles de un miembro
# ---------------------------
@bot.command()
async def mis_roles(ctx, miembro: discord.Member = None):
    miembro = miembro or ctx.author
    roles = [r.name for r in miembro.roles if r.id in ROLE_IDS.values()]
    await ctx.send(f"{miembro.name} tiene los roles: {', '.join(roles) if roles else 'ninguno'}")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------
# Base de datos
# ---------------------------
conn = sqlite3.connect("medbot.db")
c = conn.cursor()

# Tablas
c.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    discord_id INTEGER,
    nombre TEXT,
    rango TEXT DEFAULT 'miembro'
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS licencias (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER,
    tipo TEXT,
    estado TEXT DEFAULT 'pendiente',
    fecha_solicitud TEXT,
    fecha_aprobacion TEXT,
    puntos INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS formularios (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER,
    especialidad TEXT,
    caso TEXT,
    fecha TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS recordatorios (
    id INTEGER PRIMARY KEY,
    descripcion TEXT,
    fecha_evento TEXT
)
""")
conn.commit()

# ---------------------------
# Preguntas para pruebas
# ---------------------------
preguntas_especialidad = {
    "cirugia": [
        {"pregunta": "¿Cuál es la sutura recomendada para piel?", "respuesta": "nylon"},
        {"pregunta": "¿Qué instrumental se usa para apendicectomía?", "respuesta": "bisturi"},
    ],
    "medicina": [
        {"pregunta": "¿Cuál es la dosis estándar de paracetamol para un adulto?", "respuesta": "500mg"},
        {"pregunta": "¿Cuál es el signo de Murphy?", "respuesta": "dolor en hipocondrio derecho"},
    ]
}

# ---------------------------
# Comprobación de presidente
# ---------------------------
def es_presidente():
    async def pred(ctx):
        c.execute("SELECT rango FROM usuarios WHERE discord_id=?", (ctx.author.id,))
        user = c.fetchone()
        return user and user[0].lower() == "presidente"
    return commands.check(pred)

# ---------------------------
# Variables globales para votaciones y pruebas
# ---------------------------
votaciones_activas = {}  # canal_id: {tema: str, votos: {user_id: 'si/no'}, presidente_id}
bot.respuestas_para_presidente = {}  # licencia_id: {'usuario_id', 'especialidad', 'respuestas_usuario', 'respuestas_correctas'}

# ---------------------------
# Eventos
# ---------------------------
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    check_recordatorios.start()

# ---------------------------
# Comandos de usuario
# ---------------------------
@bot.command()
async def nuevo(ctx):
    c.execute("SELECT * FROM usuarios WHERE discord_id = ?", (ctx.author.id,))
    if c.fetchone():
        await ctx.send("Ya estás registrado.")
        return
    c.execute("INSERT INTO usuarios (discord_id, nombre) VALUES (?,?)", (ctx.author.id, ctx.author.name))
    conn.commit()
    await ctx.send(f"{ctx.author.mention} te has registrado correctamente en el sistema médico.")

@bot.command()
async def formulario(ctx, especialidad, *, caso):
    c.execute("SELECT id FROM usuarios WHERE discord_id = ?", (ctx.author.id,))
    user = c.fetchone()
    if not user:
        await ctx.send("Debes registrarte primero con !nuevo")
        return
    user_id = user[0]
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO formularios (usuario_id, especialidad, caso, fecha) VALUES (?,?,?,?)",
              (user_id, especialidad, caso, fecha))
    conn.commit()
    await ctx.send(f"Formulario de {especialidad} registrado correctamente.")

@bot.command()
async def solicitar_licencia(ctx, tipo):
    c.execute("SELECT id FROM usuarios WHERE discord_id = ?", (ctx.author.id,))
    user = c.fetchone()
    if not user:
        await ctx.send("Debes registrarte primero con !nuevo")
        return
    user_id = user[0]
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO licencias (usuario_id, tipo, fecha_solicitud) VALUES (?,?,?)",
              (user_id, tipo, fecha))
    conn.commit()
    await ctx.send(f"Licencia de {tipo} solicitada, pendiente de aprobación.")

@bot.command()
async def estado_licencia(ctx, tipo):
    c.execute("""
    SELECT estado, puntos FROM licencias 
    JOIN usuarios ON licencias.usuario_id = usuarios.id
    WHERE usuarios.discord_id=? AND tipo=?
    ORDER BY licencias.id DESC LIMIT 1
    """, (ctx.author.id, tipo))
    result = c.fetchone()
    if result:
        estado, puntos = result
        await ctx.send(f"Estado de la licencia de {tipo}: {estado}, Puntos: {puntos if puntos else 'N/A'}")
    else:
        await ctx.send(f"No tienes licencias de {tipo} registradas.")

# ---------------------------
# Prueba de especialidad con respuestas correctas registradas
# ---------------------------
@bot.command()
async def prueba(ctx, especialidad):
    especialidad = especialidad.lower()
    if especialidad not in preguntas_especialidad:
        await ctx.send("Especialidad no disponible para pruebas.")
        return

    c.execute("SELECT id FROM usuarios WHERE discord_id = ?", (ctx.author.id,))
    user = c.fetchone()
    if not user:
        await ctx.send("Debes registrarte primero con !nuevo")
        return
    user_id = user[0]

    await ctx.send(f"Comenzando prueba de especialidad en **{especialidad}**. Responde cada pregunta en un mensaje.")

    respuestas_usuario = []
    respuestas_correctas = [q['respuesta'] for q in preguntas_especialidad[especialidad]]

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    for q in preguntas_especialidad[especialidad]:
        await ctx.send(q["pregunta"])
        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            respuestas_usuario.append(msg.content.lower().strip())
        except:
            respuestas_usuario.append(None)
            await ctx.send("Tiempo agotado para esta pregunta.")

    # Guardar respuestas y estado pendiente
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO licencias (usuario_id, tipo, estado, fecha_solicitud) VALUES (?,?,?,?)",
              (user_id, especialidad, "pendiente", fecha))
    licencia_id = c.lastrowid
    conn.commit()

    # Mostrar resumen al participante
    resumen = ""
    for idx, resp in enumerate(respuestas_usuario):
        correcta = respuestas_correctas[idx]
        estado = "✅" if resp == correcta else "❌"
        resumen += f"Pregunta {idx+1}: tu respuesta: `{resp}` | correcta: `{correcta}` {estado}\n"
    await ctx.send(f"Prueba finalizada. Todas las respuestas se registraron como pendientes.\n\n**Resumen:**\n{resumen}\nEl presidente revisará tus respuestas y asignará los puntos (máx 100).")

    # Guardar respuestas en memoria para el presidente
    bot.respuestas_para_presidente[licencia_id] = {
        'usuario_id': user_id,
        'especialidad': especialidad,
        'respuestas_usuario': respuestas_usuario,
        'respuestas_correctas': respuestas_correctas
    }

# ---------------------------
# Comandos del presidente para aprobar, rechazar y asignar puntos
# ---------------------------
@bot.command()
@es_presidente()
async def aprobar(ctx, usuario_id: int, tipo):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("UPDATE licencias SET estado='aprobado', fecha_aprobacion=? WHERE usuario_id=? AND tipo=? ORDER BY id DESC LIMIT 1",
              (fecha, usuario_id, tipo))
    conn.commit()
    # Asignar rol automáticamente
    guild = ctx.guild
    member = guild.get_member(usuario_id)
    if member:
        role = discord.utils.get(guild.roles, name=tipo.capitalize())
        if role is None:
            role = await guild.create_role(name=tipo.capitalize())
        await member.add_roles(role)
        await ctx.send(f"Licencia de {tipo} aprobada y rol **{role.name}** asignado a {member.name}.")

@bot.command()
@es_presidente()
async def rechazar(ctx, usuario_id: int, tipo):
    c.execute("UPDATE licencias SET estado='rechazado' WHERE usuario_id=? AND tipo=? ORDER BY id DESC LIMIT 1",
              (usuario_id, tipo))
    conn.commit()
    await ctx.send(f"Licencia de {tipo} rechazada para el usuario {usuario_id}.")

@bot.command()
@es_presidente()
async def asignar_puntos(ctx, licencia_id: int, puntos: int):
    if puntos < 0 or puntos > 100:
        await ctx.send("Los puntos deben estar entre 0 y 100.")
        return

    if licencia_id not in bot.respuestas_para_presidente:
        await ctx.send("Licencia o prueba no encontrada.")
        return

    data = bot.respuestas_para_presidente[licencia_id]
    usuario_id = data['usuario_id']
    especialidad = data['especialidad']

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("UPDATE licencias SET estado='aprobado', fecha_aprobacion=?, puntos=? WHERE id=?",
              (fecha, puntos, licencia_id))
    conn.commit()

    # Asignar rol automáticamente
    guild = ctx.guild
    member = guild.get_member(usuario_id)
    if member:
        role = discord.utils.get(guild.roles, name=especialidad.capitalize())
        if role is None:
            role = await guild.create_role(name=especialidad.capitalize())
        await member.add_roles(role)
        await ctx.send(f"Puntos asignados: {puntos}/100. Licencia de {especialidad} aprobada y rol **{role.name}** asignado a {member.name}.")

    del bot.respuestas_para_presidente[licencia_id]

# ---------------------------
# Juntas y votaciones
# ---------------------------
@bot.command()
@es_presidente()
async def junta(ctx, *, tema):
    canal = ctx.channel
    votaciones_activas[canal.id] = {'tema': tema, 'votos': {}, 'presidente_id': ctx.author.id}
    await ctx.send(f"Se convoca una **junta** sobre: {tema}\nUsa `!votacion si` o `!votacion no` para participar.")

@bot.command()
async def votacion(ctx, opcion):
    canal = ctx.channel.id
    if canal not in votaciones_activas:
        await ctx.send("No hay votación activa en este canal.")
        return
    voto = opcion.lower()
    if voto not in ['si', 'no']:
        await ctx.send("Opción inválida, usa `si` o `no`.")
        return
    votaciones_activas[canal]['votos'][ctx.author.id] = voto
    await ctx.send(f"{ctx.author.name} votó {voto}")

    votos = votaciones_activas[canal]['votos']
    si = sum(1 for v in votos.values() if v=='si')
    no = sum(1 for v in votos.values() if v=='no')
    total = len(votos)
    presidente_id = votaciones_activas[canal]['presidente_id']

    if total >= 3:  # mínimo 3 votos para cerrar
        ganador = votos[presidente_id] if presidente_id in votos else ('si' if si > no else 'no')
        await ctx.send(f"Votación finalizada. Resultado: **{ganador.upper()}**")
        del votaciones_activas[canal]

# ---------------------------
# Recordatorios
# ---------------------------
@bot.command()
async def agregar_recordatorio(ctx, fecha_evento, *, descripcion):
    c.execute("INSERT INTO recordatorios (descripcion, fecha_evento) VALUES (?,?)", (descripcion, fecha_evento))
    conn.commit()
    await ctx.send(f"Recordatorio agregado para {fecha_evento}.")

@tasks.loop(minutes=1)
async def check_recordatorios():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("SELECT id, descripcion FROM recordatorios WHERE fecha_evento=?", (now,))
    eventos = c.fetchall()
    channel = bot.get_channel(INSERTA_TU_CHANNEL_ID_AQUI)  # Cambia por tu canal
    for event in eventos:
        await channel.send(f"Recordatorio: {event[1]}")
        c.execute("DELETE FROM recordatorios WHERE id=?", (event[0],))
    conn.commit()

# ---------------------------
# Ejecutar bot
# ---------------------------
bot.run("TU_TOKEN_AQUI")
