from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
import random, string, os

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
        emit("jugadores", {
            "jugadores": partidas[codigo]["jugadores"],
            "fotos": partidas[codigo]["fotos"]
        }, to=codigo)

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
            partidas[codigo]["fotos"][nombre] = foto

    # Emitir a todos la lista de jugadores
    emit("jugadores", {
        "jugadores": partidas[codigo]["jugadores"],
        "fotos": partidas[codigo]["fotos"]
    }, to=codigo)

    # Confirmar solo al que se unió
    emit("unido_ok", {"codigo": codigo, "nombre": nombre}, to=request.sid)


@socketio.on("set_status")
def set_status(data):
    codigo = data["codigo"]
    nombre = data["nombre"]
    status = "activo" if data["status"] else "inactivo"
    if nombre in partidas[codigo]["jugadores"]:
        if partidas[codigo]["jugadores"][nombre] != "muerto":
            partidas[codigo]["jugadores"][nombre] = status
        emit("jugadores", {
            "jugadores": partidas[codigo]["jugadores"],
            "fotos": partidas[codigo]["fotos"]
        }, to=codigo)

# -----------------------------------
# MATAR JUGADOR
# -----------------------------------
@socketio.on("matar_jugador")
def matar_jugador(data):
    codigo = data["codigo"]
    jugador = data["jugador"]
    partidas[codigo]["jugadores"][jugador] = "muerto"
    emit("jugadores", {
        "jugadores": partidas[codigo]["jugadores"],
        "fotos": partidas[codigo]["fotos"]
    }, to=codigo)

# -----------------------------------
# INICIAR HOGUERA
# -----------------------------------
@socketio.on("iniciar_hoguera")
def iniciar_hoguera(data):
    codigo = data["codigo"]
    jugador1 = data["jugador1"]
    jugador2 = data["jugador2"]
    host = data["host"]

    if host != "HOST":
        return

    if codigo in partidas:
        votacion = {
            "jugadores": [jugador1, jugador2],
            "votos": {jugador1: 0, jugador2: 0, "Nadie": 0},
            "activa": True
        }
        partidas[codigo]["votacion"] = votacion
        emit("votacion_iniciada", votacion, to=codigo)

# -----------------------------------
# SUMAR O RESTAR VOTO (solo host)
# -----------------------------------
@socketio.on("modificar_voto")
def modificar_voto(data):
    codigo = data["codigo"]
    jugador = data["jugador"]
    accion = data["accion"]
    host = data["host"]

    if host != "HOST":
        return

    votacion = partidas[codigo].get("votacion")
    if not votacion or not votacion["activa"]:
        return

    if jugador not in votacion["votos"]:
        votacion["votos"][jugador] = 0

    if accion == "sumar":
        votacion["votos"][jugador] += 1
    elif accion == "restar":
        votacion["votos"][jugador] = max(0, votacion["votos"][jugador]-1)

    emit("votos_actualizados", votacion["votos"], to=codigo)

# -----------------------------------
# TERMINAR HOGUERA
# -----------------------------------
@socketio.on("finalizar_hoguera")
def finalizar_hoguera(data):
    codigo = data["codigo"]
    host = data["host"]

    if host != "HOST":
        return

    votacion = partidas[codigo].get("votacion")
    if not votacion or not votacion["activa"]:
        return

    votacion["activa"] = False
    emit("votacion_finalizada", votacion["votos"], to=codigo)

# -----------------------------------
# RUN
# -----------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    socketio.run(app, host="0.0.0.0", port=port)
