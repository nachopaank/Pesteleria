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
        # Solo actualizar a activo si estaba inactivo, no sobrescribir a muerto
        if nombre in partidas[codigo]["jugadores"]:
            if partidas[codigo]["jugadores"][nombre] == "inactivo":
                partidas[codigo]["jugadores"][nombre] = "activo"
        emit("jugadores", partidas[codigo]["jugadores"], to=codigo)
        emit("roles_descartados", partidas[codigo]["roles_descartados"], to=codigo)

@socketio.on("unirse_con_foto")
def unirse_con_foto(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    foto = data["foto"]
    join_room(codigo)
    if codigo in partidas:
        if nombre in partidas[codigo]["jugadores"]:
            # No revivir a jugadores muertos
            if partidas[codigo]["jugadores"][nombre] == "inactivo":
                partidas[codigo]["jugadores"][nombre] = "activo"
        else:
            partidas[codigo]["jugadores"][nombre] = "activo"
            partidas[codigo]["fotos"][nombre] = foto
    emit("jugadores", partidas[codigo]["jugadores"], to=codigo)
    emit("roles_descartados", partidas[codigo]["roles_descartados"], to=codigo)

@socketio.on("set_status")
def set_status(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    status = "activo" if data["status"] else "inactivo"
    if nombre in partidas[codigo]["jugadores"]:
        # No cambiar a activo si estaba muerto
        if partidas[codigo]["jugadores"][nombre] != "muerto":
            partidas[codigo]["jugadores"][nombre] = status
        emit("jugadores", partidas[codigo]["jugadores"], to=codigo)

# -----------------------------------
# DESCARTAR ROLES
# -----------------------------------
@socketio.on("asignar_roles")
def asignar_roles(data):
    codigo = data["codigo"]
    roles = ["demonio","rey","adivina","monja","guerrero","tonto del pueblo","bruja",
             "jacob","ramera","cazador","boticario","celestina","asesino",
             "doctor peste","hijo del doctor"]
    n_descartes = random.randint(5, len(roles)-1)
    descartados = random.sample(roles, n_descartes)
    partidas[codigo]["roles_descartados"] = descartados
    emit("roles_descartados", descartados, to=codigo)

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
    host = data["host"]
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
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)

