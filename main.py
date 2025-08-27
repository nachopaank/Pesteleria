from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
import random, string, threading, time
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Estructura de partidas
# {codigo: {"jugadores":{nombre:estado}, "fotos":{nombre:url}, "roles_descartados":[], "votacion":None}}
partidas = {}

# -----------------------------------
# RUTAS
# -----------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/nueva")
def nueva():
    codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    partidas[codigo] = {"jugadores": {}, "fotos": {}, "roles_descartados": [], "votacion": None}
    return render_template("nueva.html", codigo=codigo)

@app.route("/unirse_form")
def unirse_form():
    return render_template("unirse.html")

@app.route("/sala/<codigo>/<nombre>")
def sala(codigo, nombre):
    es_host = nombre == "HOST"
    return render_template("sala.html", codigo=codigo, nombre=nombre, es_host=es_host)

# -----------------------------------
# SOCKETS
# -----------------------------------
@socketio.on("join")
def join(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    join_room(codigo)
    if codigo in partidas:
        if nombre in partidas[codigo]["jugadores"]:
            if partidas[codigo]["jugadores"][nombre] == "inactivo":
                partidas[codigo]["jugadores"][nombre] = "activo"
        emit("jugadores", partidas[codigo]["jugadores"], to=codigo)
        emit("roles_descartados", partidas[codigo]["roles_descartados"], to=codigo)
        emit("fotos_jugadores", partidas[codigo]["fotos"], to=codigo)  # <- NUEVO


@socketio.on("unirse_con_foto")
def unirse_con_foto(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    foto = data["foto"]
    join_room(codigo)
    if codigo in partidas:
        if nombre in partidas[codigo]["jugadores"]:
            if partidas[codigo]["jugadores"][nombre] == "inactivo":
                partidas[codigo]["jugadores"][nombre] = "activo"
        else:
            partidas[codigo]["jugadores"][nombre] = "activo"
        partidas[codigo]["fotos"][nombre] = foto  # <- almacenar foto
    emit("jugadores", partidas[codigo]["jugadores"], to=codigo)
    emit("roles_descartados", partidas[codigo]["roles_descartados"], to=codigo)
    emit("fotos_jugadores", partidas[codigo]["fotos"], to=codigo)  # <- enviar fotos


@socketio.on("set_status")
def set_status(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    status = "activo" if data["status"] else "inactivo"
    if nombre in partidas[codigo]["jugadores"]:
        if partidas[codigo]["jugadores"][nombre] != "muerto":
            partidas[codigo]["jugadores"][nombre] = status
        emit("jugadores", partidas[codigo]["jugadores"], to=codigo)

# -----------------------------------
# DESCARTAR ROLES
# -----------------------------------
@socketio.on("asignar_roles")
def asignar_roles(data):
    codigo = data["codigo"]
    if codigo not in partidas:
        return

    jugadores_vivos = [j for j, s in partidas[codigo]["jugadores"].items() if s != "muerto"]
    n_jugadores = len(jugadores_vivos)

    # Roles disponibles
    roles = ["demonio","rey","adivina","monja","guerrero","tonto del pueblo","bruja",
             "jacob","ramera","cazador","boticario","celestina","asesino",
             "doctor peste","hijo del doctor"]

    # Cantidades mínimas de cada tipo según número de jugadores
    # Para simplificar, Buen ciudadano = roles genéricos "buen_ciudadano", Ciudadano = roles genéricos "ciudadano"
    reglas = {
        5: {"buen_ciudadano":2, "ciudadano":2, "doctor":1, "hijo":0},
        6: {"buen_ciudadano":3, "ciudadano":2, "doctor":1, "hijo":0},
        7: {"buen_ciudadano":3, "ciudadano":3, "doctor":1, "hijo":0},
        8: {"buen_ciudadano":3, "ciudadano":3, "doctor":1, "hijo":1},
        9: {"buen_ciudadano":4, "ciudadano":3, "doctor":1, "hijo":1},
        10: {"buen_ciudadano":4, "ciudadano":4, "doctor":1, "hijo":1},
        11: {"buen_ciudadano":4, "ciudadano":4, "doctor":1, "hijo":1},
        12: {"buen_ciudadano":5, "ciudadano":5, "doctor":1, "hijo":1}
    }

    if n_jugadores < 5:  # mínimo para jugar
        emit("roles_descartados", [], to=codigo)
        return

    reglas_n = reglas.get(n_jugadores, reglas[12])

    # Separar roles por tipo
    roles_tipo = {
        "buen_ciudadano": ["demonio","rey","adivina","monja","guerrero","tonto del pueblo","bruja"],
        "ciudadano": ["jacob","ramera","cazador","boticario","celestina","asesino"],
        "doctor": ["doctor peste"],
        "hijo": ["hijo del doctor"]
    }

    descartados = []

    # Descartar Buen ciudadano
    n_buen = len(roles_tipo["buen_ciudadano"]) - reglas_n["buen_ciudadano"]
    descartados += random.sample(roles_tipo["buen_ciudadano"], n_buen)

    # Descartar Ciudadano
    n_ciudadano = len(roles_tipo["ciudadano"]) - reglas_n["ciudadano"]
    descartados += random.sample(roles_tipo["ciudadano"], n_ciudadano)

    # Doctor nunca se descarta

    # Hijo del doctor
    if reglas_n["hijo"] == 0:
        descartados += roles_tipo["hijo"]  # descartar el hijo
    # si reglas_n["hijo"] == 1, no descartar, queda en juego
    no_descartados = [r for r in roles if r not in descartados]

    partidas[codigo]["roles_descartados"] = descartados
    emit("roles_descartados", descartados, to=codigo)
    # Enviar solo al host los roles completos
    host_sid = None
    for sid, session in socketio.server.manager.rooms["/"].items():
        if sid != codigo:  # filtra la sala si es necesario
            continue
    emit("roles_completos", no_descartados, to=data["nombre"])

# -----------------------------------
# MATAR JUGADOR
# -----------------------------------
@socketio.on("matar_jugador")
def matar_jugador(data):
    codigo = data["codigo"]
    jugador = data["jugador"]
    partidas[codigo]["jugadores"][jugador] = "muerto"
    emit("jugadores", partidas[codigo]["jugadores"], to=codigo)

# -----------------------------------
# VOTACION
# -----------------------------------
@socketio.on("iniciar_hoguera")
def iniciar_hoguera(data):
    codigo = data["codigo"]
    tiempo = int(data["tiempo"])
    if partidas[codigo]["votacion"]:
        return
    votacion = {
        "tiempo_restante": tiempo,
        "votos": {},
        "jugadores_vivos": [j for j, s in partidas[codigo]["jugadores"].items() if s != "muerto"],
        "finalizada": False
    }
    partidas[codigo]["votacion"] = votacion
    threading.Thread(target=timer_votacion, args=(codigo,)).start()
    for j in votacion["jugadores_vivos"]:
        emit("votacion_iniciada", {"jugadores": votacion["jugadores_vivos"], "tiempo": tiempo, "ya_voto": j in votacion["votos"]}, room=codigo)

def timer_votacion(codigo):
    while partidas[codigo]["votacion"]["tiempo_restante"] > 0:
        time.sleep(1)
        partidas[codigo]["votacion"]["tiempo_restante"] -= 1
        socketio.emit("votacion_tick", partidas[codigo]["votacion"]["tiempo_restante"], to=codigo)
        if len(partidas[codigo]["votacion"]["votos"]) == len([j for j, s in partidas[codigo]["jugadores"].items() if s != "muerto"]):
            break
    finalizar_votacion(codigo)

def finalizar_votacion(codigo):
    votacion = partidas[codigo]["votacion"]
    if votacion["finalizada"]:
        return
    votacion["finalizada"] = True
    resultados = {}
    for voto in votacion["votos"].values():
        resultados[voto] = resultados.get(voto, 0) + 1
    socketio.emit("votacion_finalizada", resultados, to=codigo)
    partidas[codigo]["votacion"] = None

@socketio.on("votar")
def votar(data):
    codigo = data["codigo"]
    votante = data["votante"]
    voto = data["voto"]
    votacion = partidas[codigo]["votacion"]
    if votacion and votante in votacion["jugadores_vivos"] and votante not in votacion["votos"]:
        votacion["votos"][votante] = voto
        emit("votacion_iniciada", {"jugadores": votacion["jugadores_vivos"], "tiempo": votacion["tiempo_restante"], "ya_voto": True}, room=request.sid)

# -----------------------------------
# RUN
# -----------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
